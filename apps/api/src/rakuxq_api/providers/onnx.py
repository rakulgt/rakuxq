from __future__ import annotations

import time
from pathlib import Path
from threading import Lock

from ..domain import BoardPrediction, CellPrediction, Orientation
from .base import ProviderNotReady, RecognitionFailed, RecognitionProvider

LABELS = [".", "x", "K", "A", "B", "N", "R", "C", "P", "k", "a", "b", "n", "r", "c", "p"]


class OnnxRecognitionProvider(RecognitionProvider):
    """Two-stage four-corner pose + 90-cell layout ONNX inference.

    The preprocessing contract is compatible with the public
    yolo12138/Chinese_Chess_Recognition baseline. Model weights are external
    artifacts and are intentionally not bundled with this package.
    """

    name = "cchess-onnx"

    def __init__(
        self,
        pose_model: str,
        layout_model: str,
        model_version: str = "unverified",
        intra_op_num_threads: int = 2,
        portrait_fast_path_ratio: float = 1.5,
    ):
        self.pose_model = Path(pose_model)
        self.layout_model = Path(layout_model)
        self.model_version = model_version
        self.intra_op_num_threads = max(1, intra_op_num_threads)
        self.portrait_fast_path_ratio = portrait_fast_path_ratio
        self._pose_session = None
        self._layout_session = None
        self._load_lock = Lock()

    def ready(self) -> bool:
        return self.pose_model.is_file() and self.layout_model.is_file()

    def _load(self):
        if not self.ready():
            raise ProviderNotReady(
                "ONNX model files are missing; see models/README.md"
            )
        if self._pose_session is None:
            with self._load_lock:
                if self._pose_session is not None:
                    return self._pose_session, self._layout_session
                try:
                    import onnxruntime as ort
                except ImportError as exc:
                    raise ProviderNotReady("onnxruntime is not installed") from exc
                options = ort.SessionOptions()
                options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                options.intra_op_num_threads = self.intra_op_num_threads
                options.inter_op_num_threads = 1
                self._pose_session = ort.InferenceSession(
                    str(self.pose_model), sess_options=options, providers=["CPUExecutionProvider"]
                )
                self._layout_session = ort.InferenceSession(
                    str(self.layout_model), sess_options=options, providers=["CPUExecutionProvider"]
                )
        return self._pose_session, self._layout_session

    def warmup(self) -> None:
        """Load both sessions and execute one synthetic pass before serving traffic."""
        import cv2  # noqa: F401 -- import cost belongs to startup, not the first request
        import numpy as np

        pose, layout = self._load()
        for session in (pose, layout):
            model_input = session.get_inputs()[0]
            shape = self._concrete_shape(model_input.shape)
            zeros = np.zeros(shape, dtype=np.float32)
            session.run(None, {model_input.name: zeros})

    @staticmethod
    def _concrete_shape(shape: list[int | str | None]) -> tuple[int, ...]:
        return tuple(dimension if isinstance(dimension, int) else 1 for dimension in shape)

    def _pose_paddings(self, width: int, height: int) -> tuple[float, ...]:
        if height / max(width, 1) >= self.portrait_fast_path_ratio:
            return (1.25,)
        return (1.25, 1.5)

    @staticmethod
    def _corners_extend_outside(corners, width: int, height: int) -> bool:
        return any(
            x < 0 or x > width - 1 or y < 0 or y > height - 1
            for x, y in corners
        )

    @staticmethod
    def _project_grid_points(corners):
        import cv2
        import numpy as np

        board_corners = np.array([[0, 0], [8, 0], [0, 9], [8, 9]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(board_corners, corners.astype(np.float32))
        grid = np.array(
            [[file, rank] for rank in range(10) for file in range(9)],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(grid, matrix).reshape(-1, 2)

    @classmethod
    def _visible_grid_mask(cls, corners, width: int, height: int):
        points = cls._project_grid_points(corners)
        visible = [
            bool(0 <= x <= width - 1 and 0 <= y <= height - 1)
            for x, y in points
        ]
        return points, visible

    @staticmethod
    def _softmax_if_needed(values):
        import numpy as np

        row_sums = values.sum(axis=-1)
        if np.all(values >= 0) and np.all(values <= 1) and np.allclose(row_sums, 1, atol=1e-3):
            return values
        shifted = values - values.max(axis=-1, keepdims=True)
        exp = np.exp(shifted)
        return exp / exp.sum(axis=-1, keepdims=True)

    @staticmethod
    def _king_anchor_color_refinement(
        warped,
        symbols: list[str],
        visible: list[bool],
        minimum_anchor_distance: float = 0.04,
        minimum_assignment_margin: float = 0.02,
        maximum_nearest_distance: float = 0.50,
    ):
        """Refine camp case from the visual colours anchored by 帅 and 将.

        Piece identity is established first by the layout model.  The unique 帅
        (``K``) and 将 (``k``) patches then define image-local red and black colour
        prototypes.  Only the camp case of an already-known non-king piece may
        change, and only when both anchors are visually distinct and one anchor
        is a decisive match.  Empty/unknown cells and the king identities never
        change here.
        """
        import cv2
        import numpy as np

        red_anchors = [index for index, symbol in enumerate(symbols) if symbol == "K"]
        black_anchors = [index for index, symbol in enumerate(symbols) if symbol == "k"]
        if len(red_anchors) != 1 or len(black_anchors) != 1:
            return symbols.copy(), []

        mask = np.zeros((37, 37), dtype=np.uint8)
        cv2.circle(mask, (18, 18), 17, 255, -1)

        def histogram(index: int):
            rank, file = divmod(index, 9)
            center = (50.0 + file * 43.75, 50.0 + rank * (400.0 / 9.0))
            patch = cv2.getRectSubPix(warped, (37, 37), center)
            hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
            result = cv2.calcHist(
                [hsv], [0, 1, 2], mask, [12, 4, 4], [0, 180, 0, 256, 0, 256]
            )
            return cv2.normalize(result, result).flatten()

        occupied = [
            index
            for index, symbol in enumerate(symbols)
            if visible[index] and symbol not in {".", "x"}
        ]
        features = {index: histogram(index) for index in occupied}
        red_index = red_anchors[0]
        black_index = black_anchors[0]
        red_anchor = features.get(red_index)
        black_anchor = features.get(black_index)
        if red_anchor is None or black_anchor is None:
            return symbols.copy(), []
        anchor_distance = float(
            cv2.compareHist(red_anchor, black_anchor, cv2.HISTCMP_BHATTACHARYYA)
        )
        if anchor_distance < minimum_anchor_distance:
            return symbols.copy(), []

        refined = symbols.copy()
        details: list[dict[str, object]] = []
        for index in occupied:
            symbol = symbols[index]
            if symbol in {"K", "k"}:
                continue
            red_distance = float(
                cv2.compareHist(features[index], red_anchor, cv2.HISTCMP_BHATTACHARYYA)
            )
            black_distance = float(
                cv2.compareHist(
                    features[index], black_anchor, cv2.HISTCMP_BHATTACHARYYA
                )
            )
            nearest = min(red_distance, black_distance)
            margin = abs(red_distance - black_distance)
            if nearest > maximum_nearest_distance or margin < minimum_assignment_margin:
                continue
            inferred_red = red_distance < black_distance
            if inferred_red == symbol.isupper():
                continue
            corrected = symbol.upper() if inferred_red else symbol.lower()
            refined[index] = corrected
            details.append(
                {
                    "rank": index // 9,
                    "file": index % 9,
                    "from": symbol,
                    "to": corrected,
                    "red_distance": red_distance,
                    "black_distance": black_distance,
                    "assignment_margin": margin,
                    "anchor_distance": anchor_distance,
                }
            )
        return refined, details

    @staticmethod
    def _same_image_prototype_refinement(
        warped,
        symbols: list[str],
        confidences,
        visible: list[bool],
        prototype_confidence: float = 0.85,
        target_confidence: float = 0.75,
        minimum_similarity: float = 0.72,
        minimum_margin: float = 0.04,
    ):
        """Correct weak piece labels from strong same-set examples in one image.

        Physical sets often use fonts and materials absent from the training set, while
        repeating several visually identical rooks or pawns in the same position.  The
        layout model remains the primary classifier; this conservative pass only changes
        a known, low-confidence piece when a high-confidence piece of the same colour is
        a substantially better visual match.  Empty and unknown cells are never promoted.
        """
        import cv2
        import numpy as np

        gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
        features = []
        for index in range(90):
            rank, file = divmod(index, 9)
            center = (50.0 + file * 43.75, 50.0 + rank * (400.0 / 9.0))
            patch = cv2.getRectSubPix(gray, (37, 37), center)
            patch = cv2.resize(patch, (32, 32), interpolation=cv2.INTER_AREA).astype(
                np.float32
            )
            patch -= patch.mean()
            patch /= patch.std() + 1e-6
            features.append(patch.reshape(-1))

        prototypes = [
            index
            for index, symbol in enumerate(symbols)
            if visible[index]
            and symbol not in {".", "x"}
            and float(confidences[index]) >= prototype_confidence
        ]
        refined = symbols.copy()
        effective_confidences = np.asarray(confidences, dtype=np.float32).copy()
        details: list[dict[str, object]] = []
        for index, symbol in enumerate(symbols):
            if (
                not visible[index]
                or symbol in {".", "x"}
                or float(confidences[index]) >= target_confidence
            ):
                continue

            same_colour = [
                candidate
                for candidate in prototypes
                if symbols[candidate].isupper() == symbol.isupper()
            ]
            class_matches: dict[str, tuple[float, int]] = {}
            for candidate in same_colour:
                similarity = float(
                    np.dot(features[index], features[candidate]) / features[index].size
                )
                candidate_symbol = symbols[candidate]
                current = class_matches.get(candidate_symbol)
                if current is None or similarity > current[0]:
                    class_matches[candidate_symbol] = (similarity, candidate)

            ranked = sorted(class_matches.items(), key=lambda item: item[1][0], reverse=True)
            if not ranked:
                continue
            best_symbol, (best_similarity, prototype_index) = ranked[0]
            runner_up = ranked[1][1][0] if len(ranked) > 1 else -1.0
            if (
                best_symbol == symbol
                or best_similarity < minimum_similarity
                or best_similarity - runner_up < minimum_margin
            ):
                continue

            refined[index] = best_symbol
            effective_confidences[index] = best_similarity
            prototype_rank, prototype_file = divmod(prototype_index, 9)
            details.append(
                {
                    "rank": index // 9,
                    "file": index % 9,
                    "from": symbol,
                    "to": best_symbol,
                    "model_confidence": float(confidences[index]),
                    "similarity": best_similarity,
                    "runner_up_similarity": runner_up,
                    "prototype_rank": prototype_rank,
                    "prototype_file": prototype_file,
                }
            )
        return refined, effective_confidences, details

    @staticmethod
    def _affine_for_full_image(
        width: int,
        height: int,
        output=(256, 256),
        padding: float = 1.5,
    ):
        import cv2
        import numpy as np

        center = np.array([width / 2.0, height / 2.0], dtype=np.float32)
        scale = np.array([width * padding, height * padding], dtype=np.float32)
        aspect = output[0] / output[1]
        if scale[0] > scale[1] * aspect:
            scale[1] = scale[0] / aspect
        else:
            scale[0] = scale[1] * aspect

        src = np.array(
            [
                center,
                center + np.array([-scale[0] / 2.0, 0], dtype=np.float32),
                center + np.array([0, -scale[0] / 2.0], dtype=np.float32),
            ],
            dtype=np.float32,
        )
        dst_center = np.array([output[0] / 2.0, output[1] / 2.0], dtype=np.float32)
        dst = np.array(
            [
                dst_center,
                dst_center + np.array([-output[0] / 2.0, 0], dtype=np.float32),
                dst_center + np.array([0, -output[0] / 2.0], dtype=np.float32),
            ],
            dtype=np.float32,
        )
        forward = cv2.getAffineTransform(src, dst)
        inverse = cv2.getAffineTransform(dst, src)
        return forward, inverse

    def _predict_corners(self, bgr, pose, padding: float):
        import cv2
        import numpy as np

        height, width = bgr.shape[:2]
        forward, inverse = self._affine_for_full_image(width, height, padding=padding)
        pose_image = cv2.warpAffine(bgr, forward, (256, 256), flags=cv2.INTER_LINEAR)
        pose_rgb = cv2.cvtColor(pose_image, cv2.COLOR_BGR2RGB).astype(np.float32)
        pose_input = (pose_rgb - np.array([123.675, 116.28, 103.53])) / np.array(
            [58.395, 57.12, 57.375]
        )
        pose_input = np.transpose(pose_input, (2, 0, 1))[None, ...].astype(np.float32)
        pose_outputs = pose.run(None, {pose.get_inputs()[0].name: pose_input})
        if len(pose_outputs) != 2:
            raise RecognitionFailed("unexpected pose model outputs")
        simcc_x, simcc_y = pose_outputs
        x_index = np.argmax(simcc_x[0], axis=1).astype(np.float32) / 2.0
        y_index = np.argmax(simcc_y[0], axis=1).astype(np.float32) / 2.0
        keypoints_model = np.stack([x_index, y_index], axis=1)
        homogeneous = np.hstack(
            [keypoints_model, np.ones((keypoints_model.shape[0], 1), dtype=np.float32)]
        )
        corners = homogeneous @ inverse.T
        if corners.shape != (4, 2):
            raise RecognitionFailed(f"expected four board corners, got {corners.shape}")
        keypoint_scores = np.sqrt(
            np.maximum(simcc_x[0], 0).max(axis=1)
            * np.maximum(simcc_y[0], 0).max(axis=1)
        )

        polygon = corners[[0, 1, 3, 2]].astype(np.float32)
        area_ratio = abs(cv2.contourArea(polygon)) / float(width * height)
        plausible = cv2.isContourConvex(polygon) and area_ratio >= 0.10
        return corners, keypoint_scores, plausible, area_ratio

    def recognize(self, image: bytes, orientation: Orientation) -> BoardPrediction:
        started = time.perf_counter()
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise ProviderNotReady("opencv-python-headless and numpy are required") from exc

        pose, layout = self._load()
        loaded = time.perf_counter()
        encoded = np.frombuffer(image, dtype=np.uint8)
        bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if bgr is None:
            raise RecognitionFailed("image could not be decoded")
        height, width = bgr.shape[:2]
        decoded = time.perf_counter()

        paddings = self._pose_paddings(width, height)
        candidates = [
            (*self._predict_corners(bgr, pose, padding), padding)
            for padding in paddings
        ]
        first_corners, _, first_plausible, _, _ = candidates[0]
        if len(paddings) == 1 and (
            not first_plausible
            or self._corners_extend_outside(first_corners, width, height)
        ):
            candidates.append((*self._predict_corners(bgr, pose, 1.5), 1.5))
        pose_finished = time.perf_counter()
        plausible_candidates = [candidate for candidate in candidates if candidate[2]]
        if not plausible_candidates:
            raise RecognitionFailed("pose model did not produce a plausible board quadrilateral")
        corners, keypoint_scores, _, area_ratio, selected_padding = max(
            plausible_candidates,
            key=lambda candidate: float(candidate[1].min()),
        )

        destination = np.array([[50, 50], [400, 50], [50, 450], [400, 450]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), destination)
        board_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        warped = cv2.warpPerspective(board_rgb, matrix, (450, 500))
        cropped = warped[25:475, 25:425]
        layout_image = cv2.resize(cropped, (280, 315)).astype(np.float32)
        layout_input = (
            layout_image - np.array([123.675, 116.28, 103.53], dtype=np.float32)
        ) / np.array([58.395, 57.12, 57.375], dtype=np.float32)
        layout_input = np.transpose(layout_input, (2, 0, 1))[None, ...].astype(np.float32)
        warped_finished = time.perf_counter()
        outputs = layout.run(None, {layout.get_inputs()[0].name: layout_input})
        layout_finished = time.perf_counter()
        if len(outputs) != 1 or outputs[0].shape[1:] != (90, 16):
            raise RecognitionFailed(f"unexpected layout output shape: {outputs[0].shape}")
        probabilities = self._softmax_if_needed(outputs[0][0])
        indexes = probabilities.argmax(axis=1)
        confidences = probabilities[np.arange(90), indexes]
        raw_symbols = [LABELS[int(index)] for index in indexes]
        projected_points, visible = self._visible_grid_mask(corners, width, height)
        camp_symbols, camp_refinements = self._king_anchor_color_refinement(
            warped,
            raw_symbols,
            visible,
        )
        refined_symbols, effective_confidences, refinements = (
            self._same_image_prototype_refinement(
                warped,
                camp_symbols,
                confidences,
                visible,
            )
        )
        symbols = [
            refined_symbol if visible[index] else "."
            for index, refined_symbol in enumerate(refined_symbols)
        ]
        grid = [symbols[index : index + 9] for index in range(0, 90, 9)]
        cells = [
            CellPrediction(
                rank=index // 9,
                file=index % 9,
                symbol=symbols[index],
                confidence=float(effective_confidences[index]),
                visible=visible[index],
                assumed_empty=not visible[index],
                raw_symbol=raw_symbols[index],
                refinement=(
                    "+".join(
                        refinement
                        for refinement, changed in (
                            (
                                "king_anchor_color",
                                camp_symbols[index] != raw_symbols[index],
                            ),
                            (
                                "same_image_prototype",
                                refined_symbols[index] != camp_symbols[index],
                            ),
                        )
                        if changed
                    )
                    or None
                ),
                raw_confidence=(
                    float(confidences[index])
                    if refined_symbols[index] != raw_symbols[index]
                    else None
                ),
            )
            for index in range(90)
        ]
        assumed_empty_cells = [
            {"rank": index // 9, "file": index % 9}
            for index, is_visible in enumerate(visible)
            if not is_visible
        ]
        completed = time.perf_counter()
        return BoardPrediction(
            grid=grid,
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=float(np.clip(keypoint_scores.min(), 0, 1)),
            provider=self.name,
            model_version=self.model_version,
            corners=corners.astype(float).tolist(),
            elapsed_ms=round((completed - started) * 1000),
            metadata={
                "pose_padding": selected_padding,
                "pose_runs": len(candidates),
                "corner_confidences": keypoint_scores.astype(float).tolist(),
                "board_area_ratio": float(area_ratio),
                "visible_cell_count": sum(visible),
                "assumed_empty_cells": assumed_empty_cells,
                "projected_assumed_empty_centers": [
                    [float(projected_points[index][0]), float(projected_points[index][1])]
                    for index, is_visible in enumerate(visible)
                    if not is_visible
                ],
                "prototype_refinements": refinements,
                "camp_color_refinements": camp_refinements,
                "timings_ms": {
                    "load": round((loaded - started) * 1000),
                    "decode": round((decoded - loaded) * 1000),
                    "pose": round((pose_finished - decoded) * 1000),
                    "warp": round((warped_finished - pose_finished) * 1000),
                    "layout": round((layout_finished - warped_finished) * 1000),
                    "postprocess": round((completed - layout_finished) * 1000),
                },
            },
        )
