from __future__ import annotations

from typing import cast
from uuid import uuid4

from .domain import (
    BoardCell,
    Orientation,
    RecognitionResult,
    RecognitionStatus,
    SideToMove,
)
from .fen import FenError, normalize_orientation, to_fen, to_full_fen, to_piece_placement
from .providers.base import RecognitionProvider
from .semantic import correct_crossed_king_camps
from .validation import validate_position


class RecognitionService:
    def __init__(
        self,
        provider: RecognitionProvider,
        minimum_board_confidence: float = 0.55,
        minimum_cell_confidence: float = 0.75,
        acceptance_confidence: float = 0.55,
        minimum_partial_board_confidence: float = 0.35,
        minimum_partial_empty_confidence: float = 0.35,
        partial_acceptance_confidence: float = 0.35,
    ):
        self.provider = provider
        self.minimum_board_confidence = minimum_board_confidence
        self.minimum_cell_confidence = minimum_cell_confidence
        self.acceptance_confidence = acceptance_confidence
        self.minimum_partial_board_confidence = minimum_partial_board_confidence
        self.minimum_partial_empty_confidence = minimum_partial_empty_confidence
        self.partial_acceptance_confidence = partial_acceptance_confidence

    @staticmethod
    def _normalize_cell(cell: BoardCell, orientation: Orientation) -> BoardCell:
        if orientation == Orientation.BLACK_BOTTOM:
            return BoardCell(
                rank=9 - cell.rank,
                file=8 - cell.file,
                reason=cell.reason,
            )
        return cell

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

        grid = normalize_orientation(resolved_grid, effective_orientation)
        grid, semantic_correction = correct_crossed_king_camps(grid)
        if semantic_correction is not None:
            semantic_corrections = cast(
                list[dict[str, object]],
                prediction.metadata.setdefault("semantic_corrections", []),
            )
            semantic_corrections.append(
                {
                    "kind": semantic_correction.kind,
                    "reason": semantic_correction.reason,
                    "before_blocking": list(semantic_correction.before_blocking),
                    "after_blocking": list(semantic_correction.after_blocking),
                }
            )
        position_warnings = validate_position(grid)
        warnings = [warning.code for warning in position_warnings]

        assumed_empty_cells = [
            self._normalize_cell(cell, effective_orientation)
            for cell in raw_assumed_empty_cells
        ]
        partial_board = bool(assumed_empty_cells)
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

        board_threshold = (
            self.minimum_partial_board_confidence
            if partial_board
            else self.minimum_board_confidence
        )
        empty_threshold = (
            self.minimum_partial_empty_confidence
            if partial_board
            else self.minimum_cell_confidence
        )
        acceptance_threshold = (
            self.partial_acceptance_confidence
            if partial_board
            else self.acceptance_confidence
        )
        minimum_cell = min(minimum_occupied, minimum_empty)
        confidence = min(prediction.board_confidence, minimum_cell)

        reasons = {cell.reason for cell in assumed_empty_cells}
        if "out_of_frame" in reasons:
            warnings.append("UNSEEN_CELLS_ASSUMED_EMPTY")
        if "visually_uncertain" in reasons:
            warnings.append("UNCERTAIN_CELLS_ASSUMED_EMPTY")
        if any(cell.refinement is not None for cell in prediction.cells):
            warnings.append("SAME_IMAGE_PROTOTYPE_REFINEMENT")
        if semantic_correction is not None:
            warnings.append("SEMANTIC_CAMP_INVERSION_CORRECTED")
        if (
            partial_board
            and empty_threshold <= minimum_empty < self.minimum_cell_confidence
        ):
            warnings.append("PARTIAL_EMPTY_CONFIDENCE_RELAXED")
        if prediction.board_confidence < board_threshold:
            warnings.append("LOW_BOARD_CONFIDENCE")
        if (
            minimum_occupied < self.minimum_cell_confidence
            or minimum_empty < empty_threshold
        ):
            warnings.append("LOW_CELL_CONFIDENCE")
        if confidence < acceptance_threshold:
            warnings.append("BELOW_AUTO_ACCEPT_THRESHOLD")

        placement: str | None = None
        fen: str | None = None
        full_fen: str | None = None
        try:
            placement = to_piece_placement(grid)
            if side_to_move != SideToMove.UNKNOWN:
                fen = to_fen(placement, side_to_move)
                full_fen = to_full_fen(placement, side_to_move)
            else:
                warnings.append("SIDE_TO_MOVE_UNKNOWN")
        except FenError as exc:
            warnings.append(f"FEN_UNAVAILABLE:{exc}")

        blocking = any(warning.blocking for warning in position_warnings)
        accepted = (
            not blocking
            and fen is not None
            and prediction.board_confidence >= board_threshold
            and minimum_occupied >= self.minimum_cell_confidence
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
            side_to_move=side_to_move,
            orientation=effective_orientation,
            confidence=confidence,
            warnings=list(dict.fromkeys(warnings)),
            prediction=prediction,
            assumed_empty_cells=assumed_empty_cells,
        )
