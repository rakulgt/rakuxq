"""Xiangqi analysis engine adapters."""

from .base import (
    AnalysisEngine,
    AnalysisResult,
    EngineAnalysisError,
    EngineIdentity,
    EngineMove,
    EngineNotConfigured,
    EngineScore,
    EngineTimeout,
    InvalidEnginePosition,
    analysis_to_dict,
    normalize_engine_fen,
)
from .pikafish import PikafishEngine
from .pool import PikafishPool

__all__ = [
    "AnalysisEngine",
    "AnalysisResult",
    "EngineAnalysisError",
    "EngineIdentity",
    "EngineMove",
    "EngineNotConfigured",
    "EngineScore",
    "EngineTimeout",
    "InvalidEnginePosition",
    "PikafishEngine",
    "PikafishPool",
    "analysis_to_dict",
    "normalize_engine_fen",
]
