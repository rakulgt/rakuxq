#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.arena
# Role: Serial, color-swapped UCI matches with independent move validation and honest outcomes.
# Inputs: Explicitly permitted executables/networks, seed and time budget. Outputs: evidence JSON.
# Provenance: Project-authored, AI-assisted. State: experimental; no production activation.
from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps/api/src"))
from rakuxq_api.engines.rules import grid_from_fen, inspect_position  # noqa: E402

START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"


def file_hash(path: Path | None) -> str | None:
    if path is None:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def advance(fen: str, move: str) -> str:
    state, moves = inspect_position(fen)
    if move not in moves:
        raise ValueError("engine returned an illegal move while legal moves remain")
    grid = grid_from_fen(fen)
    source = (9 - int(move[1]), ord(move[0]) - ord("a"))
    target = (9 - int(move[3]), ord(move[2]) - ord("a"))
    grid[target[0]][target[1]], grid[source[0]][source[1]] = grid[source[0]][source[1]], "."
    ranks = []
    for row in grid:
        empty, rank = 0, ""
        for piece in row:
            if piece == ".":
                empty += 1
            else:
                rank += (str(empty) if empty else "") + piece
                empty = 0
        ranks.append(rank + (str(empty) if empty else ""))
    return "/".join(ranks) + (" b" if state.side_to_move == "red" else " w")


class Engine:
    def __init__(self, executable: Path, network: Path | None, budget_ms: int):
        self.process = subprocess.Popen(
            [str(executable.resolve())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.lines = queue.Queue()
        self.budget_ms = budget_ms

        def read():
            for line in self.process.stdout:
                self.lines.put(line.rstrip())
            self.lines.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self.send("uci")
            startup = self.until("uciok", 10)
            self.name = next((s[8:] for s in startup if s.startswith("id name ")), "unknown")
            for name, value in (("Threads", 1), ("Hash", 16), ("MultiPV", 1)):
                self.send(f"setoption name {name} value {value}")
            if network:
                self.send(f"setoption name EvalFile value {network.resolve()}")
            self.send("isready")
            self.until("readyok", 10)
        except Exception:
            self.close()
            raise

    def send(self, command: str) -> None:
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def until(self, target: str, seconds: float) -> list[str]:
        end, lines = time.monotonic() + seconds, []
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("UCI response deadline exceeded")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("UCI response deadline exceeded") from exc
            if line is None:
                raise RuntimeError("engine exited unexpectedly")
            if "ERROR:" in line or "CRITICAL ERROR" in line:
                raise RuntimeError("engine rejected the request")
            lines.append(line)
            if line == target or line.startswith(target + " "):
                return lines
            if len(lines) > 100000:
                raise RuntimeError("unbounded engine output")

    def new_game(self) -> None:
        self.send("ucinewgame")
        self.send("isready")
        self.until("readyok", 5)

    def move(self, root: str, history: list[str]) -> tuple[str, float]:
        self.send(
            "position fen " + root + " - - 0 1" + (" moves " + " ".join(history) if history else "")
        )
        started = time.monotonic()
        self.send(f"go movetime {self.budget_ms}")
        response = self.until("bestmove", self.budget_ms / 1000 + 5)
        tokens = response[-1].split()
        if len(tokens) < 2:
            raise ValueError("missing best move")
        return tokens[1], (time.monotonic() - started) * 1000

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.send("quit")
                self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
        finally:
            self.process.wait(timeout=5)
            self.reader.join(timeout=1)


def play(red: Engine, black: Engine, opening: str, max_plies: int) -> dict:
    red.new_game()
    black.new_game()
    fen, moves, seen, delays = opening, [], {}, []
    for _ in range(max_plies + 1):
        state, _ = inspect_position(fen)
        if state.terminal_reason:
            return {
                "reason": state.terminal_reason,
                "winner": state.winner,
                "plies": len(moves),
                "response_ms": delays,
            }
        seen[fen] = seen.get(fen, 0) + 1
        if seen[fen] >= 3:
            break
        if len(moves) == max_plies:
            break
        mover = red if state.side_to_move == "red" else black
        move, elapsed = mover.move(opening, moves)
        fen = advance(fen, move)
        moves.append(move)
        delays.append(elapsed)
    return {
        "reason": "unresolved_repetition" if seen[fen] >= 3 else "ply_limit",
        "winner": None,
        "plies": len(moves),
        "response_ms": delays,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-network", type=Path)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-network", type=Path)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--plies", type=int, default=120)
    parser.add_argument("--time-ms", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.pairs <= 1000 or not 1 <= args.time_ms <= 9000 or not 2 <= args.plies <= 512:
        raise ValueError("arena budget outside limits")
    if args.output.exists():
        raise ValueError("Refusing to overwrite evidence")
    rng = random.Random(args.seed)
    games, paired_scores = [], []
    candidate = Engine(args.candidate, args.candidate_network, args.time_ms)
    try:
        reference = Engine(args.reference, args.reference_network, args.time_ms)
        try:
            for pair in range(args.pairs):
                opening = START
                for _ in range(4 + 2 * (pair % 3)):
                    _, legal = inspect_position(opening)
                    if not legal:
                        break
                    opening = advance(opening, rng.choice(legal))
                scores = []
                for candidate_red in (True, False):
                    result = play(
                        candidate if candidate_red else reference,
                        reference if candidate_red else candidate,
                        opening,
                        args.plies,
                    )
                    result.update(
                        {"pair": pair, "candidate_red": candidate_red, "opening": opening}
                    )
                    if result["winner"] is not None:
                        scores.append(
                            float(result["winner"] == ("red" if candidate_red else "black"))
                        )
                    games.append(result)
                if len(scores) == 2:
                    paired_scores.append(sum(scores) / 2)
            mean = sum(paired_scores) / len(paired_scores) if paired_scores else None
            radius = math.sqrt(math.log(40) / (2 * len(paired_scores))) if paired_scores else None
            evidence = {
                "_meta": {
                    "artifact_id": "rakuxq.native.arena-evidence",
                    "purpose": "evaluation_only",
                    "not_training_labels": True,
                    "license": "MIT",
                },
                "candidate": {
                    "name": candidate.name,
                    "sha256": file_hash(args.candidate),
                    "network_sha256": file_hash(args.candidate_network),
                },
                "reference": {
                    "name": reference.name,
                    "sha256": file_hash(args.reference),
                    "network_sha256": file_hash(args.reference_network),
                },
                "seed": args.seed,
                "time_ms": args.time_ms,
                "threads_per_engine": 1,
                "hash_mb": 16,
                "games": games,
                "completed_pairs": len(paired_scores),
                "candidate_pair_score": mean,
                "exploratory_95pct_interval": None
                if mean is None
                else [max(0, mean - radius), min(1, mean + radius)],
                "interval_assumptions": "Independent opening pairs; exploratory, not certified Elo",
                "history_rules_certified": False,
                "production_approved": False,
                "remaining_gates": [
                    "independent source review",
                    "vision blind benchmark",
                    "certified history adjudication",
                    "same-budget engine nonregression",
                    "latency/memory/stability",
                    "staged deployment and rollback",
                ],
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(evidence, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            print(
                json.dumps(
                    {
                        "games": len(games),
                        "completed_pairs": len(paired_scores),
                        "production_approved": False,
                        "evidence": str(args.output),
                    }
                )
            )
        finally:
            reference.close()
    finally:
        candidate.close()


if __name__ == "__main__":
    main()
