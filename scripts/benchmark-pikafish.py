from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

POSITIONS = (
    "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w",
    "1rbakab1r/9/2n3nc1/p3p1p1p/2p6/9/PcP1P1P1P/2N1CCN2/9/1RBAKAB1R w",
    "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    "2b1kab2/4a4/1R7/1N7/p1r5P/1N4P2/P8/4B4/4A4/4KAB2 w",
    "1rbakab1r/9/1cn4c1/p1p1p4/6pnp/2P6/P3P1P1P/2N1C1C1N/8R/1RBAKAB2 b",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark one RakuXQ-compatible Pikafish pair")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--movetime-ms", type=int, default=3000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    from rakuxq_api.engines import PikafishEngine

    engine = PikafishEngine(
        args.engine,
        args.network,
        threads=1,
        hash_mb=64,
        command_timeout_ms=max(5000, args.movetime_ms + 2000),
        version=args.version,
    )
    results: list[dict[str, object]] = []
    try:
        engine.start()
        for fen in POSITIONS:
            result = engine.analyze(fen, args.movetime_ms)
            results.append(
                {
                    "fen": fen,
                    "best_move": result.best_move.iccs if result.best_move else None,
                    "score": result.score.display if result.score else None,
                    "depth": result.depth,
                    "seldepth": result.seldepth,
                    "nodes": result.nodes,
                    "time_ms": result.time_ms,
                    "nps": result.nps,
                    "pv": result.pv,
                }
            )
    finally:
        engine.close()

    print(
        json.dumps(
            {
                "version": args.version,
                "movetime_ms": args.movetime_ms,
                "positions": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
