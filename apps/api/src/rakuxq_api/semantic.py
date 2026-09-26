from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .domain import Orientation
from .validation import validate_position

RED_PALACE = {(rank, file) for rank in range(7, 10) for file in range(3, 6)}
BLACK_PALACE = {(rank, file) for rank in range(0, 3) for file in range(3, 6)}


@dataclass(frozen=True, slots=True)
class SemanticOrientation:
    orientation: Orientation
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


def rotate_grid_180(grid: Sequence[Sequence[str]]) -> list[list[str]]:
    """Rotate coordinates while preserving every recognized piece identity."""
    return [list(reversed(row)) for row in reversed(grid)]


def infer_orientation_from_kings(
    grid: Sequence[Sequence[str]],
) -> SemanticOrientation | None:
    """Infer a black-bottom photograph from the immutable 帅/将 identities.

    Uppercase ``K`` means the model recognized 帅 and lowercase ``k`` means it
    recognized 将. Their identities must never be exchanged merely to satisfy
    palace rules. When both are cross-placed in the opposite canonical palaces,
    the safe competing hypothesis is a 180-degree coordinate rotation.

    Both kings and a strict legality improvement are required. A missing king,
    one displaced king, or an equally invalid rotated position remains unchanged.
    """
    original = [list(row) for row in grid]
    red_kings = _find(original, "K")
    black_kings = _find(original, "k")
    if len(red_kings) != 1 or len(black_kings) != 1:
        return None
    if red_kings[0] not in BLACK_PALACE or black_kings[0] not in RED_PALACE:
        return None

    candidate = rotate_grid_180(original)
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
        return None
    if len(after) >= len(before):
        return None

    return SemanticOrientation(
        orientation=Orientation.BLACK_BOTTOM,
        kind="rotate_180",
        reason="red_king_top_black_king_bottom_after_board_warp",
        before_blocking=before,
        after_blocking=after,
    )
