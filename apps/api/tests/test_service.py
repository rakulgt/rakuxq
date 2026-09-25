import unittest

from rakuxq_api.domain import (
    BoardPrediction,
    CellPrediction,
    Orientation,
    RecognitionStatus,
    SideToMove,
)
from rakuxq_api.providers.base import RecognitionProvider
from rakuxq_api.service import RecognitionService

START_GRID = [
    list("rnbakabnr"),
    list("........."),
    list(".c.....c."),
    list("p.p.p.p.p"),
    list("........."),
    list("........."),
    list("P.P.P.P.P"),
    list(".C.....C."),
    list("........."),
    list("RNBAKABNR"),
]


class FixedProvider(RecognitionProvider):
    name = "fixed-test"

    def __init__(self, confidence=0.999):
        self.confidence = confidence

    def ready(self):
        return True

    def recognize(self, image, orientation):
        cells = [
            CellPrediction(rank, file, symbol, self.confidence)
            for rank, row in enumerate(START_GRID)
            for file, symbol in enumerate(row)
        ]
        return BoardPrediction(
            grid=[row.copy() for row in START_GRID],
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=self.confidence,
            provider=self.name,
            model_version="test",
        )


class PartialProvider(RecognitionProvider):
    name = "partial-test"

    def ready(self):
        return True

    def recognize(self, image, orientation):
        cells = []
        for rank, row in enumerate(START_GRID):
            for file, symbol in enumerate(row):
                assumed = (rank, file) == (1, 0)
                confidence = 0.1 if assumed else (0.8 if symbol == "." else 0.999)
                cells.append(
                    CellPrediction(
                        rank,
                        file,
                        "." if assumed else symbol,
                        confidence,
                        visible=not assumed,
                        assumed_empty=assumed,
                        raw_symbol="x" if assumed else symbol,
                    )
                )
        return BoardPrediction(
            grid=[row.copy() for row in START_GRID],
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=0.4,
            provider=self.name,
            model_version="test",
        )


