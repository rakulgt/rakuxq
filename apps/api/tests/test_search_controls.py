from unittest.mock import patch

import pytest
from test_api import START_FEN, FixedProvider, client
from test_engine_staged import StagedEngine, pair, primary

from rakuxq_api.engines.base import parse_max_candidates, search_budgets
from rakuxq_api.service import RecognitionService


@pytest.mark.parametrize("value", [None, "", "auto", " AUTO ", 1, "1"])
def test_auto_and_omission_mean_one(value):
    assert parse_max_candidates(value) == 1


@pytest.mark.parametrize("value", [True, False, 1.0, 2.0, 0, 3, "three", "1.5", [], {}])
def test_invalid_counts_are_not_silently_coerced(value):
    with pytest.raises(ValueError):
        parse_max_candidates(value)


@pytest.mark.parametrize("ms,count,expected", [
    (3000, 1, (3000, 0)), (10000, 1, (9000, 0)),
    (3000, 2, (3000, 1000)), (10000, 2, (8000, 1000)),
    (600, 2, (600, 200)), (50, 1, (50, 0)),
])
def test_time_only_caps(ms, count, expected):
    assert search_budgets(ms, count) == expected


def test_engine_omitted_count_really_skips_the_second_search():
    engine = StagedEngine([primary()])
    result = engine.analyze(START_FEN, 3000)
    assert len(engine.commands) == 3
    assert result.search.max_candidates == 1
    assert result.search.alternative_budget_ms == 0
    assert result.search.strategy == "primary_only"
    assert 3000 <= engine.timeouts[0] <= 3250


@pytest.mark.parametrize("count", [1, 2])
def test_engine_caps_real_uci_command_and_never_searches_an_unrequested_alternative(count):
    engine = StagedEngine([primary(), pair()] if count == 2 else [primary()])
    result = engine.analyze(START_FEN, 10000, count)
    assert engine.commands[2] == f"go movetime {8000 if count == 2 else 9000}"
    assert len(engine.commands) == (6 if count == 2 else 3)
    assert result.search.total_budget_ms == 9000
    if count == 1:
        assert result.search.alternative_time_ms == 0
        assert result.search.strategy == "primary_only"
        assert result.alternative_omitted_reason == "not_requested"


@pytest.mark.parametrize("path,time_field,headers", [
    ("/v1/solutions", "time_ms", {}), ("/v1/analyses", "movetime_ms", {}),
    ("/api/lab/analyses", "movetime_ms", {"Origin": "http://testserver"}),
])
@pytest.mark.parametrize("control", [{}, {"max_candidates": "auto"}, {"max_candidates": 1},
                                     {"max_candidates": "2"}])
def test_all_json_entrypoints_share_candidate_and_budget_policy(path, time_field, headers, control):
    count = parse_max_candidates(control.get("max_candidates"))
    engine = StagedEngine([primary(), pair()] if count == 2 else [primary()])
    with patch("rakuxq_api.main.analysis_engine", engine):
        response = client.post(path, headers=headers, json={
            "fen": START_FEN, time_field: 10000, **control,
        })
    assert response.status_code == 200
    result = response.json()
    assert len(result["recommendations"]) == count
    assert result["search"]["total_budget_ms"] == 9000
    assert result["search"]["primary_budget_ms"] == (9000 if count == 1 else 8000)
    if path == "/v1/solutions":
        assert result["search"]["primary_budget_capped"] is True
        assert result["search"]["max_candidates"] == count


@pytest.mark.parametrize("control,count", [({}, 1), ({"max_candidates": "auto"}, 1),
                                         ({"max_candidates": "1"}, 1),
                                         ({"max_candidates": "2"}, 2)])
def test_image_form_passes_controls_through_the_real_staged_engine(control, count):
    engine = StagedEngine([primary(), pair()] if count == 2 else [primary()])
    with (patch("rakuxq_api.main.analysis_engine", engine),
          patch("rakuxq_api.main.service", RecognitionService(FixedProvider()))):
        response = client.post("/v1/solve", files={"image": ("board.png", b"image", "image/png")},
                               data={"side_to_move": "red", **control})
    assert response.status_code == 200
    result = response.json()
    assert result["analysis_status"] == "completed"
    assert len(result["analysis"]["recommendations"]) == count
    assert result["analysis"]["search"]["total_budget_ms"] == (4000 if count == 2 else 3000)


@pytest.mark.parametrize("path", ["/v1/analyses", "/v1/solutions", "/api/lab/analyses"])
@pytest.mark.parametrize("value", [0, 3, True, 1.5, "bogus"])
def test_invalid_json_controls_fail_before_search(path, value):
    with patch("rakuxq_api.main.analysis_engine") as engine:
        response = client.post(path, headers={"Origin": "http://testserver"},
                               json={"fen": START_FEN, "max_candidates": value})
    assert response.status_code == 422
    engine.analyze.assert_not_called()


def test_invalid_image_control_does_not_run_recognition_or_search():
    with (patch("rakuxq_api.main.service") as recognition,
          patch("rakuxq_api.main.analysis_engine") as engine):
        response = client.post("/v1/solve", files={"image": ("board.png", b"image", "image/png")},
                               data={"max_candidates": "3"})
    assert response.status_code == 422
    recognition.recognize.assert_not_called()
    engine.analyze.assert_not_called()
