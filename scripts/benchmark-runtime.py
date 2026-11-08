"""RakuXQ adapter/vision benchmark, independent of public requests and counters.

Original RakuXQ maintenance utility, Li Guotai, MIT, 2026-11-08.
Input: a source tree, optional local engine/model files and owner-approved images.
Output: aggregate timing and semantic checksums only; never images, FENs or keys.
Does not activate an engine, mutate a database or export training material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import partial
from pathlib import Path

POSITIONS = (
    'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w',
    '1rbakab1r/9/2n3nc1/p3p1p1p/2p6/9/PcP1P1P1P/2N1CCN2/9/1RBAKAB1R w',
    '3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w',
    '5k3/9/9/9/9/9/4r4/9/9/4K4 w',
    '4k4/3RR4/9/9/9/9/9/9/9/5K3 b',
)


def timing(values):
    ordered = sorted(values)
    return {'n': len(values), 'median_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3)}


def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()
                if k not in {'request_id', 'elapsed_ms', 'timings_ms'}}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(scrub(value), sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--engine')
    parser.add_argument('--network')
    parser.add_argument('--pose')
    parser.add_argument('--layout')
    parser.add_argument('--images', nargs='*', type=Path, default=[])
    parser.add_argument('--repeat', type=int, default=5)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pool', action='store_true', help='Compare one/two bounded UCI slots')
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    from rakuxq_api.domain import Orientation, SideToMove
    from rakuxq_api.engines import PikafishEngine
    from rakuxq_api.engines.base import normalize_engine_fen
    from rakuxq_api.engines.rules import inspect_position
    from rakuxq_api.providers.onnx import OnnxRecognitionProvider
    from rakuxq_api.service import RecognitionService

    samples = []
    for _ in range(40):
        start = time.perf_counter()
        for fen in POSITIONS:
            inspect_position(normalize_engine_fen(fen))
        samples.append((time.perf_counter() - start) * 1000 / len(POSITIONS))
    from rakuxq_api.main import app
    schema = app.openapi()
    schema['info'].pop('version', None)
    output = {'rules_per_position': timing(samples), 'vision': [], 'engine': [],
              'openapi_without_version_sha256': digest(schema)}
    if args.images:
        if not args.pose or not args.layout:
            parser.error('--images requires --pose and --layout')
        provider = OnnxRecognitionProvider(args.pose, args.layout, intra_op_num_threads=2)
        provider.warmup()
        service = RecognitionService(provider)
        for index, path in enumerate(args.images):
            data = path.read_bytes()
            samples, hashes = [], set()
            for _ in range(args.repeat):
                start = time.perf_counter()
                result = service.recognize(data, SideToMove.AUTO, Orientation.AUTO)
                samples.append((time.perf_counter()-start)*1000)
                hashes.add(digest(asdict(result)))
            output['vision'].append({'case': index + 1, 'status': result.status,
                                     'contract_sha256': sorted(hashes), **timing(samples)})
    if args.engine and args.network and args.pool:
        from rakuxq_api.engines.pool import PikafishPool
        output['pool'] = []
        for workers in (1, 2):
            pool = PikafishPool(args.engine, args.network, workers=workers, threads=1, hash_mb=64)
            try:
                pool.start()
                rss_kib = 0
                for engine in pool._engines:
                    status = Path(f'/proc/{engine._process.pid}/status')
                    if status.exists():
                        rss_kib += int(next(line.split()[1] for line in status.read_text().splitlines()
                                            if line.startswith('VmRSS:')))
                start = time.perf_counter()
                with ThreadPoolExecutor(max_workers=2) as executor:
                    answers = list(executor.map(partial(pool.analyze, movetime_ms=1500),
                                                POSITIONS[:2]))
                output['pool'].append({'workers': workers,
                    'pair_wall_ms': round((time.perf_counter()-start)*1000, 3),
                    'engine_rss_mib': round(rss_kib/1024, 2),
                    'search_ms': [answer.time_ms for answer in answers],
                    'depths': [answer.depth for answer in answers],
                    'moves': [answer.best_move.iccs for answer in answers],
                    'legal': all(answer.best_move.iccs in inspect_position(answer.fen)[1]
                                 for answer in answers)})
            finally:
                pool.close()
    elif args.engine and args.network:
        # A fresh process/hash per case keeps source comparisons independent.
        for index, fen in enumerate(POSITIONS):
            engine = PikafishEngine(args.engine, args.network, threads=1, hash_mb=64)
            try:
                engine.start()
                start = time.perf_counter()
                result = engine.analyze(fen, 1500, 1)
                output['engine'].append({'case': index + 1, 'status': result.status,
                    'wall_ms': round((time.perf_counter()-start)*1000, 3),
                    'search_ms': result.time_ms, 'depth': result.depth,
                    'best_move': result.best_move.iccs if result.best_move else None,
                    'score': asdict(result.score) if result.score else None,
                    'legal': result.best_move is None or result.best_move.iccs
                    in inspect_position(result.fen)[1]})
            finally:
                engine.close()
    rendered = json.dumps(output, indent=2)
    if args.output:
        # Output contains summaries only, never original paths or business data.
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
