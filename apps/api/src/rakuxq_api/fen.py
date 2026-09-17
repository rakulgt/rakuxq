from __future__ import annotations

from collections.abc import Sequence

from .domain import Orientation, SideToMove

ROWS = 10
FILES = 9
EMPTY = "."
UNKNOWN = "x"
PIECES = frozenset("KABNRCPkabnrcp")
ALLOWED = PIECES | {EMPTY, UNKNOWN}


class FenError(ValueError):
    """The recognized grid cannot be represented safely as FEN."""


def validate_grid_shape(grid: Sequence[Sequence[str]]) -> None:
    if len(grid) != ROWS:
        raise FenError(f"expected {ROWS} ranks, got {len(grid)}")
    for rank, row in enumerate(grid):
        if len(row) != FILES:
            raise FenError(f"rank {rank} expected {FILES} files, got {len(row)}")
        invalid = [symbol for symbol in row if symbol not in ALLOWED]
        if invalid:
            raise FenError(f"rank {rank} contains unsupported symbols: {invalid!r}")


def normalize_orientation(
    grid: Sequence[Sequence[str]], orientation: Orientation
) -> list[list[str]]:
    validate_grid_shape(grid)
    normalized = [list(row) for row in grid]
    if orientation == Orientation.BLACK_BOTTOM:
        normalized = [list(reversed(row)) for row in reversed(normalized)]
    return normalized


def to_piece_placement(grid: Sequence[Sequence[str]]) -> str:
    validate_grid_shape(grid)
    if any(UNKNOWN in row for row in grid):
        raise FenError("grid contains unknown cells")

    encoded_rows: list[str] = []
    for row in grid:
        empty_run = 0
        encoded = ""
        for symbol in row:
            if symbol == EMPTY:
                empty_run += 1
                continue
            if empty_run:
                encoded += str(empty_run)
                empty_run = 0
            encoded += symbol
        if empty_run:
            encoded += str(empty_run)
        encoded_rows.append(encoded or "9")
    return "/".join(encoded_rows)


def to_fen(piece_placement: str, side_to_move: SideToMove) -> str:
    if side_to_move == SideToMove.UNKNOWN:
        raise FenError("side to move is required for a complete FEN")
    active = "w" if side_to_move == SideToMove.RED else "b"
    return f"{piece_placement} {active}"


def to_full_fen(piece_placement: str, side_to_move: SideToMove) -> str:
    return f"{to_fen(piece_placement, side_to_move)} - - 0 1"
