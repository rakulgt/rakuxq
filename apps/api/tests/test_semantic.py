import unittest

from rakuxq_api.domain import Orientation
from rakuxq_api.semantic import (
    infer_orientation_from_kings,
    rotate_grid_180,
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

REAL_FAILURE_GRID = [
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


class SemanticOrientationTests(unittest.TestCase):
    def test_rotate_preserves_piece_identity_and_changes_coordinates(self):
        rotated = rotate_grid_180(LEGAL_GRID)

        self.assertEqual(rotated[0], list("RNBAKABNR"))
        self.assertEqual(rotated[1], list("........."))
        self.assertEqual(rotated[9], list("rnbakabnr"))
        self.assertEqual(sum(row.count("K") for row in rotated), 1)
        self.assertEqual(sum(row.count("k") for row in rotated), 1)

    def test_crossed_kings_infer_black_bottom_orientation(self):
        black_bottom = rotate_grid_180(LEGAL_GRID)

        decision = infer_orientation_from_kings(black_bottom)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.orientation, Orientation.BLACK_BOTTOM)
        self.assertEqual(decision.kind, "rotate_180")
        self.assertEqual(decision.after_blocking, ())

    def test_legal_red_bottom_grid_needs_no_orientation_change(self):
        self.assertIsNone(infer_orientation_from_kings(LEGAL_GRID))

    def test_missing_king_is_not_enough_evidence(self):
        grid = [row.copy() for row in LEGAL_GRID]
        grid[9][4] = "."
        grid[2][4] = "K"

        self.assertIsNone(infer_orientation_from_kings(grid))

    def test_real_failure_rotates_without_turning_shuai_into_jiang(self):
        decision = infer_orientation_from_kings(REAL_FAILURE_GRID)
        corrected = rotate_grid_180(REAL_FAILURE_GRID)

        self.assertIsNotNone(decision)
        self.assertEqual(corrected[7][4], "K")
        self.assertEqual(corrected[2][3], "k")
        self.assertEqual(decision.after_blocking, ())


if __name__ == "__main__":
    unittest.main()
