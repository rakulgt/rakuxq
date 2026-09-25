import unittest

from rakuxq_api.semantic import (
    correct_crossed_king_camps,
    swap_piece_camps,
)

LEGAL_GRID = [
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

GOLD_DISC_SKIN_FAILURE_GRID = [
    list("..n......"),
    list("......c.."),
    list("....Kc..r"),
    list(".pp......"),
    list(".pp......"),
    list(".Cp......"),
    list("........."),
    list("R....k..b"),
    list(".C..an..."),
    list(".r.a..b.."),
]


class SemanticCorrectionTests(unittest.TestCase):
    def test_swap_piece_camps_preserves_coordinates_and_empty_cells(self):
        swapped = swap_piece_camps(LEGAL_GRID)

        self.assertEqual(swapped[0], list("RNBAKABNR"))
        self.assertEqual(swapped[1], list("........."))
        self.assertEqual(swapped[9], list("rnbakabnr"))

    def test_crossed_kings_trigger_auditable_global_swap(self):
        inverted = swap_piece_camps(LEGAL_GRID)

        corrected, correction = correct_crossed_king_camps(inverted)

        self.assertEqual(corrected, LEGAL_GRID)
        self.assertIsNotNone(correction)
        self.assertEqual(correction.kind, "global_camp_swap")
        self.assertEqual(correction.after_blocking, ())

    def test_legal_grid_is_never_changed(self):
        corrected, correction = correct_crossed_king_camps(LEGAL_GRID)

        self.assertEqual(corrected, LEGAL_GRID)
        self.assertIsNone(correction)

    def test_missing_king_is_not_enough_evidence(self):
        grid = [row.copy() for row in LEGAL_GRID]
        grid[9][4] = "."
        grid[2][4] = "K"

        corrected, correction = correct_crossed_king_camps(grid)

        self.assertEqual(corrected, grid)
        self.assertIsNone(correction)

    def test_real_gold_disc_skin_failure_is_corrected(self):
        corrected, correction = correct_crossed_king_camps(
            GOLD_DISC_SKIN_FAILURE_GRID
        )

        self.assertIsNotNone(correction)
        self.assertEqual(corrected[2][4], "k")
        self.assertEqual(corrected[7][5], "K")
        self.assertEqual(correction.after_blocking, ())


if __name__ == "__main__":
    unittest.main()
