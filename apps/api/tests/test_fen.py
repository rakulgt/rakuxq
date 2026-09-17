import unittest

from rakuxq_api.domain import Orientation, SideToMove
from rakuxq_api.fen import FenError, normalize_orientation, to_fen, to_piece_placement

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


class FenTests(unittest.TestCase):
    def test_start_position(self):
        placement = to_piece_placement(START_GRID)
        self.assertEqual(
            placement,
            "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR",
        )
        self.assertEqual(
            to_fen(placement, SideToMove.RED),
            placement + " w - - 0 1",
        )

    def test_unknown_cell_is_not_serialized(self):
        grid = [row.copy() for row in START_GRID]
        grid[4][4] = "x"
        with self.assertRaises(FenError):
            to_piece_placement(grid)

    def test_black_bottom_rotates_to_canonical(self):
        rotated = [list(reversed(row)) for row in reversed(START_GRID)]
        self.assertEqual(
            normalize_orientation(rotated, Orientation.BLACK_BOTTOM), START_GRID
        )

    def test_side_is_required_for_complete_fen(self):
        with self.assertRaises(FenError):
            to_fen(to_piece_placement(START_GRID), SideToMove.UNKNOWN)


if __name__ == "__main__":
    unittest.main()

