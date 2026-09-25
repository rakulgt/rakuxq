from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .validation import validate_position

RED_PALACE = {(rank, file) for rank in range(7, 10) for file in range(3, 6)}
BLACK_PALACE = {(rank, file) for rank in range(0, 3) for file in range(3, 6)}
PIECE_SYMBOLS = frozenset("KABNRCPkabnrcp")


@dataclass(frozen=True, slots=True)
class SemanticCorrection:
    kind: str
    reason: str
    before_blocking: tuple[str, ...]
    after_blocking: tuple[str, ...]


def _find(
    grid: Sequence[Sequence[str]], symbol: str
) -> list[tuple[int, int]]:
    return [
        (rank, file)
        for rank, row in enumerate(grid)
        for file, value in enumerate(row)
        if value == symbol
    ]


def swap_piece_camps(grid: Sequence[Sequence[str]]) -> list[list[str]]:
    """Swap red/black piece classes without moving any board coordinate."""
    return [
        [value.swapcase() if value in PIECE_SYMBOLS else value for value in row]
        for row in grid
    ]


def correct_crossed_king_camps(
    grid: Sequence[Sequence[str]],
) -> tuple[list[list[str]], SemanticCorrection | None]:
    """Correct a decisive whole-board camp inversion.

    The layout model encodes both piece type and camp in one class.  On an
    unfamiliar visual skin it can invert the camp of every otherwise-correct
    class.  Xiangqi supplies a hard semantic signature for that failure: the
    sole red king is in Black's palace while the sole black king is in Red's.

    We intentionally require both kings and a strict validation improvement.
    A single misplaced/missing king is not enough evidence for a global swap.
    """
    original = [list(row) for row in grid]
    red_kings = _find(original, "K")
    black_kings = _find(original, "k")
    if len(red_kings) != 1 or len(black_kings) != 1:
        return original, None
    if red_kings[0] not in BLACK_PALACE or black_kings[0] not in RED_PALACE:
        return original, None

    candidate = swap_piece_camps(original)
    before = tuple(
        warning.code for warning in validate_position(original) if warning.blocking
    )
    after = tuple(
        warning.code for warning in validate_position(candidate) if warning.blocking
    )
    king_failures = {
        "RED_KING_OUTSIDE_PALACE",
        "BLACK_KING_OUTSIDE_PALACE",
    }
    if not king_failures.issubset(before) or king_failures.intersection(after):
        return original, None
    if len(after) >= len(before):
        return original, None

    return candidate, SemanticCorrection(
        kind="global_camp_swap",
        reason="crossed_kings_after_orientation_normalization",
        before_blocking=before,
        after_blocking=after,
    )
