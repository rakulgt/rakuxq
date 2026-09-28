from __future__ import annotations

from collections.abc import Iterable

_FILES = "abcdefghi"
_RED_NUMERALS = "一二三四五六七八九"
_PIECE_NAMES = {
    "K": "帅",
    "A": "仕",
    "B": "相",
    "N": "马",
    "R": "车",
    "C": "炮",
    "P": "兵",
    "k": "将",
    "a": "士",
    "b": "象",
    "n": "马",
    "r": "车",
    "c": "炮",
    "p": "卒",
}


def _parse_board(fen: str) -> dict[tuple[int, int], str]:
    placement = fen.strip().split()[0]
    board: dict[tuple[int, int], str] = {}
    for row_index, row in enumerate(placement.split("/")):
        file_index = 0
        rank = 9 - row_index
        for symbol in row:
            if symbol.isdigit():
                file_index += int(symbol)
            else:
                board[(file_index, rank)] = symbol
                file_index += 1
    return board


def _square(value: str) -> tuple[int, int]:
    if len(value) != 2 or value[0] not in _FILES or value[1] not in "0123456789":
        raise ValueError(f"invalid ICCS square: {value!r}")
    return _FILES.index(value[0]), int(value[1])


def _number(value: int, red: bool) -> str:
    if not 1 <= value <= 9:
        raise ValueError(f"Chinese notation number is outside 1-9: {value}")
    return _RED_NUMERALS[value - 1] if red else str(value)


def _file_number(file_index: int, red: bool) -> str:
    return _number(9 - file_index if red else file_index + 1, red)


def _source_name(
    board: dict[tuple[int, int], str],
    symbol: str,
    source_file: int,
    source_rank: int,
) -> str:
    red = symbol.isupper()
    piece_name = _PIECE_NAMES[symbol]
    peers = sorted(
        (
            rank
            for (file_index, rank), candidate in board.items()
            if file_index == source_file and candidate == symbol
        ),
        reverse=red,
    )
    if len(peers) == 1:
        return piece_name + _file_number(source_file, red)

    position = peers.index(source_rank)
    if len(peers) == 2:
        prefix = ("前", "后")[position]
    elif len(peers) == 3:
        prefix = ("前", "中", "后")[position]
    elif position == 0:
        prefix = "前"
    elif position == len(peers) - 1:
        prefix = "后"
    else:
        # Four or five same-file pawns are legal but rare. Number the interior
        # pawns from the front so the notation remains deterministic.
        prefix = _number(position + 1, red)
    return prefix + piece_name


def _format_move(
    board: dict[tuple[int, int], str],
    iccs: str,
) -> str:
    if len(iccs) < 4:
        raise ValueError(f"invalid ICCS move: {iccs!r}")
    source_file, source_rank = _square(iccs[:2].lower())
    target_file, target_rank = _square(iccs[2:4].lower())
    symbol = board.get((source_file, source_rank))
    if symbol not in _PIECE_NAMES:
        raise ValueError(f"ICCS source square {iccs[:2]!r} is empty")

    red = symbol.isupper()
    source_name = _source_name(board, symbol, source_file, source_rank)
    if source_rank == target_rank:
        return source_name + "平" + _file_number(target_file, red)

    advancing = target_rank > source_rank if red else target_rank < source_rank
    action = "进" if advancing else "退"
    if symbol.lower() in {"n", "b", "a"}:
        suffix = _file_number(target_file, red)
    else:
        suffix = _number(abs(target_rank - source_rank), red)
    return source_name + action + suffix


def chinese_move_notation(fen: str, iccs: str) -> str:
    """Convert one ICCS move to standard red/black Chinese Xiangqi notation."""
    return _format_move(_parse_board(fen), iccs)


def chinese_principal_variation(fen: str, moves: Iterable[str]) -> list[str]:
    """Format a PV while applying each move to the temporary board in sequence."""
    board = _parse_board(fen)
    result: list[str] = []
    for iccs in moves:
        result.append(_format_move(board, iccs))
        source = _square(iccs[:2].lower())
        target = _square(iccs[2:4].lower())
        board[target] = board.pop(source)
    return result
