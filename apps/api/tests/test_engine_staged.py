from unittest.mock import patch

import pytest
from test_engine_candidates import info
from test_engine_rules import START, ScriptedEngine

from rakuxq_api.engines.base import EngineTimeout, analysis_to_dict, search_budgets


class StagedEngine(ScriptedEngine):
    def __init__(self, stages):
        super().__init__([])
        self.stages = list(stages)
        self.timeouts = []

    def _read_until(self, target, timeout_ms):
        self.timeouts.append(timeout_ms)
        stage = self.stages.pop(0)
        if isinstance(stage, Exception):
            raise stage
        return stage


def primary(score="cp 80", move="h2e2"):
    return [info(1, score, depth=25, move=move), f"bestmove {move}"]


def pair():
    return [info(1, "cp 75", depth=17), info(2, "cp 60", depth=17), "bestmove h2e2"]


def test_first_search_is_single_pv_3s_then_short_comparison_and_primary_is_frozen():
    engine = StagedEngine([primary(), pair()])
    result = engine.analyze(START, 3000)
    assert engine.commands[0] == "setoption name MultiPV value 1"
    assert engine.commands[2] == "go movetime 3000"
    assert engine.commands[3] == "setoption name MultiPV value 2"
    assert 900 <= int(engine.commands[5].split()[-1]) <= 975
    assert result.best_move.iccs == "h2e2"
    assert result.score.value == 80 and result.depth == 25
    assert result.recommendations[0].depth == 25
    assert result.recommendations[1].depth == 17
    assert result.search.comparison_primary_score.value == 75
    assert result.search.comparison_depth == 17
    assert result.search.total_budget_ms == 4000
    assert "备选：" in analysis_to_dict(result)["display_text"]


def test_short_search_cannot_replace_the_deeper_primary_even_if_it_ranks_another_root_first():
    engine = StagedEngine([primary(), [
        info(1, "cp 90", depth=17, move="b2e2"),
        info(2, "cp 85", depth=17, move="h2e2"), "bestmove b2e2",
    ]])
    result = engine.analyze(START, 3000)
    assert result.best_move.iccs == "h2e2"
    assert result.score.value == 80 and result.depth == 25
    assert result.recommendations[1].move.iccs == "b2e2"


def test_black_staged_search_keeps_fixed_red_scores_and_black_mover_quality():
    engine = StagedEngine([
        [info(1, "cp 80", depth=25, move="h7e7"), "bestmove h7e7"],
        [info(1, "cp 75", depth=17, move="h7e7"),
         info(2, "cp 60", depth=17, move="b7e7"), "bestmove h7e7"],
    ])
    result = engine.analyze(START.replace(" w", " b"), 3000)
    assert result.score.value == -80
    assert [r.score.value for r in result.recommendations] == [-80, -60]
    assert result.search.comparison_primary_score.value == -75


def test_one_lock_prevents_other_requests_from_entering_either_stage():
    import threading

    engine = StagedEngine([primary(), pair()])
    read = engine._read_until
    attempts = []

    def locked_read(target, timeout_ms):
        def another_request():
            acquired = engine._lock.acquire(timeout=0.01)
            attempts.append(acquired)
            if acquired:
                engine._lock.release()

        thread = threading.Thread(target=another_request)
        thread.start()
        thread.join()
        return read(target, timeout_ms)

    engine._read_until = locked_read
    engine.analyze(START, 3000)
    assert attempts == [False, False]


@pytest.mark.parametrize("first,second,reason", [
    ("cp 800", "cp 60", "score_gap"),
    ("cp -500", "cp 60", "insufficient_search"),
    ("mate 2", "cp 60", "mate_outcome"),
    ("cp 80 lowerbound", "cp 60", "insufficient_search"),
])
def test_shallower_pair_cannot_override_deeper_primary_safety(first, second, reason):
    engine = StagedEngine([primary(first), [
        info(1, "cp 75", depth=17), info(2, second, depth=17), "bestmove h2e2",
    ]])
    result = engine.analyze(START, 3000)
    assert result.best_move.iccs == "h2e2"
    assert len(result.recommendations) == 1
    assert result.alternative_omitted_reason == reason


def test_optional_engine_timeout_never_discards_the_primary_answer():
    engine = StagedEngine([primary(), EngineTimeout("test timeout")])
    result = engine.analyze(START, 3000)
    assert result.status == "completed"
    assert result.best_move.iccs == "h2e2" and result.score.value == 80
    assert len(result.recommendations) == 1
    assert result.alternative_omitted_reason == "alternative_failed"
    assert result.search.alternative_status == "failed"


def test_a_short_budget_does_not_start_a_pointless_optional_search():
    engine = StagedEngine([primary()])
    result = engine.analyze(START, 50)
    assert len(engine.commands) == 3
    assert result.alternative_omitted_reason == "budget_exhausted"


def test_deadline_can_skip_the_alternative_even_if_primary_overruns():
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()
    engine = StagedEngine([primary()])
    read = engine._read_until

    def delayed_read(target, timeout_ms):
        clock.now = 3.99
        return read(target, timeout_ms)

    engine._read_until = delayed_read
    with patch("rakuxq_api.engines.pikafish.time.monotonic", clock.monotonic):
        result = engine.analyze(START, 3000)
    assert result.best_move.iccs == "h2e2"
    assert result.alternative_omitted_reason == "budget_exhausted"
    assert len(engine.commands) == 3
    assert engine.timeouts[0] <= 4000


@pytest.mark.parametrize("requested_ms,expected", [
    (3000, (3000, 1000)), (10000, (3000, 1000)), (600, (600, 200)), (50, (50, 16)),
])
def test_primary_and_total_budget_caps_are_explicit(requested_ms, expected):
    assert search_budgets(requested_ms) == expected
    engine = StagedEngine([primary(), pair()])
    result = engine.analyze(START, requested_ms)
    assert engine.commands[2] == f"go movetime {expected[0]}"
    assert result.search.total_budget_ms <= 4000
