# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.tests
# Role: Safety, UCI, quantization and independent dataset regression checks.
# Inputs: Candidate executable (optional locally), temporary synthetic fixtures.
# Outputs: Test results; no production state changes. Provenance: Project-authored, AI-assisted.
# State: experimental; passing these checks does not establish production-equivalent strength.
from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rakuxq_native_pipeline", ROOT / "tools/pipeline.py")
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)
START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"
EVASION = "5k3/9/9/9/9/9/4r4/9/9/4K4 w"
WINNING = "4k4/3R1R3/9/9/9/9/9/9/9/5K3 w"


@pytest.fixture
def executable():
    value = os.environ.get("RAKUXQ_NATIVE_ENGINE")
    if not value:
        pytest.skip("native executable absent; dedicated native CI must supply it")
    path = Path(value).resolve()
    assert path.is_file()
    return path


def run(executable, *args):
    return subprocess.run(
        [str(executable), *map(str, args)], text=True, capture_output=True, timeout=10, check=True
    ).stdout.strip()


class UCI:
    def __init__(self, executable):
        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.lines = queue.Queue()

        def read():
            for line in self.process.stdout:
                self.lines.put(line.strip())
            self.lines.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, line):
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def until(self, prefix, seconds=5):
        end, lines = time.monotonic() + seconds, []
        while True:
            line = self.lines.get(timeout=max(0.001, end - time.monotonic()))
            assert line is not None, lines
            lines.append(line)
            if line == prefix or line.startswith(prefix + " "):
                return lines

    def close(self):
        try:
            self.send("quit")
            self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            self.reader.join(timeout=1)


def test_start_perft_and_unique_evasion(executable):
    assert len(run(executable, "--legal", START).split()) == 44
    assert run(executable, "--perft", 0, START) == "1"
    assert run(executable, "--legal", EVASION) == "e0d0"
    assert run(executable, "--legal", "4k4/3RR4/9/9/9/9/9/9/9/5K3 b") == ""


