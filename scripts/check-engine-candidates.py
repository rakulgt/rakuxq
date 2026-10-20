"""Serial single-primary/staged wall-time smoke benchmark; never loads user uploads."""

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--time-ms", type=int, default=3000)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    from rakuxq_api.engines import PikafishEngine, analysis_to_dict
    from rakuxq_api.engines.rules import inspect_position

    start = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"
    positions = {
        "opening_red": start + " w",
        "opening_black": start + " b",
        "forced_mate": "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w",
    }
    results = []
    for name, fen in positions.items():
        # Separate processes, strictly serial, equal cold hashes and thread limits.
        for mode, count in (("single", 1), ("two", 2)):
            engine = PikafishEngine(args.engine, args.network, threads=1, hash_mb=64)
            try:
                engine.start()
                began = time.monotonic()
                result = engine.analyze(fen, args.time_ms, count)
                wall_ms = round((time.monotonic() - began) * 1000)
                _, legal = inspect_position(fen)
                assert result.best_move.iccs in legal
                assert wall_ms < min(9000, args.time_ms + (1000 if count == 2 else 0)) + 500, (
                    name, mode, wall_ms,
                )
                assert len(result.recommendations) in {1, 2}
                assert all(r.move.iccs in legal for r in result.recommendations)
                results.append({
                    "case": name, "mode": mode, "wall_ms": wall_ms,
                    "engine_ms": result.time_ms, "depth": result.depth,
                    "candidate_count": len(result.recommendations),
                    "primary_ms": result.search.primary_time_ms if result.search else result.time_ms,
                    "alternative_ms": result.search.alternative_time_ms if result.search else 0,
                    "omission": result.alternative_omitted_reason,
                    "display_text": analysis_to_dict(result)["display_text"],
                })
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            finally:
                engine.close()


if __name__ == "__main__":
    main()
