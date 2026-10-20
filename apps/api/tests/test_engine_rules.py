import pytest

from rakuxq_api.engines.base import (
    EngineAnalysisError,
    EngineIdentity,
    InvalidEnginePosition,
    analysis_to_dict,
    normalize_engine_fen,
)
from rakuxq_api.engines.pikafish import PikafishEngine
from rakuxq_api.engines.rules import grid_from_fen, in_check, inspect_position

START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"
EVASION = "5k3/9/9/9/9/9/4r4/9/9/4K4 w"
MATE = "4k4/3RR4/9/9/9/9/9/9/9/5K3 b"
STALEMATE = "4k4/3R1R3/9/9/9/9/9/9/9/3K5 b"


def test_check_evasion_remains_analyzable_even_with_only_one_move():
    assert normalize_engine_fen(EVASION).startswith(EVASION)
    state, moves = inspect_position(EVASION)
    assert state.in_check
    assert state.terminal_reason is None
    assert moves == ["e0d0"]


def test_wrong_mover_is_rejected_before_starting_the_engine():
    engine = PikafishEngine("", "")
    with pytest.raises(InvalidEnginePosition) as caught:
        engine.analyze(EVASION.replace(" w", " b"), 3000)
    assert caught.value.code == "SIDE_TO_MOVE_CONFLICT"
    assert engine._process is None


def test_a_winning_forced_mate_position_still_has_moves():
    fen = "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w"
    state, moves = inspect_position(normalize_engine_fen(fen))
    assert state.terminal_reason is None
    assert "e6e8" in moves


@pytest.mark.parametrize(
    "fen,reason,display",
    [(MATE, "checkmate", "黑方已将死，红方获胜。"),
     (STALEMATE, "stalemate", "黑方无合法着法（困毙），红方获胜。")],
)
def test_terminal_positions_return_explicit_results_without_a_search(fen, reason, display):
    engine = PikafishEngine("", "")
    result = engine.analyze(fen, 3000)
    assert result.status == "terminal"
    assert result.best_move is None
    assert result.position.terminal_reason == reason
    assert result.position.winner == "red"
    assert analysis_to_dict(result)["display_text"] == display
    assert engine._process is None


def test_start_position_has_44_legal_moves():
    state, moves = inspect_position(START)
    assert not state.in_check
    assert len(set(moves)) == state.legal_move_count == 44


class ScriptedEngine(PikafishEngine):
    def __init__(self, lines):
        super().__init__("", "")
        self.lines = lines
        self.commands = []
        self._identity = EngineIdentity("test", None, "test", None)

    @property
    def ready(self):
        return True

    def _send(self, command):
        self.commands.append(command)

    def _read_until(self, target, timeout_ms):
        return self.lines


def test_engine_returns_the_only_legal_evasion_instead_of_a_terminal_result():
    engine = ScriptedEngine([
        "info depth 12 score mate -8 nodes 100 time 10 pv e0d0", "bestmove e0d0",
    ])
    result = engine.analyze(EVASION, 50)
    assert result.best_move.iccs == "e0d0"
    assert result.status == "completed"
    assert result.position.in_check
    assert analysis_to_dict(result)["display_text"] == "帅五平六 黑方 KO(8)"
    assert engine.commands[0] == "setoption name MultiPV value 1"
    assert len(engine.commands) == 3
    assert len(result.recommendations) == 1
    assert result.alternative_omitted_reason == "only_legal_move"


@pytest.mark.parametrize("bestmove", ["(none)", "0000", "e0e1"])
def test_missing_or_illegal_move_is_not_reported_as_success_or_game_over(bestmove):
    engine = ScriptedEngine([f"bestmove {bestmove}"])
    with pytest.raises(EngineAnalysisError, match="仍有合法着法"):
        engine.analyze(EVASION, 50)


@pytest.mark.parametrize(
    "piece,source,target,blocker,blocked",
    [
        ("r", (3, 4), (9, 4), None, True),
        ("r", (3, 4), (9, 4), (6, 4), False),
        ("c", (3, 4), (9, 4), None, False),
        ("c", (3, 4), (9, 4), (6, 4), True),
        ("n", (7, 3), (9, 4), None, True),
        ("n", (7, 3), (9, 4), (8, 3), False),
        ("n", (8, 2), (9, 4), (8, 3), False),
        ("p", (8, 4), (9, 4), None, True),
        ("p", (9, 3), (9, 4), None, True),
    ],
)
def test_attack_checks_respect_screens_horse_legs_and_pawn_direction(
    piece, source, target, blocker, blocked,
):
    grid = grid_from_fen("5k3/9/9/9/9/9/9/9/9/4K4 w")
    grid[target[0]][target[1]] = "K"
    grid[source[0]][source[1]] = piece
    if blocker:
        grid[blocker[0]][blocker[1]] = "P"
    assert in_check(grid, True) is blocked
