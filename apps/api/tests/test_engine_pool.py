import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from rakuxq_api.engines.base import EngineAnalysisError, EngineIdentity
from rakuxq_api.engines.pool import PikafishPool


class FakeWorker:
    configured = True

    def __init__(self, *_args, **_kwargs):
        self.ready = False
        self.identity = EngineIdentity('fixed', None, 'same', 'same-network')
        self.closed = False
        self.active = False

    def start(self):
        self.ready = True
        self.closed = False

    def close(self):
        assert not self.active
        self.ready = False
        self.closed = True

    def analyze(self, fen, movetime_ms, max_candidates=1):
        assert not self.active and not self.closed
        self.active = True
        try:
            if fen == 'fail':
                raise EngineAnalysisError('injected')
            time.sleep(.02)
            return fen, movetime_ms, max_candidates
        finally:
            self.active = False


@pytest.mark.parametrize('workers', [1, 2])
def test_pool_caps_parallelism_and_never_interleaves_or_changes_requests(workers):
    active, maximum = 0, 0
    mutex = threading.Lock()

    class MeasuredWorker(FakeWorker):
        def analyze(self, *args):
            nonlocal active, maximum
            with mutex:
                active += 1
                maximum = max(maximum, active)
            try:
                return super().analyze(*args)
            finally:
                with mutex:
                    active -= 1

    with patch('rakuxq_api.engines.pool.PikafishEngine', MeasuredWorker):
        pool = PikafishPool('', '', workers=workers)
    pool.start()
    assert pool.configured and pool.ready and pool.identity.network_sha256 == 'same-network'
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda n: pool.analyze(str(n), 9000, 2), range(6)))
    assert maximum == workers
    assert results == [(str(n), 9000, 2) for n in range(6)]
    pool.close()
    assert not pool.ready and all(worker.closed for worker in pool._engines)


def test_analysis_error_always_releases_lease_without_hidden_engine_fallback():
    with patch('rakuxq_api.engines.pool.PikafishEngine', FakeWorker):
        pool = PikafishPool('', '', workers=1)
    pool.start()
    with pytest.raises(EngineAnalysisError, match='injected'):
        pool.analyze('fail', 1500)
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(pool.analyze, 'next', 1500).result(timeout=1) == ('next', 1500, 1)
    pool.close()


def test_serial_play_reuses_a_warm_process_instead_of_rotating_hash_tables():
    called = []

    class StickyWorker(FakeWorker):
        def analyze(self, *args):
            called.append(id(self))
            return super().analyze(*args)

    with patch('rakuxq_api.engines.pool.PikafishEngine', StickyWorker):
        pool = PikafishPool('', '', workers=2)
    pool.start()
    for turn in range(4):
        pool.analyze(str(turn), 1500)
    assert len(set(called)) == 1
    pool.close()


def test_shutdown_waits_for_active_analysis_and_does_not_resurrect_workers():
    entered, release = threading.Event(), threading.Event()

    class BlockingWorker(FakeWorker):
        def analyze(self, *args):
            entered.set()
            assert release.wait(timeout=2)
            return super().analyze(*args)

    with patch('rakuxq_api.engines.pool.PikafishEngine', BlockingWorker):
        pool = PikafishPool('', '', workers=1)
    pool.start()
    with ThreadPoolExecutor(max_workers=2) as executor:
        request = executor.submit(pool.analyze, 'active', 1500)
        assert entered.wait(timeout=1)
        shutdown = executor.submit(pool.close)
        try:
            deadline = time.monotonic() + 1
            while not pool._closing and time.monotonic() < deadline:
                time.sleep(.001)
            assert pool._closing and not shutdown.done()
            with pytest.raises(EngineAnalysisError, match='shutting down'):
                pool.analyze('late', 1500)
        finally:
            release.set()
        assert request.result(timeout=1) == ('active', 1500, 1)
        shutdown.result(timeout=1)
    assert pool._engines[0].closed


@pytest.mark.parametrize('workers', [0, 3, -1])
def test_more_than_two_processes_cannot_accidentally_be_enabled(workers):
    with pytest.raises(ValueError, match='1 or 2'):
        PikafishPool('', '', workers=workers)
