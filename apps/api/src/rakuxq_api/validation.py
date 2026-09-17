from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from .fen import validate_grid_shape


@dataclass(frozen=True, slots=True)
class PositionWarning:
    code: str
    blocking: bool


MAX_COUNTS = {
    "K": 1,
    "A": 2,
    "B": 2,
    "N": 2,
    "R": 2,
    "C": 2,
    "P": 5,
    "k": 1,
    "a": 2,
    "b": 2,
    "n": 2,
    "r": 2,
    "c": 2,
    "p": 5,
}

RED_ADVISOR_SQUARES = {(7, 3), (7, 5), (8, 4), (9, 3), (9, 5)}
BLACK_ADVISOR_SQUARES = {(0, 3), (0, 5), (1, 4), (2, 3), (2, 5)}
RED_ELEPHANT_SQUARES = {(5, 2), (5, 6), (7, 0), (7, 4), (7, 8), (9, 2), (9, 6)}
BLACK_ELEPHANT_SQUARES = {(0, 2), (0, 6), (2, 0), (2, 4), (2, 8), (4, 2), (4, 6)}


def _find(grid: Sequence[Sequence[str]], symbol: str) -> list[tuple[int, int]]:
    return [
        (rank, file)
        for rank, row in enumerate(grid)
        for file, value in enumerate(row)
        if value == symbol
    ]


def validate_position(grid: Sequence[Sequence[str]]) -> list[PositionWarning]:
    validate_grid_shape(grid)
    warnings: list[PositionWarning] = []
    flat = [value for row in grid for value in row]
    counts = Counter(flat)

    if counts["x"]:
        warnings.append(PositionWarning("UNKNOWN_CELLS", True))

    for symbol, maximum in MAX_COUNTS.items():
        if counts[symbol] > maximum:
            warnings.append(PositionWarning(f"TOO_MANY_{symbol}", True))

    red_kings = _find(grid, "K")
    black_kings = _find(grid, "k")
    if len(red_kings) != 1:
        warnings.append(PositionWarning("RED_KING_COUNT", True))
    if len(black_kings) != 1:
        warnings.append(PositionWarning("BLACK_KING_COUNT", True))

    for rank, file in red_kings:
        if rank not in range(7, 10) or file not in range(3, 6):
            warnings.append(PositionWarning("RED_KING_OUTSIDE_PALACE", True))
    for rank, file in black_kings:
        if rank not in range(0, 3) or file not in range(3, 6):
            warnings.append(PositionWarning("BLACK_KING_OUTSIDE_PALACE", True))

    for square in _find(grid, "A"):
        if square not in RED_ADVISOR_SQUARES:
            warnings.append(PositionWarning("RED_ADVISOR_OUTSIDE_PALACE", True))
    for square in _find(grid, "a"):
        if square not in BLACK_ADVISOR_SQUARES:
            warnings.append(PositionWarning("BLACK_ADVISOR_OUTSIDE_PALACE", True))
    if any(square not in RED_ELEPHANT_SQUARES for square in _find(grid, "B")):
        warnings.append(PositionWarning("RED_ELEPHANT_ILLEGAL_SQUARE", True))
    if any(square not in BLACK_ELEPHANT_SQUARES for square in _find(grid, "b")):
        warnings.append(PositionWarning("BLACK_ELEPHANT_ILLEGAL_SQUARE", True))

    if len(red_kings) == 1 and len(black_kings) == 1:
        red_rank, red_file = red_kings[0]
        black_rank, black_file = black_kings[0]
        if red_file == black_file:
            between = [
                grid[rank][red_file]
                for rank in range(black_rank + 1, red_rank)
            ]
            if all(value == "." for value in between):
                warnings.append(PositionWarning("KINGS_FACE_EACH_OTHER", True))

    return warnings
