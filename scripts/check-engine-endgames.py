"""Local/server smoke check against a separately installed engine/network pair."""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--network", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    from rakuxq_api.engines import InvalidEnginePosition, PikafishEngine, analysis_to_dict
    from rakuxq_api.engines.rules import inspect_position

    evasion = "5k3/9/9/9/9/9/4r4/9/9/4K4 w"
    positions = {
        "single_check_evasion": evasion,
        "forced_mate_still_playable": "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w",
        "checkmate": "4k4/3RR4/9/9/9/9/9/9/9/5K3 b",
        "stalemate": "4k4/3R1R3/9/9/9/9/9/9/9/3K5 b",
    }
    engine = PikafishEngine(args.engine, args.network, threads=1, hash_mb=64)
    results = []
    try:
        engine.start()
        for name, fen in positions.items():
            result = engine.analyze(fen, 200)
            state, moves = inspect_position(fen)
            assert result.status == ("terminal" if state.terminal_reason else "completed")
            if moves:
                assert result.best_move and result.best_move.iccs in moves
                if name == "single_check_evasion":
                    assert result.best_move.iccs == "e0d0"
            else:
                assert result.best_move is None and result.position.winner == "red"
            results.append({"case": name, "status": result.status,
                            "display_text": analysis_to_dict(result)["display_text"],
                            "time_ms": result.time_ms})
        try:
            engine.analyze(evasion.replace(" w", " b"), 200)
        except InvalidEnginePosition as exc:
            assert exc.code == "SIDE_TO_MOVE_CONFLICT"
        else:
            raise AssertionError("mover conflict was not rejected")
        assert engine.ready, "invalid input must not terminate the engine"
        again = engine.analyze(evasion, 200)
        assert again.best_move.iccs == "e0d0"
        results.append({"case": "conflict_then_valid", "engine_still_ready": engine.ready})
    finally:
        engine.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
