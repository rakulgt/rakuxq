from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

from ..validation import validate_position


class EngineAnalysisError(RuntimeError):
    """The configured engine could not complete an analysis."""


class EngineNotConfigured(EngineAnalysisError):
    """No runnable engine binary and network are configured."""


class EngineTimeout(EngineAnalysisError):
    """The engine did not return a best move within the allowed time."""


class InvalidEnginePosition(ValueError):
    """The supplied Xiangqi FEN is not safe to send to a strict engine."""


@dataclass(frozen=True, slots=True)
class EngineMove:
    iccs: str
    from_square: str
    to_square: str


@dataclass(frozen=True, slots=True)
class EngineScore:
    type: str
    value: int
    perspective: str = "red"
    display: str = "0"
    bound: str | None = None


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    name: str
    author: str | None
    version: str
    network_sha256: str | None


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    status: str
    fen: str
    best_move: EngineMove | None
    ponder: str | None
    score: EngineScore | None
    depth: int
    seldepth: int | None
    nodes: int | None
    time_ms: int
    nps: int | None
    pv: list[str] = field(default_factory=list)
    engine: EngineIdentity | None = None


class AnalysisEngine(Protocol):
    @property
    def configured(self) -> bool: ...

    @property
    def ready(self) -> bool: ...

    def start(self) -> None: ...

    def close(self) -> None: ...

    def analyze(self, fen: str, movetime_ms: int) -> AnalysisResult: ...


def analysis_to_dict(result: AnalysisResult) -> dict[str, object]:
    """Serialize the public contract while keeping Python-safe internal field names."""
    payload = asdict(result)
    move = payload.get("best_move")
    if isinstance(move, dict):
        move["from"] = move.pop("from_square")
        move["to"] = move.pop("to_square")
    return payload


_PIECES = frozenset("KABNRCPkabnrcp")


def normalize_engine_fen(fen: str) -> str:
    """Validate a Xiangqi FEN and normalize it to Pikafish's six fields."""
    fields = fen.strip().split()
    if len(fields) == 2:
        fields.extend(["-", "-", "0", "1"])
    if len(fields) != 6:
        raise InvalidEnginePosition("fen must contain 2 or 6 fields")

    placement, active, castling, en_passant, halfmove, fullmove = fields
    if active not in {"w", "b"}:
        raise InvalidEnginePosition("active color must be w (red) or b (black)")
    if castling != "-" or en_passant != "-":
        raise InvalidEnginePosition("Xiangqi FEN castling and en-passant fields must be '-'")
    try:
        halfmove_number = int(halfmove)
        fullmove_number = int(fullmove)
    except ValueError as exc:
        raise InvalidEnginePosition("FEN move counters must be integers") from exc
    if halfmove_number < 0 or fullmove_number < 1:
        raise InvalidEnginePosition("FEN move counters are outside their valid ranges")

    ranks = placement.split("/")
    if len(ranks) != 10:
        raise InvalidEnginePosition("Xiangqi FEN must contain exactly 10 ranks")

    red_kings = 0
    black_kings = 0
    grid: list[list[str]] = []
    for rank_index, rank in enumerate(ranks):
        files = 0
        row: list[str] = []
        for symbol in rank:
            if symbol.isdigit():
                if symbol == "0":
                    raise InvalidEnginePosition("empty runs must be between 1 and 9")
                files += int(symbol)
                row.extend("." for _ in range(int(symbol)))
            elif symbol in _PIECES:
                files += 1
                row.append(symbol)
                red_kings += symbol == "K"
                black_kings += symbol == "k"
            else:
                raise InvalidEnginePosition(
                    f"rank {rank_index} contains unsupported symbol {symbol!r}"
                )
        if files != 9:
            raise InvalidEnginePosition(
                f"rank {rank_index} expands to {files} files instead of 9"
            )
        grid.append(row)
    if red_kings != 1 or black_kings != 1:
        raise InvalidEnginePosition("engine analysis requires exactly one red and one black king")

    blocking_warnings = [
        warning.code for warning in validate_position(grid) if warning.blocking
    ]
    if blocking_warnings:
        raise InvalidEnginePosition(
            "position failed Xiangqi validation: " + ", ".join(blocking_warnings)
        )

    return " ".join(fields)


def score_from_side_to_move(
    score_type: str,
    raw_value: int,
    active_color: str,
    bound: str | None = None,
) -> EngineScore:
    """Convert a UCI side-to-move score into RakuXQ's fixed red perspective."""
    if score_type not in {"cp", "mate"}:
        raise EngineAnalysisError(f"unsupported engine score type: {score_type}")
    value = raw_value if active_color == "w" else -raw_value
    if score_type == "mate":
        sign = "+" if value > 0 else ""
        display = f"KO({sign}{value})"
    elif value > 0:
        display = f"+{value}"
    else:
        display = str(value)
    return EngineScore(
        type=score_type,
        value=value,
        perspective="red",
        display=display,
        bound=bound,
    )
