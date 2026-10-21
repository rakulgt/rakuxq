#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.pipeline
# Role: Offline selfplay collection, small NNUE training and bounded candidate experiments.
# Inputs: Independently built engine, generated JSONL, seed. Outputs: model and evidence files.
# Provenance: Project-authored, AI-assisted; no imported engine weights or customer records.
# State: experimental; training loss is NOT proof of playing strength or production approval.
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

PIECES = "KABNRCPkabnrcp"
FEATURES, HIDDEN, SCALE = 1262, 32, 256
VERSION = "0.1.0-experimental"


def features(fen: str) -> list[int]:
    fields = fen.split()
    if len(fields) not in (2, 6) or fields[1] not in ("w", "b"):
        raise ValueError("FEN must have two or six fields and w/b")
    rows = fields[0].split("/")
    if len(rows) != 10:
        raise ValueError("FEN must have ten ranks")
    result = []
    for row, rank in enumerate(rows):
        file = 0
        for symbol in rank:
            if symbol in "123456789":
                file += int(symbol)
            elif symbol in PIECES and file < 9:
                result.append(PIECES.index(symbol) * 90 + row * 9 + file)
                file += 1
            else:
                raise ValueError("invalid FEN symbol or rank")
            if file > 9:
                raise ValueError("oversized FEN rank")
        if file != 9:
            raise ValueError("FEN rank must have nine squares")
    result.append(1260 if fields[1] == "w" else 1261)
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_output(path: Path) -> None:
    if path.exists():
        raise ValueError(f"Refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, content: dict) -> None:
    checked_output(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(content, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def validate_own_model(receipt: dict, model_sha256: str) -> None:
    if (
        receipt.get("version") != VERSION
        or receipt.get("origin") != "independently_trained_from_random_initialization"
        or receipt.get("license") != "MIT"
        or receipt.get("model_sha256") != model_sha256
        or receipt.get("features") != FEATURES
        or receipt.get("hidden") != HIDDEN
        or receipt.get("scale") != SCALE
    ):
        raise ValueError("unsupported or inconsistent independent model provenance")
    for name in ("model_sha256", "dataset_sha256", "trainer_sha256"):
        value = receipt.get(name)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("invalid independent model provenance digest")


def generate(args: argparse.Namespace) -> None:
    if not 2 <= args.games <= 10000 or not 2 <= args.plies <= 512 or not 1 <= args.time_ms <= 1000:
        raise ValueError("generation budget outside limits")
    checked_output(args.output)
    metadata = args.output.with_suffix(args.output.suffix + ".meta.json")
    checked_output(metadata)
    command = [
        str(args.engine.resolve()),
    ]
    network_receipt = None
    network_sha256 = None
    receipt_sha256 = None
    if args.network:
        receipt_path = args.network.with_suffix(args.network.suffix + ".meta.json")
        network_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        network_sha256 = digest(args.network)
        validate_own_model(network_receipt, network_sha256)
        receipt_sha256 = digest(receipt_path)
        command.extend(["--network", str(args.network.resolve())])
    command.extend(
        [
            "--selfplay",
            str(args.games),
            str(args.plies),
            str(args.time_ms),
            str(args.seed),
        ]
    )
    # No inherited customer data, network, API key or server database is involved.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        subprocess.run(
            command,
            stdout=stream,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=min(7200, 30 + args.games * args.plies * (args.time_ms + 50) / 1000),
        )
    current = datetime.now(UTC)
    write_json(
        metadata,
        {
            "artifact_id": "rakuxq.dataset.synthetic-selfplay",
            "version": VERSION,
            "source": "rakuxq_selfplay",
            "origin": "operator_generated_synthetic",
            "license": "MIT",
            "raw_customer_data": False,
            "engine_sha256": digest(args.engine),
            "dataset_sha256": digest(args.output),
            "seed": args.seed,
            "games": args.games,
            "plies_limit": args.plies,
            "search_ms": args.time_ms,
            "teacher": "independent_rakuxq_nnue_search"
            if args.network
            else "independent_rakuxq_handcrafted_search",
            "network_used": bool(args.network),
            "source_network_sha256": network_sha256,
            "source_network_receipt_sha256": receipt_sha256,
            "source_network_receipt": network_receipt,
            "not_ground_truth": True,
            "production_approved": False,
            "created_at": current.isoformat(),
            "expires_at": (current + timedelta(days=3 * 365)).isoformat(),
        },
    )
    print(json.dumps({"generated": str(args.output), "production_approved": False}))


def dataset(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    meta = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text(encoding="utf-8"))
    if (
        meta.get("source") != "rakuxq_selfplay"
        or meta.get("origin") != "operator_generated_synthetic"
        or meta.get("raw_customer_data") is not False
        or meta.get("license") != "MIT"
        or meta.get("dataset_sha256") != digest(path)
    ):
        raise ValueError("dataset provenance is missing, inconsistent or unsupported")
    created, expiry = (datetime.fromisoformat(meta[name]) for name in ("created_at", "expires_at"))
    if (
        created.tzinfo is None
        or expiry.tzinfo is None
        or created > datetime.now(UTC)
        or expiry <= datetime.now(UTC)
        or expiry - created > timedelta(days=3 * 365)
    ):
        raise ValueError("dataset retention receipt is invalid or expired")
    network_used = meta.get("network_used", False)
    if type(network_used) is not bool:
        raise ValueError("invalid source network flag")
    if network_used:
        if meta.get("teacher") != "independent_rakuxq_nnue_search":
            raise ValueError("unsupported selfplay teacher")
        validate_own_model(
            meta.get("source_network_receipt") or {}, meta.get("source_network_sha256")
        )
    elif meta.get("source_network_sha256") or meta.get("source_network_receipt"):
        raise ValueError("inconsistent baseline selfplay provenance")
    elif meta.get("teacher", "independent_rakuxq_handcrafted_search") != (
        "independent_rakuxq_handcrafted_search"
    ):
        raise ValueError("unsupported baseline teacher")
    examples = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                record = json.loads(line)
                if (
                    record.get("source") != "rakuxq_selfplay"
                    or record.get("network_used") is not network_used
                    or record.get("engine_version") != VERSION
                    or record.get("depth", 0) < 1
                ):
                    raise ValueError("only source-traceable independent selfplay is supported")
                score = record.get("score_cp")
                if type(score) is not int or not -30000 <= score <= 30000:
                    raise ValueError("invalid search label")
                examples.append(record)
                if len(examples) > 20000:
                    raise ValueError("first-stage in-memory dataset limit is 20000 rows")
    # Split by whole game before deduplication. Any position shared across the split is removed
    # from training, so duplicated opening screenshots cannot leak into a held-out position.
    games = sorted({r["game_id"] for r in examples})
    if len(games) < 2:
        raise ValueError("at least two complete game groups are required")
    held_out = {g for i, g in enumerate(games) if i % 5 == 0}
    validation_fens = {r["fen"] for r in examples if r["game_id"] in held_out}
    unique: dict[str, dict] = {}
    for r in examples:
        if r["game_id"] not in held_out and r["fen"] in validation_fens:
            continue
        unique.setdefault(r["fen"], r)
    records = list(unique.values())
    x = np.zeros((len(records), FEATURES), dtype=np.float32)
    y = np.empty(len(records), dtype=np.float32)
    test = np.empty(len(records), dtype=bool)
    for i, record in enumerate(records):
        x[i, features(record["fen"])] = 1
        # These are bootstrap labels from a weak search, not verified optimal moves.
        y[i] = np.clip(record["score_cp"], -2000, 2000) / 1000
        test[i] = record["game_id"] in held_out
    if min(np.count_nonzero(test), np.count_nonzero(~test)) < 2:
        raise ValueError("insufficient distinct training/validation positions")
    return x, y, test, meta


def train(args: argparse.Namespace) -> None:
    if not 1 <= args.epochs <= 1000 or not 0 < args.learning_rate <= 0.1:
        raise ValueError("invalid training budget")
    checked_output(args.output)
    receipt = args.output.with_suffix(args.output.suffix + ".meta.json")
    checked_output(receipt)
    x, y, test, source = dataset(args.data)
    rng = np.random.default_rng(args.seed)
    w = rng.normal(0, 0.04, (FEATURES, HIDDEN)).astype(np.float32)
    b = np.full(HIDDEN, 0.25, dtype=np.float32)
    out = rng.normal(0, 0.04, HIDDEN).astype(np.float32)
    out_b = np.float32(0)
    best = None
    best_loss = float("inf")
    train_x, train_y = x[~test], y[~test]
    for _ in range(args.epochs):
        for indices in np.array_split(rng.permutation(len(train_x)), max(1, len(train_x) // 128)):
            batch, target = train_x[indices], train_y[indices]
            pre = batch @ w + b
            hidden = np.clip(pre, 0, 1)
            error = 2 * (hidden @ out + out_b - target) / len(indices)
            gradient = error[:, None] * out[None, :] * ((pre > 0) & (pre < 1))
            out_gradient = hidden.T @ error
            w -= args.learning_rate * (batch.T @ gradient)
            b -= args.learning_rate * gradient.sum(axis=0)
            out -= args.learning_rate * out_gradient
            out_b -= args.learning_rate * error.sum()
            np.clip(w, -100, 100, out=w)
            np.clip(out, -100, 100, out=out)
        predicted = np.clip(x[test] @ w + b, 0, 1) @ out + out_b
        loss = float(np.mean((predicted - y[test]) ** 2))
        if np.isfinite(loss) and loss < best_loss:
            best_loss = loss
            best = w.copy(), b.copy(), out.copy(), float(out_b)
    if best is None:
        raise ValueError("training did not produce finite parameters")
    w, b, out, out_b = best
    qw = np.rint(w * SCALE).astype(np.int64)
    qb = np.rint(b * SCALE).astype(np.int64)
    qo = np.rint(out * SCALE).astype(np.int64)
    qob = round(out_b * SCALE)
    if (
        max(np.max(np.abs(qw)), np.max(np.abs(qo))) > 32767
        or max(np.max(np.abs(qb)), abs(qob)) > 1000000
    ):
        raise ValueError("quantization overflow")
    with args.output.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(f"RAKUXQ_NNUE_V1 {FEATURES} {HIDDEN} {SCALE}\n")
        for row in [qb, *qw, qo, [qob]]:
            stream.write(" ".join(str(int(v)) for v in row) + "\n")
    quantized = (np.clip(x[test].astype(np.int64) @ qw + qb, 0, SCALE) @ qo + qob * SCALE) / (
        SCALE * SCALE
    )
    write_json(
        receipt,
        {
            "artifact_id": "rakuxq.model.nnue-v1",
            "version": VERSION,
            "license": "MIT",
            "origin": "independently_trained_from_random_initialization",
            "model_sha256": digest(args.output),
            "dataset_sha256": source["dataset_sha256"],
            "trainer_sha256": digest(Path(__file__)),
            "parent_model_sha256": source.get("source_network_sha256"),
            "source_engine_sha256": source.get("engine_sha256"),
            "created_at": datetime.now(UTC).isoformat(),
            "seed": args.seed,
            "epochs": args.epochs,
            "features": FEATURES,
            "hidden": HIDDEN,
            "scale": SCALE,
            "training_positions": int(np.count_nonzero(~test)),
            "validation_positions": int(np.count_nonzero(test)),
            "validation_mse": best_loss,
            "quantized_validation_mse": float(np.mean((quantized - y[test]) ** 2)),
            "playing_strength_verified": False,
            "production_approved": False,
        },
    )
    print(
        json.dumps(
            {
                "model": str(args.output),
                "validation_mse": best_loss,
                "playing_strength_verified": False,
                "production_approved": False,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--engine", type=Path, required=True)
    gen.add_argument("--network", type=Path, help="Own model with a matching training receipt only")
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--games", type=int, default=8)
    gen.add_argument("--plies", type=int, default=48)
    gen.add_argument("--time-ms", type=int, default=10)
    gen.add_argument("--seed", type=int, default=20261021)
    fit = sub.add_parser("train")
    fit.add_argument("--data", type=Path, required=True)
    fit.add_argument("--output", type=Path, required=True)
    fit.add_argument("--epochs", type=int, default=20)
    fit.add_argument("--learning-rate", type=float, default=0.01)
    fit.add_argument("--seed", type=int, default=20261021)
    args = parser.parse_args()
    (generate if args.command == "generate" else train)(args)


if __name__ == "__main__":
    main()
