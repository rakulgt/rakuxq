from dataclasses import asdict

import pytest

from rakuxq_api.engines.base import (
    InvalidEnginePosition,
    analysis_to_dict,
    normalize_engine_fen,
    score_from_side_to_move,
)
from rakuxq_api.engines.pikafish import parse_uci_info

START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"


def test_normalize_engine_fen_expands_short_contract():
    assert normalize_engine_fen(START_FEN) == f"{START_FEN} - - 0 1"


@pytest.mark.parametrize(
    "fen,message",
    [
        ("9/9/9/9/9/9/9/9/9/9 w", "exactly one red and one black king"),
        ("4k4/9/9/9/9/9/9/9/9/4K3 w", "expands to 8 files"),
        ("4k4/9/9/9/9/9/9/9/9/4K4 x", "active color"),
        ("4k4/9/9/9/9/9/3K5/9/9/9 w", "RED_KING_OUTSIDE_PALACE"),
    ],
)
def test_normalize_engine_fen_rejects_positions_that_could_kill_strict_engine(
    fen, message
):
    with pytest.raises(InvalidEnginePosition, match=message):
        normalize_engine_fen(fen)


def test_score_is_always_normalized_to_red_perspective():
    red_advantage = score_from_side_to_move("cp", 186, "w")
    black_advantage = score_from_side_to_move("cp", 243, "b")

    assert asdict(red_advantage) == {
        "type": "cp",
        "value": 186,
        "perspective": "red",
        "display": "+186",
        "bound": None,
    }
    assert black_advantage.value == -243
    assert black_advantage.display == "-243"


def test_mate_score_uses_ko_contract_and_red_perspective():
    red_mates = score_from_side_to_move("mate", -5, "b")
    black_mates = score_from_side_to_move("mate", 3, "b")

    assert red_mates.value == 5
    assert red_mates.display == "KO(+5)"
    assert black_mates.value == -3
    assert black_mates.display == "KO(-3)"


def test_parse_pikafish_principal_variation_info():
    parsed = parse_uci_info(
        "info depth 18 seldepth 27 multipv 1 score cp -42 nodes 123456 "
        "nps 987654 time 125 pv h2e2 h9g7"
    )

    assert parsed is not None
    assert parsed.depth == 18
    assert parsed.seldepth == 27
    assert parsed.score_type == "cp"
    assert parsed.score_value == -42
    assert parsed.nodes == 123456
    assert parsed.nps == 987654
    assert parsed.time_ms == 125
    assert parsed.pv == ["h2e2", "h9g7"]


def test_parse_pikafish_ignores_non_primary_multipv():
    assert parse_uci_info("info depth 12 multipv 2 score cp 10 pv a0a1") is None


def test_public_move_fields_use_from_and_to_names():
    from rakuxq_api.engines.base import AnalysisResult, EngineMove

    payload = analysis_to_dict(
        AnalysisResult(
            status="completed",
            fen=f"{START_FEN} - - 0 1",
            best_move=EngineMove("h2e2", "h2", "e2"),
            ponder=None,
            score=None,
            depth=1,
            seldepth=None,
            nodes=None,
            time_ms=1,
            nps=None,
        )
    )

    assert payload["best_move"] == {"iccs": "h2e2", "from": "h2", "to": "e2"}
