"""Small, stateless safety checks for the UCI boundary (not a search engine)."""

from collections.abc import Sequence
from dataclasses import dataclass

Grid = Sequence[Sequence[str]]
Square = tuple[int, int]


@dataclass(frozen=True, slots=True)
class PositionState:
    side_to_move: str
    in_check: bool
    legal_move_count: int
    terminal_reason: str | None = None
    winner: str | None = None


def grid_from_fen(fen: str) -> list[list[str]]:
    """Expand an already validated FEN; row zero is Black's home rank."""
    return [
        [cell for symbol in row for cell in (["."] * int(symbol) if symbol.isdigit() else [symbol])]
        for row in fen.split()[0].split("/")
    ]


def _palace(row: int, file: int, red: bool) -> bool:
    return 3 <= file <= 5 and (7 <= row <= 9 if red else 0 <= row <= 2)


def _attacks(grid: Grid, source: Square, target: Square) -> bool:
    row, file = source
    tr, tf = target
    dr, df = tr - row, tf - file
    if source == target:
        return False
    symbol = grid[row][file]
    red = symbol.isupper()
    kind = symbol.lower()
    if kind in {"r", "c", "k"} and (dr == 0 or df == 0):
        sr = (dr > 0) - (dr < 0)
        sf = (df > 0) - (df < 0)
        screens = sum(
            grid[row + sr * step][file + sf * step] != "."
            for step in range(1, max(abs(dr), abs(df)))
        )
        if kind == "r":
            return screens == 0
        if kind == "c":
            return screens == (0 if grid[tr][tf] == "." else 1)
        if grid[tr][tf].lower() == "k" and df == 0:
            return screens == 0
    if kind == "k":
        return abs(dr) + abs(df) == 1 and _palace(tr, tf, red)
    if kind == "a":
        return abs(dr) == abs(df) == 1 and _palace(tr, tf, red)
    if kind == "b":
        return (
            abs(dr) == abs(df) == 2
            and (tr >= 5 if red else tr <= 4)
            and grid[row + dr // 2][file + df // 2] == "."
        )
    if kind == "n":
        if (abs(dr), abs(df)) == (2, 1):
            return grid[row + dr // 2][file] == "."
        if (abs(dr), abs(df)) == (1, 2):
            return grid[row][file + df // 2] == "."
    if kind == "p":
        forward = -1 if red else 1
        crossed = row <= 4 if red else row >= 5
        return (dr == forward and df == 0) or (crossed and dr == 0 and abs(df) == 1)
    return False


def in_check(grid: Grid, red: bool) -> bool:
    king = "K" if red else "k"
    target = next(
        (r, f) for r, row in enumerate(grid) for f, symbol in enumerate(row) if symbol == king
    )
    return any(
        symbol != "." and symbol.isupper() != red and _attacks(grid, (r, f), target)
        for r, row in enumerate(grid)
        for f, symbol in enumerate(row)
    )


def legal_moves(grid: Grid, red: bool) -> list[str]:
    """Enumerate moves, including check evasions; never include a king capture."""
    moves: list[str] = []
    for r, row in enumerate(grid):
        for f, symbol in enumerate(row):
            if symbol == "." or symbol.isupper() != red:
                continue
            for tr in range(10):
                for tf in range(9):
                    target = grid[tr][tf]
                    if target != "." and (target.isupper() == red or target.lower() == "k"):
                        continue
                    if not _attacks(grid, (r, f), (tr, tf)):
                        continue
                    candidate = [list(rank) for rank in grid]
                    candidate[tr][tf], candidate[r][f] = symbol, "."
                    if not in_check(candidate, red):
                        moves.append(f"{'abcdefghi'[f]}{9-r}{'abcdefghi'[tf]}{9-tr}")
    return moves


def inspect_position(fen: str) -> tuple[PositionState, list[str]]:
    grid = grid_from_fen(fen)
    red = fen.split()[1] == "w"
    checked = in_check(grid, red)
    moves = legal_moves(grid, red)
    return PositionState(
        side_to_move="red" if red else "black",
        in_check=checked,
        legal_move_count=len(moves),
        terminal_reason=("checkmate" if checked else "stalemate") if not moves else None,
        winner=("black" if red else "red") if not moves else None,
    ), moves
