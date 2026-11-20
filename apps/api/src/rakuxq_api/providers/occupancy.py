"""Image-local occupancy evidence for a weak empty candidate.

Input: rectified RGB board and raw layout candidates; output: auditable distances
and an empty/occupied/uncertain vote, never changed labels. Original Raku code,
MIT; no external model, training collection, network call or cross-request state.
"""
from __future__ import annotations

import time
from typing import Any


class LocalOccupancyProbe:
    """Compare off-centre appearance against reliable cells in this image only."""

    def __init__(self, warped: Any, symbols: list[str], confidences: Any, visible: list[bool]):
        self.warped = warped
        self.symbols = symbols
        self.confidences = confidences
        self.visible = visible
        self._hsv: Any = None
        self._mask: Any = None
        self._features: dict[int, Any] = {}

    def _feature(self, index: int) -> Any:
        import cv2
        import numpy as np

        if index not in self._features:
            if self._hsv is None:
                self._hsv = cv2.cvtColor(self.warped, cv2.COLOR_RGB2HSV)
                y, x = np.ogrid[-18:19, -18:19]
                self._mask = (((x*x + y*y) >= 81) & ((x*x + y*y) <= 256)).astype(
                    np.uint8
                ) * 255
            rank, file = divmod(index, 9)
            patch = cv2.getRectSubPix(
                self._hsv, (37, 37), (50.0 + file*43.75, 50.0 + rank*400.0/9.0),
            )
            histogram = cv2.calcHist(
                [patch], [0, 1, 2], self._mask, [12, 4, 4], [0, 180, 0, 256, 0, 256],
            )
            self._features[index] = cv2.normalize(histogram, histogram).flatten()
        return self._features[index]

    def _distance(self, index: int, references: list[int]) -> float:
        import cv2

        distances = sorted(
            float(cv2.compareHist(self._feature(index), self._feature(other),
                                  cv2.HISTCMP_BHATTACHARYYA))
            for other in references if other != index
        )[:3]
        return sum(distances) / len(distances)

    def check_empty(self, index: int) -> dict[str, object]:
        started = time.perf_counter()
        result: dict[str, object] = {
            "method": "same_image_annular_occupancy_v1", "vote": "uncertain",
            "confirmed_empty": False, "rank": index // 9, "file": index % 9,
            "maximum_empty_distance": 0.45, "minimum_distance_margin": 0.15,
            "centre_exclusion_radius": 9, "outer_radius": 16,
        }
        if not 0 <= index < 90 or self.symbols[index] != "." or not all(self.visible):
            return {**result, "reason": "not_a_full_board_empty_candidate"}
        empty = [i for i, symbol in enumerate(self.symbols)
                 if i != index and symbol == "." and float(self.confidences[i]) >= 0.80]
        pieces = [i for i, symbol in enumerate(self.symbols)
                  if symbol not in {".", "x"} and float(self.confidences[i]) >= 0.90]
        result.update(empty_reference_count=len(empty), piece_reference_count=len(pieces))
        if len(empty) < 3 or len(pieces) < 2:
            return {**result, "reason": "insufficient_image_local_references"}

        # If this palette already confuses a known piece with the empty board,
        # it cannot independently support deleting occupancy at another square.
        piece_control_errors = sum(
            self._distance(i, empty) <= self._distance(i, pieces) for i in pieces
        )
        result["piece_control_errors"] = piece_control_errors
        if piece_control_errors:
            return {**result, "reason": "piece_and_board_appearance_not_separable",
                    "elapsed_ms": round((time.perf_counter()-started)*1000, 3)}
        empty_distance = self._distance(index, empty)
        piece_distance = self._distance(index, pieces)
        margin = piece_distance - empty_distance
        confirmed = empty_distance <= 0.45 and margin >= 0.15
        result.update(
            distance_to_empty=empty_distance, distance_to_piece=piece_distance,
            distance_margin=margin, confirmed_empty=confirmed,
            vote="empty" if confirmed else ("occupied" if margin <= -0.15 else "uncertain"),
            reason="background_supported" if confirmed else "empty_not_independently_supported",
            elapsed_ms=round((time.perf_counter()-started)*1000, 3),
        )
        return result