@pytest.mark.parametrize(
    "fen", ["9/9 w", START.replace(" w", " auto"), START + " - - 0 0", "4k4/9/9/9/9/9/9/9/9/4K4 w"]
)
def test_invalid_fens_are_not_silently_repaired(executable, fen):
    result = subprocess.run(
        [str(executable), "--legal", fen], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2
    assert not result.stdout.strip()


def test_search_finds_one_move_mate_and_handles_multipv(executable):
    uci = UCI(executable)
    try:
        uci.send("uci")
        assert any("RakuXQ" in line for line in uci.until("uciok"))
        uci.send("position fen " + WINNING)
        uci.send("go depth 1 movetime 2000")
        answer = uci.until("bestmove")
        assert any("score mate 1" in line for line in answer)
        assert answer[-1].split()[1] in run(executable, "--legal", WINNING).split()
        uci.send("setoption name MultiPV value 2")
        uci.send("position startpos")
        uci.send("go depth 1 movetime 2000")
        answer = uci.until("bestmove")
        assert any("multipv 2" in line for line in answer)
    finally:
        uci.close()


def test_stop_and_ready_are_responsive(executable):
    uci = UCI(executable)
    try:
        uci.send("position startpos")
        uci.send("go movetime 9000")
        uci.send("isready")
        uci.until("readyok", 2)
        uci.send("stop")
        answer = uci.until("bestmove", 3)
        assert answer[-1].split()[1] in run(executable, "--legal", START).split()
    finally:
        uci.close()


def test_bad_position_cannot_reuse_a_previous_position(executable):
    uci = UCI(executable)
    try:
        uci.send("position startpos moves e0e9")
        uci.send("go movetime 10")
        assert uci.until("bestmove")[-1] == "bestmove 0000"
    finally:
        uci.close()


def test_incremental_quantized_network_matches_python(executable, tmp_path):
    rng = np.random.default_rng(42)
    w = rng.integers(-8, 9, (1262, 32))
    b = rng.integers(10, 30, 32)
    out = rng.integers(-30, 31, 32)
    model = tmp_path / "independent-test.rknn"
    lines = ["RAKUXQ_NNUE_V1 1262 32 256", " ".join(map(str, b))]
    lines.extend(" ".join(map(str, row)) for row in w)
    lines.extend([" ".join(map(str, out)), "3"])
    model.write_text("\n".join(lines) + "\n", encoding="ascii")
    for fen in (START, EVASION, WINNING):
        accumulator = b + w[pipeline.features(fen)].sum(axis=0)
        numerator = int(np.clip(accumulator, 0, 256) @ out + 3 * 256)
        expected = int(numerator * 1000 / 65536)
        assert int(run(executable, "--network", model, "--evaluate", fen)) == expected
        assert run(executable, "--network", model, "--verify-accumulator", fen) == "ok"
    with model.open("a", encoding="ascii") as stream:
        stream.write("unexpected\n")
    with pytest.raises(subprocess.CalledProcessError):
        run(executable, "--network", model, "--evaluate", START)


def test_fen_feature_parser_rejects_overflows():
    assert len(pipeline.features(START)) == 33
    for fen in ("999/9/9/9/9/9/9/9/9/9 w", "9/9 b", START.replace(" w", " unknown")):
        with pytest.raises(ValueError):
            pipeline.features(fen)


@pytest.mark.parametrize("offset", [0, 32, 32 + 1262 * 32, 32 + 1262 * 32 + 32])
@pytest.mark.parametrize("value", ["-9223372036854775808", "9223372036854775807"])
def test_network_extreme_integers_are_rejected(executable, tmp_path, offset, value):
    tokens = ["0"] * (32 + 1262 * 32 + 32 + 1)
    tokens[offset] = value
    model = tmp_path / "out-of-range.rknn"
    model.write_text("RAKUXQ_NNUE_V1 1262 32 256\n" + " ".join(tokens), encoding="ascii")
    result = subprocess.run(
        [str(executable), "--network", str(model), "--evaluate", START],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert not result.stdout.strip()


def test_training_requires_provenance_and_disjoint_groups(tmp_path):
    data = tmp_path / "samples.jsonl"
    records = []
    # Different legal piece locations are not needed for the parser-only partition test.
    for g in range(6):
        for i in range(3):
            row = f"{i + 1}P{7 - i}" if i < 7 else "9"
            fen = f"4k4/9/9/{row}/9/9/9/9/9/3K5 {'w' if g % 2 else 'b'}"
            records.append(
                {
                    "game_id": f"g{g}",
                    "fen": fen,
                    "score_cp": 20,
                    "depth": 1,
                    "source": "rakuxq_selfplay",
                    "network_used": False,
                    "engine_version": pipeline.VERSION,
                }
            )
    data.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    now = datetime.now(UTC)
    metadata = {
        "source": "rakuxq_selfplay",
        "origin": "operator_generated_synthetic",
        "raw_customer_data": False,
        "license": "MIT",
        "dataset_sha256": pipeline.digest(data),
        "created_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(days=10)).isoformat(),
    }
    receipt = data.with_suffix(".jsonl.meta.json")
    receipt.write_text(json.dumps(metadata), encoding="utf-8")
    # All records are duplicate positions across games: leakage removal must fail closed.
    with pytest.raises(ValueError, match="insufficient distinct"):
        pipeline.dataset(data)
    metadata["raw_customer_data"] = True
    receipt.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        pipeline.dataset(data)


def test_generated_artifacts_are_not_overwritten(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        pipeline.write_json(path, {})


def test_continued_selfplay_requires_a_matching_own_training_receipt(tmp_path):
    receipt = {
        "version": pipeline.VERSION,
        "origin": "independently_trained_from_random_initialization",
        "license": "MIT",
        "model_sha256": "a" * 64,
        "dataset_sha256": "b" * 64,
        "trainer_sha256": "c" * 64,
        "features": 1262,
        "hidden": 32,
        "scale": 256,
    }
    pipeline.validate_own_model(receipt, "a" * 64)
    for name, value in (
        ("origin", "upstream_weights"),
        ("license", "unknown"),
        ("dataset_sha256", "not-a-digest"),
        ("hidden", 128),
    ):
        with pytest.raises(ValueError, match="provenance"):
            pipeline.validate_own_model({**receipt, name: value}, "a" * 64)
    with pytest.raises(ValueError, match="provenance"):
        pipeline.validate_own_model(receipt, "d" * 64)
    model = tmp_path / "untraceable.rknn"
    model.write_text("not an own trained model", encoding="ascii")
    model.with_suffix(".rknn.meta.json").write_text(json.dumps(receipt), encoding="utf-8")
    args = pipeline.argparse.Namespace(
        engine=tmp_path / "never-executed",
        network=model,
        games=2,
        plies=2,
        time_ms=1,
        seed=1,
        output=tmp_path / "never-created.jsonl",
    )
    with pytest.raises(ValueError, match="provenance"):
        pipeline.generate(args)
    assert not args.output.exists()


def test_frozen_requests_and_metadata_are_valid():
    for tool in ("contracts.py", "metadata.py"):
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / tool)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )


def test_bad_network_does_not_silently_fall_back(executable, tmp_path):
    broken = tmp_path / "broken.rknn"
    broken.write_text("RAKUXQ_NNUE_V1 1262 32 256\n0", encoding="ascii")
    uci = UCI(executable)
    try:
        uci.send("setoption name EvalFile value " + str(broken))
        uci.send("position startpos")
        uci.send("go movetime 10")
        answer = uci.until("bestmove")
        assert any("ERROR:" in line for line in answer)
        assert answer[-1] == "bestmove 0000"
    finally:
        uci.close()


def test_arena_preserves_unfinished_outcomes(executable, tmp_path):
    evidence = tmp_path / "arena.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/arena.py"),
            "--candidate",
            str(executable),
            "--reference",
            str(executable),
            "--pairs",
            "1",
            "--plies",
            "2",
            "--time-ms",
            "1",
            "--output",
            str(evidence),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(evidence.read_text(encoding="utf-8"))
    assert len(report["games"]) == 2
    assert all(game["winner"] is None and game["reason"] == "ply_limit" for game in report["games"])
    assert all(len(game["moves"]) == game["plies"] == 2 for game in report["games"])
    assert all(game["final_fen"] != game["opening"] for game in report["games"])
    assert report["completed_pairs"] == 0
    assert report["candidate_pair_score"] is None
    assert report["production_approved"] is False
    assert report["_meta"]["not_training_labels"] is True


