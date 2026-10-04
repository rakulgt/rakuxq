from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from ..domain import BoardPrediction, CellPrediction, Orientation
from ..fen import normalize_orientation
from ..semantic import infer_orientation_from_kings
from ..validation import validate_position
from .base import ProviderNotReady, RecognitionFailed, RecognitionProvider

LABELS = [".", "x", "K", "A", "B", "N", "R", "C", "P", "k", "a", "b", "n", "r", "c", "p"]


@dataclass(slots=True)
class _LayoutCandidate:
    name: str
    corners: Any
    warped: Any
    raw_symbols: list[str]
    refined_symbols: list[str]
    confidences: Any
    effective_confidences: Any
    refinements: list[dict[str, Any]]
    visual_fusions: list[dict[str, Any]]
    camp_diagnostics: list[dict[str, Any]]
    projected_points: Any
    visible: list[bool]
    grid: list[list[str]]
    blocking_warnings: tuple[str, ...]
    warning_penalty: int
    minimum_occupied_confidence: float
    mean_occupied_confidence: float
    unknown_count: int
    warp_ms: int
    layout_ms: int
    postprocess_ms: int

    @property
    def score(self) -> tuple[float, ...]:
        return (
            -float(self.warning_penalty),
            -float(len(self.blocking_warnings)),
            self.minimum_occupied_confidence,
            self.mean_occupied_confidence,
            -float(self.unknown_count),
        )


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
    def _king_anchor_color_evidence(
        warped,
        symbols: list[str],
        confidences,
        visible: list[bool],
        minimum_anchor_confidence: float = 0.85,
        minimum_anchor_distance: float = 0.04,
        minimum_assignment_margin: float = 0.02,
        maximum_nearest_distance: float = 0.50,
    ):
        """Measure image-local camp colour evidence without changing model output.

        Piece identity is established first by the layout model.  The unique 帅
        (``K``) and 将 (``k``) patches then define image-local red and black colour
        prototypes.  Both agreements and disagreements are returned so a later,
        independently gated fusion pass can combine colour with piece-type
        prototypes and position legality.
        """
        import cv2
        import numpy as np

        red_anchors = [index for index, symbol in enumerate(symbols) if symbol == "K"]
        black_anchors = [index for index, symbol in enumerate(symbols) if symbol == "k"]
        if len(red_anchors) != 1 or len(black_anchors) != 1:
            return []

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
        if (
            float(confidences[red_index]) < minimum_anchor_confidence
            or float(confidences[black_index]) < minimum_anchor_confidence
        ):
            return []
        red_anchor = features.get(red_index)
        black_anchor = features.get(black_index)
        if red_anchor is None or black_anchor is None:
            return []
        anchor_distance = float(
            cv2.compareHist(red_anchor, black_anchor, cv2.HISTCMP_BHATTACHARYYA)
        )
        if anchor_distance < minimum_anchor_distance:
            return []

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
            suggested = symbol.upper() if inferred_red else symbol.lower()
            details.append(
                {
                    "rank": index // 9,
                    "file": index % 9,
                    "from": symbol,
                    "suggested": suggested,
                    "agrees_with_model": inferred_red == symbol.isupper(),
                    "raw_confidence": float(confidences[index]),
                    "applied": False,
                    "reason": "diagnostic_only_unsegmented_patch_colour",
                    "red_distance": red_distance,
                    "black_distance": black_distance,
                    "assignment_margin": margin,
                    "anchor_distance": anchor_distance,
                }
            )
        return details

    @classmethod
    def _king_anchor_color_diagnostics(
        cls,
        warped,
        symbols: list[str],
        confidences,
        visible: list[bool],
    ):
        """Retain the historical audit surface: only camp disagreements."""

        return [
            detail
            for detail in cls._king_anchor_color_evidence(
                warped,
                symbols,
                confidences,
                visible,
            )
            if not detail["agrees_with_model"]
        ]

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
                    "method": "same_image_prototype_correction",
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
    def _piece_type_prototype_evidence(
        warped,
        symbols: list[str],
        confidences,
        visible: list[bool],
        prototype_confidence: float = 0.85,
        target_confidence: float = 0.75,
    ) -> list[dict[str, Any]]:
        """Compare weak pieces with strong same-image piece-type examples.

        Camp case is deliberately ignored: a red cannon and a black cannon can
        confirm the shared cannon glyph/type while camp is assessed separately.
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
        details: list[dict[str, Any]] = []
        for index, symbol in enumerate(symbols):
            if (
                not visible[index]
                or symbol in {".", "x"}
                or float(confidences[index]) >= target_confidence
            ):
                continue

            type_matches: dict[str, tuple[float, int]] = {}
            for candidate in prototypes:
                candidate_type = symbols[candidate].lower()
                similarity = float(
                    np.dot(features[index], features[candidate]) / features[index].size
                )
                current = type_matches.get(candidate_type)
                if current is None or similarity > current[0]:
                    type_matches[candidate_type] = (similarity, candidate)

            ranked = sorted(type_matches.items(), key=lambda item: item[1][0], reverse=True)
            if not ranked:
                continue
            best_type, (best_similarity, prototype_index) = ranked[0]
            runner_up = ranked[1][1][0] if len(ranked) > 1 else -1.0
            details.append(
                {
                    "rank": index // 9,
                    "file": index % 9,
                    "model_symbol": symbol,
                    "model_confidence": float(confidences[index]),
                    "best_type": best_type,
                    "similarity": best_similarity,
                    "runner_up_similarity": runner_up,
                    "type_margin": best_similarity - runner_up,
                    "prototype_symbol": symbols[prototype_index],
                    "prototype_rank": prototype_index // 9,
                    "prototype_file": prototype_index % 9,
                }
            )
        return details

    @classmethod
    def _apply_low_confidence_visual_fusion(
        cls,
        symbols: list[str],
        model_confidences,
        model_margins,
        effective_confidences,
        visible: list[bool],
        type_evidence: list[dict[str, Any]],
        color_evidence: list[dict[str, Any]],
        minimum_model_confidence: float = 0.45,
        minimum_decisive_model_confidence: float = 0.50,
        minimum_model_margin: float = 0.15,
        target_confidence: float = 0.75,
        minimum_type_similarity: float = 0.68,
        minimum_type_margin: float = 0.12,
        minimum_anchor_distance: float = 0.20,
        minimum_color_margin: float = 0.15,
        maximum_color_distance: float = 0.40,
    ):
        """Fuse independent evidence for weak known pieces without lowering gates.

        A piece is confirmed when either a strong same-image prototype confirms
        its case-insensitive type, or it is the board's only weak occupied cell
        and the model has a decisive lead over its runner-up.  The two king
        anchors must independently confirm its camp.  A camp correction always
        requires prototype evidence and must strictly reduce blocking-position
        warnings.  High-confidence labels, piece types, empty cells, and unknown
        cells are never rewritten by this pass.
        """

        import numpy as np

        refined = symbols.copy()
        effective = np.asarray(effective_confidences, dtype=np.float32).copy()
        type_by_index = {
            int(detail["rank"]) * 9 + int(detail["file"]): detail
            for detail in type_evidence
        }
        color_by_index = {
            int(detail["rank"]) * 9 + int(detail["file"]): detail
            for detail in color_evidence
        }
        details: list[dict[str, Any]] = []
        weak_occupied = [
            index
            for index, symbol in enumerate(refined)
            if visible[index]
            and symbol not in {".", "x", "K", "k"}
            and minimum_model_confidence
            <= float(model_confidences[index])
            < target_confidence
        ]

        def blocking(values: list[str]) -> tuple[str, ...]:
            grid = [values[index : index + 9] for index in range(0, 90, 9)]
            validation_grid = cls._candidate_grid_for_validation(grid)
            return tuple(
                warning.code
                for warning in validate_position(validation_grid)
                if warning.blocking
            )

        for index, symbol in enumerate(refined):
            model_confidence = float(model_confidences[index])
            if (
                not visible[index]
                or symbol in {".", "x", "K", "k"}
                or model_confidence < minimum_model_confidence
                or float(effective[index]) >= target_confidence
            ):
                continue

            color_detail = color_by_index.get(index)
            if color_detail is None:
                continue
            type_detail = type_by_index.get(index)
            type_confirmed = bool(
                type_detail is not None
                and str(type_detail["best_type"]) == symbol.lower()
                and float(type_detail["similarity"]) >= minimum_type_similarity
                and float(type_detail["type_margin"]) >= minimum_type_margin
            )

            anchor_distance = float(color_detail["anchor_distance"])
            red_distance = float(color_detail["red_distance"])
            black_distance = float(color_detail["black_distance"])
            color_margin = float(color_detail["assignment_margin"])
            if (
                anchor_distance < minimum_anchor_distance
                or min(red_distance, black_distance) > maximum_color_distance
                or color_margin < minimum_color_margin
            ):
                continue

            suggested = str(color_detail["suggested"])
            if suggested.lower() != symbol.lower():
                continue
            before = blocking(refined)
            model_margin = float(model_margins[index])
            decisive_model_confirmation = (
                suggested == symbol
                and len(weak_occupied) == 1
                and model_confidence >= minimum_decisive_model_confidence
                and model_margin >= minimum_model_margin
                and not before
            )
            if not type_confirmed and not decisive_model_confirmation:
                continue

            type_similarity = (
                float(type_detail["similarity"]) if type_detail is not None else None
            )
            type_margin = (
                float(type_detail["type_margin"]) if type_detail is not None else None
            )
            method = (
                "same_image_prototype_confirmation"
                if type_confirmed
                else "model_margin_camp_confirmation"
            )
            if suggested != symbol:
                if not type_confirmed or type_detail is None:
                    continue
                proposed = refined.copy()
                proposed[index] = suggested
                after = blocking(proposed)
                if cls._blocking_warning_penalty(after) >= cls._blocking_warning_penalty(before):
                    continue
                refined = proposed
                method = "same_image_prototype_camp_correction"
            else:
                after = before

            evidence_confidence = (
                type_similarity
                if type_confirmed and type_similarity is not None
                else model_confidence + model_margin
            )
            fused_confidence = max(target_confidence, min(evidence_confidence, 1.0))
            effective[index] = fused_confidence
            details.append(
                {
                    "method": method,
                    "rank": index // 9,
                    "file": index % 9,
                    "from": symbol,
                    "to": refined[index],
                    "model_confidence": model_confidence,
                    "model_margin": model_margin,
                    "effective_confidence": fused_confidence,
                    "type_similarity": type_similarity,
                    "type_margin": type_margin,
                    "prototype_symbol": (
                        type_detail["prototype_symbol"] if type_detail is not None else None
                    ),
                    "prototype_rank": (
                        type_detail["prototype_rank"] if type_detail is not None else None
                    ),
                    "prototype_file": (
                        type_detail["prototype_file"] if type_detail is not None else None
                    ),
                    "red_distance": red_distance,
                    "black_distance": black_distance,
                    "color_margin": color_margin,
                    "anchor_distance": anchor_distance,
                    "blocking_warnings_before": list(before),
                    "blocking_warnings_after": list(after),
                }
            )
        return refined, effective, details

    @classmethod
    def _apply_decisive_empty_confirmation(
        cls,
        symbols: list[str],
        model_confidences,
        model_margins,
        effective_confidences,
        visible: list[bool],
        minimum_confidence: float = 0.65,
        minimum_margin: float = 0.50,
        target_confidence: float = 0.75,
    ):
        """Confirm one borderline empty cell when the model lead is decisive.

        This addresses transient board UI overlays without weakening the global
        empty-cell gate.  The pass is disabled for unknown cells, multiple weak
        cells, or an already impossible position.
        """

        import numpy as np

        effective = np.asarray(effective_confidences, dtype=np.float32).copy()
        if "x" in symbols:
            return effective, []
        weak = [
            index
            for index, symbol in enumerate(symbols)
            if visible[index]
            and float(effective[index]) < target_confidence
            and symbol not in {"K", "k"}
        ]
        if len(weak) != 1:
            return effective, []
        index = weak[0]
        if symbols[index] != ".":
            return effective, []
        confidence = float(model_confidences[index])
        margin = float(model_margins[index])
        if confidence < minimum_confidence or margin < minimum_margin:
            return effective, []

        grid = [symbols[offset : offset + 9] for offset in range(0, 90, 9)]
        validation_grid = cls._candidate_grid_for_validation(grid)
        blocking = [
            warning.code
            for warning in validate_position(validation_grid)
            if warning.blocking
        ]
        if blocking:
            return effective, []

        fused_confidence = max(target_confidence, min(confidence + margin, 1.0))
        effective[index] = fused_confidence
        return effective, [
            {
                "method": "model_margin_empty_confirmation",
                "rank": index // 9,
                "file": index % 9,
                "from": ".",
                "to": ".",
                "model_confidence": confidence,
                "model_margin": margin,
                "effective_confidence": fused_confidence,
                "blocking_warnings_before": blocking,
                "blocking_warnings_after": blocking,
            }
        ]

    @staticmethod
    def _blocking_warning_penalty(warnings: tuple[str, ...]) -> int:
        """Rank impossible layouts without pretending legality proves correctness."""
        penalty = 0
        for warning in warnings:
            if warning in {"RED_KING_COUNT", "BLACK_KING_COUNT"}:
                penalty += 100
            elif warning in {"TOO_MANY_K", "TOO_MANY_k"}:
                penalty += 100
            elif "KING_OUTSIDE_PALACE" in warning:
                penalty += 40
            elif warning.startswith("TOO_MANY_"):
                penalty += 20
            elif "ADVISOR_OUTSIDE_PALACE" in warning:
                penalty += 10
            elif "ELEPHANT_ILLEGAL_SQUARE" in warning:
                penalty += 10
            elif warning == "KINGS_FACE_EACH_OTHER":
                penalty += 5
            else:
                penalty += 1
        return penalty

    @staticmethod
    def _geometric_rotation_candidates(corners):
        """Return the four rotations of a quadrilateral, never a mirror.

        The pose model labels its points as A0/A8/J0/J8.  Highly stylized video
        frames can locate all four physical corners while permuting those semantic
        labels.  Sorting the physical polygon and rotating it covers that failure
        without introducing an unresolvable left/right reflection.
        """
        import numpy as np

        points = np.asarray(corners, dtype=np.float32)
        center = points.mean(axis=0)
        angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
        cyclic = points[np.argsort(angles)]
        start = int(np.argmin(cyclic.sum(axis=1)))
        cyclic = np.roll(cyclic, -start, axis=0)
        tl, tr, br, bl = cyclic
        portrait = [
            ("rotation_0", np.array([tl, tr, bl, br], dtype=np.float32)),
            ("rotation_180", np.array([br, bl, tr, tl], dtype=np.float32)),
        ]
        landscape = [
            ("rotation_90", np.array([tr, br, tl, bl], dtype=np.float32)),
            ("rotation_270", np.array([bl, tl, br, tr], dtype=np.float32)),
        ]
        horizontal = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2.0
        vertical = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
        ratio = horizontal / max(vertical, 1e-6)
        portrait_error = abs(np.log(ratio / (8.0 / 9.0)))
        landscape_error = abs(np.log(ratio / (9.0 / 8.0)))
        return portrait + landscape if portrait_error <= landscape_error else landscape + portrait

    @staticmethod
    def _candidate_grid_for_validation(grid: list[list[str]]) -> list[list[str]]:
        resolved = [["." if symbol == "x" else symbol for symbol in row] for row in grid]
        semantic_orientation = infer_orientation_from_kings(resolved)
        if semantic_orientation is not None:
            return normalize_orientation(resolved, semantic_orientation.orientation)
        return resolved

    def _classify_layout_candidate(
        self,
        *,
        board_rgb,
        corners,
        layout,
        width: int,
        height: int,
        name: str,
    ) -> _LayoutCandidate:
        import cv2
        import numpy as np

        warp_started = time.perf_counter()
        destination = np.array([[50, 50], [400, 50], [50, 450], [400, 450]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(np.asarray(corners, dtype=np.float32), destination)
        warped = cv2.warpPerspective(board_rgb, matrix, (450, 500))
        cropped = warped[25:475, 25:425]
        layout_image = cv2.resize(cropped, (280, 315)).astype(np.float32)
        layout_input = (
            layout_image - np.array([123.675, 116.28, 103.53], dtype=np.float32)
        ) / np.array([58.395, 57.12, 57.375], dtype=np.float32)
        layout_input = np.transpose(layout_input, (2, 0, 1))[None, ...].astype(np.float32)
        warp_finished = time.perf_counter()

        outputs = layout.run(None, {layout.get_inputs()[0].name: layout_input})
        layout_finished = time.perf_counter()
        if len(outputs) != 1 or outputs[0].shape[1:] != (90, 16):
            raise RecognitionFailed(f"unexpected layout output shape: {outputs[0].shape}")
        probabilities = self._softmax_if_needed(outputs[0][0])
        indexes = probabilities.argmax(axis=1)
        confidences = probabilities[np.arange(90), indexes]
        sorted_probabilities = np.sort(probabilities, axis=1)
        model_margins = sorted_probabilities[:, -1] - sorted_probabilities[:, -2]
        raw_symbols = [LABELS[int(index)] for index in indexes]
        projected_points, visible = self._visible_grid_mask(corners, width, height)
        refined_symbols, effective_confidences, refinements = self._same_image_prototype_refinement(
            warped,
            raw_symbols,
            confidences,
            visible,
        )
        color_evidence = self._king_anchor_color_evidence(
            warped,
            refined_symbols,
            confidences,
            visible,
        )
        camp_diagnostics = [
            detail for detail in color_evidence if not detail["agrees_with_model"]
        ]
        type_evidence = self._piece_type_prototype_evidence(
            warped,
            refined_symbols,
            effective_confidences,
            visible,
        )
        refined_symbols, effective_confidences, visual_fusions = (
            self._apply_low_confidence_visual_fusion(
                refined_symbols,
                confidences,
                model_margins,
                effective_confidences,
                visible,
                type_evidence,
                color_evidence,
            )
        )
        effective_confidences, empty_confirmations = (
            self._apply_decisive_empty_confirmation(
                refined_symbols,
                confidences,
                model_margins,
                effective_confidences,
                visible,
            )
        )
        visual_fusions.extend(empty_confirmations)
        symbols = [
            refined_symbol if visible[index] else "."
            for index, refined_symbol in enumerate(refined_symbols)
        ]
        grid = [symbols[index : index + 9] for index in range(0, 90, 9)]
        validation_grid = self._candidate_grid_for_validation(grid)
        blocking_warnings = tuple(
            warning.code for warning in validate_position(validation_grid) if warning.blocking
        )
        occupied_confidences = [
            float(effective_confidences[index])
            for index, symbol in enumerate(refined_symbols)
            if visible[index] and symbol not in {".", "x"}
        ]
        postprocess_finished = time.perf_counter()
        return _LayoutCandidate(
            name=name,
            corners=np.asarray(corners, dtype=np.float32),
            warped=warped,
            raw_symbols=raw_symbols,
            refined_symbols=refined_symbols,
            confidences=confidences,
            effective_confidences=effective_confidences,
            refinements=refinements,
            visual_fusions=visual_fusions,
            camp_diagnostics=camp_diagnostics,
            projected_points=projected_points,
            visible=visible,
            grid=grid,
            blocking_warnings=blocking_warnings,
            warning_penalty=self._blocking_warning_penalty(blocking_warnings),
            minimum_occupied_confidence=min(occupied_confidences, default=1.0),
            mean_occupied_confidence=(
                sum(occupied_confidences) / len(occupied_confidences)
                if occupied_confidences
                else 1.0
            ),
            unknown_count=sum(symbol == "x" for symbol in symbols),
            warp_ms=round((warp_finished - warp_started) * 1000),
            layout_ms=round((layout_finished - warp_finished) * 1000),
            postprocess_ms=round((postprocess_finished - layout_finished) * 1000),
        )

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

        board_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        initial = self._classify_layout_candidate(
            board_rgb=board_rgb,
            corners=corners,
            layout=layout,
            width=width,
            height=height,
            name="pose",
        )
        board_confidence = float(np.clip(keypoint_scores.min(), 0, 1))
        fallback_reasons = []
        if initial.blocking_warnings:
            fallback_reasons.append("blocking_position_warnings")
        if board_confidence < 0.40 and initial.minimum_occupied_confidence < 0.75:
            fallback_reasons.append("low_corner_and_piece_confidence")

        layout_candidates = [initial]
        if fallback_reasons:
            for index, (name, candidate_corners) in enumerate(
                self._geometric_rotation_candidates(corners)
            ):
                if not any(
                    np.allclose(candidate_corners, existing.corners, atol=1.0)
                    for existing in layout_candidates
                ):
                    layout_candidates.append(
                        self._classify_layout_candidate(
                            board_rgb=board_rgb,
                            corners=candidate_corners,
                            layout=layout,
                            width=width,
                            height=height,
                            name=name,
                        )
                    )
                if index == 1 and any(
                    candidate.warning_penalty == 0 for candidate in layout_candidates
                ):
                    break

        selected = max(layout_candidates, key=lambda candidate: candidate.score)
        zero_warning_candidates = [
            candidate for candidate in layout_candidates if candidate.warning_penalty == 0
        ]
        recovery_trusted = (
            bool(fallback_reasons)
            and len(zero_warning_candidates) == 1
            and zero_warning_candidates[0] is selected
            and board_confidence >= 0.30
            and selected.minimum_occupied_confidence >= 0.45
            and selected.mean_occupied_confidence >= 0.85
        )
        recovery_applied = selected is not initial

        corners = selected.corners
        raw_symbols = selected.raw_symbols
        confidences = selected.confidences
        effective_confidences = selected.effective_confidences
        visible = selected.visible
        projected_points = selected.projected_points
        grid = selected.grid
        symbols = [symbol for row in grid for symbol in row]
        refinements_by_index: dict[int, list[str]] = {}
        for detail in [*selected.refinements, *selected.visual_fusions]:
            index = int(detail["rank"]) * 9 + int(detail["file"])
            refinements_by_index.setdefault(index, []).append(str(detail["method"]))
        cells = [
            CellPrediction(
                rank=index // 9,
                file=index % 9,
                symbol=symbols[index],
                confidence=float(effective_confidences[index]),
                visible=visible[index],
                assumed_empty=not visible[index],
                raw_symbol=raw_symbols[index],
                refinement="+".join(refinements_by_index.get(index, [])) or None,
                raw_confidence=(
                    float(confidences[index])
                    if index in refinements_by_index
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
            board_confidence=board_confidence,
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
                "projected_king_centers": [
                    {
                        "symbol": symbol,
                        "rank": index // 9,
                        "file": index % 9,
                        "x": float(projected_points[index][0]),
                        "y": float(projected_points[index][1]),
                    }
                    for index, symbol in enumerate(symbols)
                    if symbol in {"K", "k"}
                ],
                "prototype_refinements": [
                    *selected.refinements,
                    *selected.visual_fusions,
                ],
                "camp_color_refinements": [
                    detail
                    for detail in selected.visual_fusions
                    if detail["method"] == "same_image_prototype_camp_correction"
                ],
                "low_confidence_visual_fusions": selected.visual_fusions,
                "camp_color_diagnostics": selected.camp_diagnostics,
                "corner_order_recovery": {
                    "triggered": bool(fallback_reasons),
                    "reasons": fallback_reasons,
                    "applied": recovery_applied,
                    "trusted": recovery_trusted,
                    "selected": selected.name,
                    "layout_runs": len(layout_candidates),
                    "candidates": [
                        {
                            "name": candidate.name,
                            "blocking_warnings": list(candidate.blocking_warnings),
                            "warning_penalty": candidate.warning_penalty,
                            "minimum_occupied_confidence": (candidate.minimum_occupied_confidence),
                            "mean_occupied_confidence": (candidate.mean_occupied_confidence),
                            "unknown_count": candidate.unknown_count,
                            "selected": candidate is selected,
                        }
                        for candidate in layout_candidates
                    ],
                },
                "timings_ms": {
                    "load": round((loaded - started) * 1000),
                    "decode": round((decoded - loaded) * 1000),
                    "pose": round((pose_finished - decoded) * 1000),
                    "warp": sum(candidate.warp_ms for candidate in layout_candidates),
                    "layout": sum(candidate.layout_ms for candidate in layout_candidates),
                    "postprocess": sum(candidate.postprocess_ms for candidate in layout_candidates),
                },
            },
        )
