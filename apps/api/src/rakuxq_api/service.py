from __future__ import annotations

from typing import cast
from uuid import uuid4

from .domain import (
    BoardCell,
    BoardPrediction,
    Orientation,
    RecognitionResult,
    RecognitionStatus,
    SideToMove,
)
from .fen import FenError, normalize_orientation, to_fen, to_full_fen, to_piece_placement
from .providers.base import RecognitionProvider
from .semantic import infer_orientation_from_kings
from .validation import validate_position


class RecognitionService:
    def __init__(
        self,
        provider: RecognitionProvider,
        minimum_board_confidence: float = 0.50,
        minimum_cell_confidence: float = 0.75,
        acceptance_confidence: float = 0.50,
        minimum_partial_board_confidence: float = 0.30,
        minimum_partial_empty_confidence: float = 0.30,
        partial_acceptance_confidence: float = 0.30,
        minimum_recovered_board_confidence: float = 0.30,
        minimum_recovered_piece_confidence: float = 0.45,
        recovered_acceptance_confidence: float = 0.30,
    ):
        self.provider = provider
        self.minimum_board_confidence = minimum_board_confidence
        self.minimum_cell_confidence = minimum_cell_confidence
        self.acceptance_confidence = acceptance_confidence
        self.minimum_partial_board_confidence = minimum_partial_board_confidence
        self.minimum_partial_empty_confidence = minimum_partial_empty_confidence
        self.partial_acceptance_confidence = partial_acceptance_confidence
        self.minimum_recovered_board_confidence = minimum_recovered_board_confidence
        self.minimum_recovered_piece_confidence = minimum_recovered_piece_confidence
        self.recovered_acceptance_confidence = recovered_acceptance_confidence

    @staticmethod
    def _normalize_cell(cell: BoardCell, orientation: Orientation) -> BoardCell:
        if orientation == Orientation.BLACK_BOTTOM:
            return BoardCell(
                rank=9 - cell.rank,
                file=8 - cell.file,
                reason=cell.reason,
            )
        return cell

    @staticmethod
    def _infer_side_to_move_from_bottom_king(
        grid: list[list[str]],
        prediction: BoardPrediction,
    ) -> tuple[SideToMove, dict[str, object]]:
        red_kings = [
            (rank, file)
            for rank, row in enumerate(grid)
            for file, symbol in enumerate(row)
            if symbol == "K"
        ]
        black_kings = [
            (rank, file)
            for rank, row in enumerate(grid)
            for file, symbol in enumerate(row)
            if symbol == "k"
        ]
        evidence: dict[str, object] = {
            "method": "lower_king_original_image_center_is_side_to_move",
            "red_king_positions": [list(position) for position in red_kings],
            "black_king_positions": [list(position) for position in black_kings],
        }
        if len(red_kings) != 1 or len(black_kings) != 1:
            evidence.update(
                {
                    "resolved": False,
                    "reason": "requires_exactly_one_red_and_one_black_king",
                }
            )
            return SideToMove.UNKNOWN, evidence

        projected_centers = prediction.metadata.get("projected_king_centers")
        centers = projected_centers if isinstance(projected_centers, list) else []

        def find_center(symbol: str, position: tuple[int, int]):
            rank, file = position
            matches = [
                center
                for center in centers
                if isinstance(center, dict)
                and center.get("symbol") == symbol
                and center.get("rank") == rank
                and center.get("file") == file
                and isinstance(center.get("y"), (int, float))
            ]
            return matches[0] if len(matches) == 1 else None

        red_center = find_center("K", red_kings[0])
        black_center = find_center("k", black_kings[0])
        if red_center is None or black_center is None:
            evidence.update(
                {
                    "resolved": False,
                    "reason": "king_original_image_centers_unavailable",
                }
            )
            return SideToMove.UNKNOWN, evidence

        red_image_center = [red_center.get("x"), red_center["y"]]
        black_image_center = [black_center.get("x"), black_center["y"]]
        evidence.update(
            {
                "coordinate_space": "original_image_pixels",
                "red_king_image_center": red_image_center,
                "black_king_image_center": black_image_center,
            }
        )
        red_image_y = float(red_center["y"])
        black_image_y = float(black_center["y"])
        if abs(red_image_y - black_image_y) < 1e-6:
            evidence.update(
                {
                    "resolved": False,
                    "reason": "kings_have_the_same_original_image_height",
                }
            )
            return SideToMove.UNKNOWN, evidence

        inferred = (
            SideToMove.RED
            if red_image_y > black_image_y
            else SideToMove.BLACK
        )
        evidence.update(
            {
                "resolved": True,
                "side_to_move": inferred.value,
                "lower_king": "red_king" if inferred == SideToMove.RED else "black_king",
                "reason": "lower_side_is_the_requesting_player",
            }
        )
        return inferred, evidence

    def recognize(
        self,
        image: bytes,
        side_to_move: SideToMove,
        orientation: Orientation,
    ) -> RecognitionResult:
        request_id = f"rec_{uuid4().hex}"
        prediction = self.provider.recognize(image, orientation)
        effective_orientation = (
            prediction.orientation if orientation == Orientation.AUTO else orientation
        )
        resolved_grid = [row.copy() for row in prediction.grid]
        raw_assumed_empty_cells = [
            BoardCell(rank=cell.rank, file=cell.file, reason="out_of_frame")
            for cell in prediction.cells
            if cell.assumed_empty
        ]
        assumed_coordinates = {
            (cell.rank, cell.file) for cell in raw_assumed_empty_cells
        }
        for cell in prediction.cells:
            coordinate = (cell.rank, cell.file)
            if coordinate not in assumed_coordinates and cell.symbol == "x":
                resolved_grid[cell.rank][cell.file] = "."
                raw_assumed_empty_cells.append(
                    BoardCell(
                        rank=cell.rank,
                        file=cell.file,
                        reason="visually_uncertain",
                    )
                )
                assumed_coordinates.add(coordinate)

        resolved_side_to_move = side_to_move
        side_to_move_inference: dict[str, object] | None = None
        if side_to_move == SideToMove.AUTO:
            resolved_side_to_move, side_to_move_inference = (
                self._infer_side_to_move_from_bottom_king(resolved_grid, prediction)
            )
            prediction.metadata["side_to_move_inference"] = side_to_move_inference

        semantic_orientation = (
            infer_orientation_from_kings(resolved_grid)
            if orientation == Orientation.AUTO
            else None
        )
        if semantic_orientation is not None:
            effective_orientation = semantic_orientation.orientation
            semantic_orientations = cast(
                list[dict[str, object]],
                prediction.metadata.setdefault("semantic_orientations", []),
            )
            semantic_orientations.append(
                {
                    "orientation": semantic_orientation.orientation.value,
                    "kind": semantic_orientation.kind,
                    "reason": semantic_orientation.reason,
                    "before_blocking": list(semantic_orientation.before_blocking),
                    "after_blocking": list(semantic_orientation.after_blocking),
                }
            )
        grid = normalize_orientation(resolved_grid, effective_orientation)
        position_warnings = validate_position(grid)
        warnings = [warning.code for warning in position_warnings]
        if side_to_move_inference is not None:
            if resolved_side_to_move in {SideToMove.RED, SideToMove.BLACK}:
                warnings.append("SIDE_TO_MOVE_INFERRED_FROM_BOTTOM_KING")
            else:
                warnings.append("SIDE_TO_MOVE_AUTO_UNRESOLVED")

        assumed_empty_cells = [
            self._normalize_cell(cell, effective_orientation)
            for cell in raw_assumed_empty_cells
        ]
        partial_board = bool(assumed_empty_cells)
        recovery = prediction.metadata.get("corner_order_recovery")
        trusted_corner_recovery = bool(
            isinstance(recovery, dict) and recovery.get("trusted") is True
        )
        visible_cells = [
            cell
            for cell in prediction.cells
            if (cell.rank, cell.file) not in assumed_coordinates
        ]
        occupied_cells = [cell for cell in visible_cells if cell.symbol not in {".", "x"}]
        empty_cells = [cell for cell in visible_cells if cell.symbol == "."]
        minimum_occupied = min(
            (cell.confidence for cell in occupied_cells), default=1.0
        )
        minimum_empty = min((cell.confidence for cell in empty_cells), default=1.0)

        if trusted_corner_recovery:
            board_threshold = self.minimum_recovered_board_confidence
            occupied_threshold = self.minimum_recovered_piece_confidence
            acceptance_threshold = self.recovered_acceptance_confidence
        else:
            board_threshold = (
                self.minimum_partial_board_confidence
                if partial_board
                else self.minimum_board_confidence
            )
            occupied_threshold = self.minimum_cell_confidence
            acceptance_threshold = (
                self.partial_acceptance_confidence
                if partial_board
                else self.acceptance_confidence
            )
        empty_threshold = (
            self.minimum_partial_empty_confidence
            if partial_board
            else self.minimum_cell_confidence
        )
        minimum_cell = min(minimum_occupied, minimum_empty)
        confidence = min(prediction.board_confidence, minimum_cell)

        reasons = {cell.reason for cell in assumed_empty_cells}
        if "out_of_frame" in reasons:
            warnings.append("UNSEEN_CELLS_ASSUMED_EMPTY")
        if "visually_uncertain" in reasons:
            warnings.append("UNCERTAIN_CELLS_ASSUMED_EMPTY")
        if any(
            cell.refinement is not None
            and "same_image_prototype" in cell.refinement
            for cell in prediction.cells
        ):
            warnings.append("SAME_IMAGE_PROTOTYPE_REFINEMENT")
        if semantic_orientation is not None:
            warnings.append("SEMANTIC_ORIENTATION_ROTATED")
        if trusted_corner_recovery:
            warnings.append("CORNER_ORDER_RECOVERY")
        if (
            partial_board
            and empty_threshold <= minimum_empty < self.minimum_cell_confidence
        ):
            warnings.append("PARTIAL_EMPTY_CONFIDENCE_RELAXED")
        if prediction.board_confidence < board_threshold:
            warnings.append("LOW_BOARD_CONFIDENCE")
        if minimum_occupied < occupied_threshold or minimum_empty < empty_threshold:
            warnings.append("LOW_CELL_CONFIDENCE")
        if (
            trusted_corner_recovery
            and minimum_occupied < self.minimum_cell_confidence
        ):
            warnings.append("CORNER_ORDER_CONFIDENCE_RELAXED")
        if confidence < acceptance_threshold:
            warnings.append("BELOW_AUTO_ACCEPT_THRESHOLD")

        placement: str | None = None
        fen: str | None = None
        full_fen: str | None = None
        try:
            placement = to_piece_placement(grid)
            if resolved_side_to_move != SideToMove.UNKNOWN:
                fen = to_fen(placement, resolved_side_to_move)
                full_fen = to_full_fen(placement, resolved_side_to_move)
            else:
                if side_to_move != SideToMove.AUTO:
                    warnings.append("SIDE_TO_MOVE_UNKNOWN")
        except FenError as exc:
            warnings.append(f"FEN_UNAVAILABLE:{exc}")

        blocking = any(warning.blocking for warning in position_warnings)
        accepted = (
            not blocking
            and fen is not None
            and prediction.board_confidence >= board_threshold
            and minimum_occupied >= occupied_threshold
            and minimum_empty >= empty_threshold
            and confidence >= acceptance_threshold
        )
        status = RecognitionStatus.ACCEPTED if accepted else RecognitionStatus.REVIEW_REQUIRED
        return RecognitionResult(
            request_id=request_id,
            status=status,
            grid=grid,
            piece_placement=placement,
            fen=fen,
            full_fen=full_fen,
            side_to_move=resolved_side_to_move,
            orientation=effective_orientation,
            confidence=confidence,
            warnings=list(dict.fromkeys(warnings)),
            prediction=prediction,
            assumed_empty_cells=assumed_empty_cells,
        )
