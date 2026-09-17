from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import BoardPrediction, Orientation


class ProviderNotReady(RuntimeError):
    pass


class RecognitionFailed(RuntimeError):
    pass


class RecognitionProvider(ABC):
    name: str

    @abstractmethod
    def ready(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def recognize(self, image: bytes, orientation: Orientation) -> BoardPrediction:
        raise NotImplementedError

