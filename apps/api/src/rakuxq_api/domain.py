from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SideToMove(StrEnum):
    RED = "red"
    BLACK = "black"
    UNKNOWN = "unknown"


class Orientation(StrEnum):
    AUTO = "auto"
    RED_BOTTOM = "red_bottom"
    BLACK_BOTTOM = "black_bottom"


class RecognitionStatus(StrEnum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CellPrediction:
    rank: int
    file: int
    symbol: str
    confidence: float
    visible: bool = True
    assumed_empty: bool = False
    raw_symbol: str | None = None
    refinement: str | None = None
    raw_confidence: float | None = None


@dataclass(frozen=True, slots=True)
class BoardCell:
    rank: int
    file: int
    reason: str = "out_of_frame"


@dataclass(slots=True)
class BoardPrediction:
    grid: list[list[str]]
    cells: list[CellPrediction]
    orientation: Orientation
    board_confidence: float
    provider: str
    model_version: str
    corners: list[list[float]] = field(default_factory=list)
    elapsed_ms: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RecognitionResult:
    request_id: str
    status: RecognitionStatus
    grid: list[list[str]]
    piece_placement: str | None
    fen: str | None
    side_to_move: SideToMove
    orientation: Orientation
    confidence: float
    warnings: list[str]
    prediction: BoardPrediction | None
    assumed_empty_cells: list[BoardCell] = field(default_factory=list)
