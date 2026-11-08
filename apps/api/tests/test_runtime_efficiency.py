"""Efficiency regressions must preserve safety, score fidelity and request shape."""
import queue
import threading
from types import SimpleNamespace
from unittest.mock import patch

import anyio
import httpx
import numpy as np
from test_api import FixedProvider
from test_engine_rules import START, ScriptedEngine
from test_engine_staged import StagedEngine, pair, primary

from rakuxq_api import main
from rakuxq_api.domain import Orientation, SideToMove
from rakuxq_api.engines.pikafish import PikafishEngine
from rakuxq_api.engines.rules import grid_from_fen, inspect_position
from rakuxq_api.providers.onnx import OnnxRecognitionProvider, _GlyphFeatures
from rakuxq_api.service import RecognitionService


def test_same_position_is_prepared_once_across_both_search_stages():
    from rakuxq_api.engines import pikafish

    engine = StagedEngine([primary(), pair()])
    with (patch.object(pikafish, "inspect_position", wraps=inspect_position) as inspect,
          patch.object(pikafish, "normalize_engine_fen", wraps=pikafish.normalize_engine_fen)
          as normalize):
        result = engine.analyze(START, 3000, 2)
    assert inspect.call_count == normalize.call_count == 1
    assert result.search.primary_budget_ms == 3000
    assert result.search.alternative_budget_ms == 1000
    assert result.best_move.iccs == "h2e2" and result.depth == 25


def test_later_exact_score_at_same_depth_replaces_earlier_bound():
    engine = ScriptedEngine([
        "info depth 18 score cp 200 lowerbound pv h2e2",
        "info depth 18 score cp 125 pv h2e2 h9g7",
        "bestmove h2e2",
    ])
    result = engine.analyze(START, 3000)
    assert result.score.value == 125 and result.score.bound is None
    assert result.pv == ["h2e2", "h9g7"]
    assert result.pv_notation == result.recommendations[0].pv_notation


def test_retiring_reader_cannot_poison_replacement_output_queue():
    old_lines = queue.Queue()
    replacement_lines = queue.Queue()
    engine = PikafishEngine("", "")
    engine._lines = replacement_lines
    process = SimpleNamespace(stdout=iter(["old output\n"]))
    engine._read_stdout(process, old_lines)
    assert [old_lines.get_nowait(), old_lines.get_nowait()] == ["old output", None]
    assert replacement_lines.empty()


def test_move_generation_leaves_input_rows_untouched_and_order_stable():
    from rakuxq_api.engines.rules import legal_moves

    grid = grid_from_fen(START)
    before = [row[:] for row in grid]
    first = legal_moves(grid, True)
    assert grid == before
    assert first == legal_moves(tuple(tuple(row) for row in grid), True)
    assert len(first) == 44


def test_confident_layout_skips_all_glyph_patch_extraction():
    image = np.zeros((500, 450, 3), dtype=np.uint8)
    symbols = list("rnbakabnr") + ["."] * 72 + list("RNBAKABNR")
    confidences = np.full(90, .99, dtype=np.float32)
    with patch("cv2.getRectSubPix", side_effect=AssertionError("unused feature extraction")):
        refined, effective, details = OnnxRecognitionProvider._same_image_prototype_refinement(
            image, symbols, confidences, [True] * 90)
        evidence = OnnxRecognitionProvider._piece_type_prototype_evidence(
            image, refined, effective, [True] * 90)
    assert refined == symbols and details == evidence == []


def test_lazy_features_match_legacy_math_and_reuse_only_requested_patches():
    import cv2

    image = np.random.default_rng(20261108).integers(0, 256, (500, 450, 3), dtype=np.uint8)
    cache = _GlyphFeatures(image)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    with patch("cv2.getRectSubPix", wraps=cv2.getRectSubPix) as extract:
        for index in [0, 14, 89, 14]:
            row, file = divmod(index, 9)
            patch_image = cv2.getRectSubPix(gray, (37, 37),
                                          (50 + file * 43.75, 50 + row * (400 / 9)))
            expected = cv2.resize(patch_image, (32, 32), interpolation=cv2.INTER_AREA).astype(
                np.float32)
            expected -= expected.mean()
            expected /= expected.std() + 1e-6
            np.testing.assert_array_equal(cache[index], expected.reshape(-1))
        assert extract.call_count == 4 + 3  # Four reference extractions, three lazy ones.


def test_worker_vision_keeps_health_responsive_and_preserves_single_vision_lane():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        completed = anyio.Event()
        active = 0
        maximum = 0
        mutex = threading.Lock()
        service = RecognitionService(FixedProvider())

        def blocked(data, side, orientation, location):
            nonlocal active, maximum
            with mutex:
                active += 1
                maximum = max(maximum, active)
            entered.set()
            release.wait(timeout=2)
            result = service.recognize(data, side, orientation)
            with mutex:
                active -= 1
            return result

        async def recognize(client):
            response = await client.post('/v1/recognitions',
                                         files={'image': ('board.png', b'fake', 'image/png')},
                                         data={'side_to_move': 'red'})
            assert response.status_code == 200 and response.json()['status'] == 'accepted'
            completed.set()

        with patch.object(main, '_run', blocked):
            # The production lifespan installs its own loop-local limiter.
            previous = getattr(main.app.state, 'recognition_limiter', None)
            main.app.state.recognition_limiter = anyio.CapacityLimiter(1)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                             base_url='http://testserver') as client:
                    async with anyio.create_task_group() as group:
                        group.start_soon(recognize, client)
                        group.start_soon(recognize, client)
                        try:
                            with anyio.fail_after(1):
                                while not entered.is_set():
                                    await anyio.sleep(.001)
                                assert not completed.is_set()
                                response = await client.get('/healthz')
                                assert response.status_code == 200
                                assert not completed.is_set()
                        finally:
                            release.set()
                assert maximum == 1
            finally:
                if previous is None:
                    del main.app.state.recognition_limiter
                else:
                    main.app.state.recognition_limiter = previous

    anyio.run(scenario)


def test_recognize_helper_retains_explicit_controls():
    async def scenario():
        with patch.object(main, '_run', return_value='unchanged') as run:
            result = await main._recognize(b'image', SideToMove.BLACK,
                                            Orientation.BLACK_BOTTOM, None)
        assert result == 'unchanged'
        run.assert_called_once_with(b'image', SideToMove.BLACK, Orientation.BLACK_BOTTOM, None)
    anyio.run(scenario)
