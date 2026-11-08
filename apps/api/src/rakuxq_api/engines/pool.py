"""Bounded leases of independent UCI processes, never shared position streams.

Original RakuXQ orchestration, Li Guotai, MIT, 2026-11-08.
Inputs/outputs are the unchanged AnalysisEngine contract. This does not implement
or replace NNUE/search, cache old answers, or grant additional engine permissions.
"""
from __future__ import annotations

import queue
import threading
from typing import Any

from .base import AnalysisResult, EngineAnalysisError, EngineIdentity
from .pikafish import PikafishEngine


class PikafishPool:
    """At most two one-request leases, each held across BOTH search stages."""

    def __init__(self, executable: str, network: str, *, workers: int = 1, **options: Any):
        if workers not in {1, 2}:
            raise ValueError("engine workers must be 1 or 2")
        self._engines = [PikafishEngine(executable, network, **options) for _ in range(workers)]
        # Reuse the most recently idle process for serial play, preserving its
        # warm transposition table instead of needlessly alternating workers.
        self._available: queue.Queue[PikafishEngine] = queue.LifoQueue()
        for engine in self._engines:
            self._available.put(engine)
        self._lifecycle_lock = threading.Lock()
        self._closing = False

    @property
    def configured(self) -> bool:
        return all(engine.configured for engine in self._engines)

    @property
    def ready(self) -> bool:
        return not self._closing and all(engine.ready for engine in self._engines)

    @property
    def identity(self) -> EngineIdentity | None:
        return next((engine.identity for engine in self._engines if engine.identity), None)

    def start(self) -> None:
        with self._lifecycle_lock:
            leases = [self._available.get() for _ in self._engines]
            try:
                for engine in leases:
                    engine.start()
                self._closing = False
            except Exception:
                for engine in leases:
                    engine.close()
                raise
            finally:
                for engine in leases:
                    self._available.put(engine)

    def close(self) -> None:
        with self._lifecycle_lock:
            self._closing = True
            # Existing work finishes before shutdown. Pending/new work must not
            # resurrect a process after close(); analyze checks again on lease.
            leases = [self._available.get() for _ in self._engines]
            try:
                for engine in leases:
                    engine.close()
            finally:
                for engine in leases:
                    self._available.put(engine)

    def analyze(self, fen: str, movetime_ms: int, max_candidates: int = 1) -> AnalysisResult:
        if self._closing:
            raise EngineAnalysisError("Engine pool is shutting down")
        engine = self._available.get()
        try:
            if self._closing:
                raise EngineAnalysisError("Engine pool is shutting down")
            return engine.analyze(fen, movetime_ms, max_candidates)
        finally:
            self._available.put(engine)
