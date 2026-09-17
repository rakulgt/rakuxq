import unittest

from rakuxq_api.validation import validate_position

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


class ValidationTests(unittest.TestCase):
    def test_start_position_has_no_warnings(self):
        self.assertEqual(validate_position(LEGAL_GRID), [])

    def test_missing_red_king_blocks(self):
        grid = [row.copy() for row in LEGAL_GRID]
        grid[9][4] = "."
        warnings = validate_position(grid)
        self.assertIn("RED_KING_COUNT", [warning.code for warning in warnings])
        self.assertTrue(all(warning.blocking for warning in warnings))

    def test_facing_kings_blocks(self):
        grid = [list(".........") for _ in range(10)]
        grid[0][4] = "k"
        grid[9][4] = "K"
        warnings = validate_position(grid)
        self.assertIn("KINGS_FACE_EACH_OTHER", [warning.code for warning in warnings])

    def test_advisor_on_non_diagonal_palace_square_blocks(self):
        grid = [row.copy() for row in LEGAL_GRID]
        grid[9][3] = "."
        grid[9][4] = "A"
        warnings = validate_position(grid)
        self.assertIn("RED_ADVISOR_OUTSIDE_PALACE", [warning.code for warning in warnings])

    def test_elephant_on_unreachable_square_blocks(self):
        grid = [row.copy() for row in LEGAL_GRID]
        grid[9][2] = "."
        grid[8][2] = "B"
        warnings = validate_position(grid)
        self.assertIn("RED_ELEPHANT_ILLEGAL_SQUARE", [warning.code for warning in warnings])


if __name__ == "__main__":
    unittest.main()