class PartialProviderWithVisibleUnknown(PartialProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.grid[1][1] = "x"
        prediction.cells[10] = CellPrediction(
            rank=1,
            file=1,
            symbol="x",
            confidence=0.3,
            visible=True,
            assumed_empty=False,
            raw_symbol="x",
        )
        return prediction


class LowConfidenceEmptyProvider(FixedProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.cells[10] = CellPrediction(
            rank=1,
            file=1,
            symbol=".",
            confidence=0.4,
            visible=True,
            assumed_empty=False,
            raw_symbol=".",
        )
        return prediction


class LowConfidencePieceProvider(FixedProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.cells[54] = CellPrediction(
            rank=6,
            file=0,
            symbol="P",
            confidence=0.7,
            visible=True,
            assumed_empty=False,
            raw_symbol="P",
        )
        return prediction


class PartialLowConfidenceEmptyProvider(PartialProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.cells[10] = CellPrediction(
            rank=1,
            file=1,
            symbol=".",
            confidence=0.4,
            visible=True,
            assumed_empty=False,
            raw_symbol=".",
        )
        return prediction


class RefinedPieceProvider(FixedProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.grid[0][0] = "r"
        prediction.cells[0] = CellPrediction(
            rank=0,
            file=0,
            symbol="r",
            confidence=0.8,
            raw_symbol="b",
            refinement="same_image_prototype",
            raw_confidence=0.6,
        )
        return prediction


class CampReversedProvider(FixedProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.grid = [
            [symbol.swapcase() if symbol.isalpha() else symbol for symbol in row]
            for row in prediction.grid
        ]
        prediction.cells = [
            CellPrediction(
                cell.rank,
                cell.file,
                cell.symbol.swapcase() if cell.symbol.isalpha() else cell.symbol,
                cell.confidence,
            )
            for cell in prediction.cells
        ]
        return prediction


class OneKingOutsideProvider(FixedProvider):
    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.grid[9][4] = "."
        prediction.grid[2][4] = "K"
        prediction.cells[85] = CellPrediction(9, 4, ".", self.confidence)
        prediction.cells[22] = CellPrediction(2, 4, "K", self.confidence)
        return prediction


class ServiceTests(unittest.TestCase):
    def test_high_confidence_complete_position_is_accepted(self):
        result = RecognitionService(FixedProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )
        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertTrue(result.fen.endswith(" w"))
        self.assertTrue(result.full_fen.endswith(" w - - 0 1"))

    def test_unknown_side_requires_review(self):
        result = RecognitionService(FixedProvider()).recognize(
            b"image", SideToMove.UNKNOWN, Orientation.AUTO
        )
        self.assertEqual(result.status, RecognitionStatus.REVIEW_REQUIRED)
        self.assertIsNone(result.fen)
        self.assertIn("SIDE_TO_MOVE_UNKNOWN", result.warnings)

    def test_low_confidence_is_not_auto_accepted(self):
        result = RecognitionService(
            FixedProvider(confidence=0.80), acceptance_confidence=0.985
        ).recognize(
            b"image", SideToMove.BLACK, Orientation.AUTO
        )
        self.assertEqual(result.status, RecognitionStatus.REVIEW_REQUIRED)
        self.assertIn("BELOW_AUTO_ACCEPT_THRESHOLD", result.warnings)

    def test_unseen_cells_are_assumed_empty_without_lowering_visual_confidence(self):
        result = RecognitionService(PartialProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertIn("UNSEEN_CELLS_ASSUMED_EMPTY", result.warnings)
        self.assertEqual(result.confidence, 0.4)
        self.assertEqual(
            [(cell.rank, cell.file) for cell in result.assumed_empty_cells],
            [(1, 0)],
        )

    def test_assumed_empty_coordinates_follow_orientation_normalization(self):
        result = RecognitionService(PartialProvider()).recognize(
            b"image", SideToMove.RED, Orientation.BLACK_BOTTOM
        )

        self.assertEqual(
            [(cell.rank, cell.file) for cell in result.assumed_empty_cells],
            [(8, 8)],
        )

    def test_visible_unknown_is_assumed_empty_and_keeps_raw_prediction(self):
        result = RecognitionService(PartialProviderWithVisibleUnknown()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertIsNotNone(result.fen)
        self.assertEqual(result.grid[1][1], ".")
        self.assertEqual(result.prediction.grid[1][1], "x")
        self.assertIn("UNCERTAIN_CELLS_ASSUMED_EMPTY", result.warnings)
        self.assertIn(
            (1, 1, "visually_uncertain"),
            [
                (cell.rank, cell.file, cell.reason)
                for cell in result.assumed_empty_cells
            ],
        )

    def test_low_confidence_empty_requires_review_without_becoming_assumed(self):
        result = RecognitionService(LowConfidenceEmptyProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.REVIEW_REQUIRED)
        self.assertNotIn("UNCERTAIN_CELLS_ASSUMED_EMPTY", result.warnings)
        self.assertEqual(result.assumed_empty_cells, [])
        self.assertIn("LOW_CELL_CONFIDENCE", result.warnings)

    def test_low_confidence_piece_is_preserved_and_requires_review(self):
        result = RecognitionService(LowConfidencePieceProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.REVIEW_REQUIRED)
        self.assertEqual(result.grid[6][0], "P")
        self.assertEqual(result.prediction.grid[6][0], "P")
        self.assertNotIn("UNCERTAIN_CELLS_ASSUMED_EMPTY", result.warnings)
        self.assertEqual(result.assumed_empty_cells, [])
        self.assertIn("LOW_CELL_CONFIDENCE", result.warnings)

    def test_partial_board_uses_relaxed_empty_threshold(self):
        result = RecognitionService(PartialLowConfidenceEmptyProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertNotIn("LOW_CELL_CONFIDENCE", result.warnings)
        self.assertIn("PARTIAL_EMPTY_CONFIDENCE_RELAXED", result.warnings)

    def test_same_image_refinement_is_disclosed(self):
        result = RecognitionService(RefinedPieceProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertIn("SAME_IMAGE_PROTOTYPE_REFINEMENT", result.warnings)

    def test_decisive_whole_board_camp_inversion_is_corrected(self):
        result = RecognitionService(CampReversedProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.ACCEPTED)
        self.assertEqual(result.grid, START_GRID)
        self.assertNotEqual(result.prediction.grid, result.grid)
        self.assertIn("SEMANTIC_CAMP_INVERSION_CORRECTED", result.warnings)
        self.assertEqual(
            result.prediction.metadata["semantic_corrections"][0]["kind"],
            "global_camp_swap",
        )
        self.assertIn(
            "RED_KING_OUTSIDE_PALACE",
            result.prediction.metadata["semantic_corrections"][0]["before_blocking"],
        )
        self.assertEqual(
            result.prediction.metadata["semantic_corrections"][0]["after_blocking"],
            [],
        )

    def test_single_outside_king_does_not_trigger_global_camp_swap(self):
        result = RecognitionService(OneKingOutsideProvider()).recognize(
            b"image", SideToMove.RED, Orientation.AUTO
        )

        self.assertEqual(result.status, RecognitionStatus.REVIEW_REQUIRED)
        self.assertNotIn("SEMANTIC_CAMP_INVERSION_CORRECTED", result.warnings)
        self.assertNotIn("semantic_corrections", result.prediction.metadata)


if __name__ == "__main__":
    unittest.main()