def test_existing_api_adapter_can_run_the_candidate_without_client_changes(
    executable,
    tmp_path,
    monkeypatch,
):
    from dataclasses import replace

    sys.path.insert(0, str(ROOT.parents[1] / "apps/api/src"))
    from fastapi.testclient import TestClient
    from rakuxq_api import main
    from rakuxq_api.engines.pikafish import PikafishEngine

    model = tmp_path / "neutral-test.rknn"
    model.write_text(
        "RAKUXQ_NNUE_V1 1262 32 256\n" + "0 " * (32 + 1262 * 32 + 32 + 1), encoding="ascii"
    )
    engine = PikafishEngine(
        str(executable), str(model), version=pipeline.VERSION, hash_mb=16, command_timeout_ms=5000
    )
    monkeypatch.setattr(main, "analysis_engine", engine)
    monkeypatch.setattr(main, "settings", replace(main.settings, require_api_key=False))
    try:
        client = TestClient(main.app)
        response = client.post("/v1/solutions", json={"fen": WINNING, "time_ms": 500})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "accepted"
        assert body["analysis_status"] == "completed"
        assert body["engine"]["name"].startswith("RakuXQ")
        assert {"iccs", "from", "to", "notation"} <= body["best_move"].keys()
        assert body["best_move"]["iccs"] in run(executable, "--legal", WINNING).split()
        assert body["score"]["perspective"] == "red"
        assert body["fen"] == WINNING
        assert len(body["full_fen"].split()) == 6
        assert "KO" in body["display_text"]
        assert len(body["recommendations"]) == 1
        terminal = client.post(
            "/v1/solutions",
            json={
                "fen": "4k4/3RR4/9/9/9/9/9/9/9/5K3 b",
                "time_ms": 100,
            },
        ).json()
        assert terminal["status"] == "accepted" and terminal["analysis_status"] == "terminal"
        assert terminal["best_move"] is None
        assert "红方获胜" in terminal["display_text"]
        legacy = client.post("/v1/analyses", json={"fen": WINNING, "movetime_ms": 100})
        assert legacy.status_code == 200 and legacy.json()["status"] == "completed"
        lab = client.post(
            "/api/lab/analyses",
            headers={"Origin": "http://testserver"},
            json={"fen": WINNING, "movetime_ms": 100},
        )
        assert lab.status_code == 200 and lab.json()["status"] == "completed"
    finally:
        engine.close()
