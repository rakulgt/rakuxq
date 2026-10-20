import pytest
from test_engine_rules import START, ScriptedEngine

from rakuxq_api.engines.base import analysis_to_dict
from rakuxq_api.engines.pikafish import alternative_omission_reason, parse_uci_info


def info(rank, score="cp 40", *, depth=12, move=None):
    move = move or ("h2e2" if rank == 1 else "b2e2")
    return f"info depth {depth} multipv {rank} score {score} time 100 pv {move}"


def analyze(lines, fen=START):
    engine = ScriptedEngine(lines + ["bestmove h2e2"])
    result = engine._analyze_once(fen, 3000, candidate_count=2)
    assert engine.commands[0] == "setoption name MultiPV value 2"
    assert engine.commands[-1] == "go movetime 3000"
    assert sum(c.startswith("go ") for c in engine.commands) == 1
    return result


@pytest.mark.parametrize("active", ["w", "b"])
def test_two_sibling_moves_share_budget_and_fixed_red_score_perspective(active):
    first, second = ("h2e2", "b2e2") if active == "w" else ("h7e7", "b7e7")
    engine = ScriptedEngine([
        info(1, "cp 100", move=first), info(2, "cp 20", move=second),
        f"bestmove {first}",
    ])
    result = engine._analyze_once(START.replace(" w", f" {active}"), 3000, candidate_count=2)
    assert len(result.recommendations) == 2
    assert result.alternative_omitted_reason is None
    assert [r.score.value for r in result.recommendations] == (
        [100, 20] if active == "w" else [-100, -20]
    )
    assert result.best_move == result.recommendations[0].move
    payload = analysis_to_dict(result)
    assert payload["recommendations"][1]["move"]["from"] == second[:2]
    assert "from_square" not in payload["recommendations"][1]["move"]
    assert payload["display_text"].startswith("首选：")
    assert "；备选：" in payload["display_text"]


@pytest.mark.parametrize(
    "first,second,reason",
    [
        ("cp 200", "cp 50", None),
        ("cp 200", "cp 49", "score_gap"),
        ("cp -300", "cp -600", "score_gap"),
        ("mate 2", "cp 800", "mate_outcome"),
        ("cp -100", "mate -3", "mate_outcome"),
        ("mate 2", "mate -2", "mate_outcome"),
        ("mate 2", "mate 5", None),
        ("mate -8", "mate -2", "mate_outcome"),
        ("cp 100 lowerbound", "cp 0", "insufficient_search"),
        ("cp 100", "cp 150", "score_gap"),
    ],
)
def test_alternative_quality_policy(first, second, reason):
    assert alternative_omission_reason(
        parse_uci_info(info(1, first)), parse_uci_info(info(2, second)), 150,
    ) == reason


def test_bad_alternative_is_not_shown_but_best_move_remains():
    result = analyze([info(1, "cp 600"), info(2, "cp -100")])
    assert len(result.recommendations) == 1
    assert result.best_move.iccs == "h2e2"
    assert result.alternative_omitted_reason == "score_gap"
    assert analysis_to_dict(result)["display_text"] == "炮二平五 红优 600"


def test_incomplete_iteration_uses_a_complete_pair_at_same_depth():
    result = analyze([
        info(1, "cp 80"), info(2, "cp 70"), info(1, "cp 200", depth=13),
    ])
    assert len(result.recommendations) == 2
    assert [r.depth for r in result.recommendations] == [12, 12]
    assert result.score.value == 80


@pytest.mark.parametrize("second", [
    info(2, depth=11), info(2, move="h2e2"), info(2, move="a0a9"),
    info(2, "cp 40 upperbound"),
])
def test_missing_duplicate_illegal_or_bound_candidates_are_not_fabricated(second):
    result = analyze([info(1), second])
    assert len(result.recommendations) == 1
    assert result.alternative_omitted_reason == "insufficient_search"


def test_stale_score_never_attaches_to_changed_bestmove():
    result = analyze([
        info(1, "cp 200", move="b2e2"), info(2, "cp 180", move="h2e2"),
    ])
    assert result.best_move.iccs == "h2e2"
    assert result.score is None
    assert len(result.recommendations) == 1


def test_interrupted_trial_root_can_use_a_completed_pair_matching_actual_bestmove():
    result = analyze([
        info(1), info(2), info(1, depth=13, move="b2e2"),
    ])
    assert len(result.recommendations) == 2
    assert result.depth == 12
    assert all(r.depth == 12 for r in result.recommendations)


def test_completed_pair_must_not_be_much_shallower_than_the_primary_search():
    result = analyze([info(1), info(2), info(1, depth=16)])
    assert len(result.recommendations) == 1
    assert result.depth == 16


def test_forced_single_search_does_not_leak_multipv_into_the_next_search():
    from test_engine_rules import EVASION

    engine = ScriptedEngine(["info depth 2 score cp 0 pv e0d0", "bestmove e0d0"])
    engine.analyze(EVASION, 50)
    engine.lines = [info(1), info(2), "bestmove h2e2"]
    engine._analyze_once(START, 50, candidate_count=2)
    assert engine.commands[0] == "setoption name MultiPV value 1"
    assert engine.commands[3] == "setoption name MultiPV value 2"
