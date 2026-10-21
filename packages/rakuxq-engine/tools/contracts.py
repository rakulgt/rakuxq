#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.contracts
# Role: Freeze existing public request contracts before any candidate promotion.
# Inputs: Existing API OpenAPI and versioned baseline. Outputs: comparison or canonical JSON.
# Provenance: Project-authored, AI-assisted. State: regression guard; no deployment authority.
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api/src"))


def request_contract() -> dict:
    from rakuxq_api.main import app

    document = app.openapi()
    models = document["components"]["schemas"]

    def schema(value):
        if isinstance(value, list):
            return [schema(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return schema(models[value["$ref"].rsplit("/", 1)[1]])
        cleaned = {
            key: schema(item) for key, item in value.items() if key not in {"title", "description"}
        }
        if cleaned.pop("contentMediaType", None) == "application/octet-stream":
            cleaned["format"] = "binary"
        return cleaned

    result = {}
    for path in ("/v1/recognitions", "/v1/fen", "/v1/solve", "/v1/solutions", "/v1/analyses"):
        operation = document["paths"][path]["post"]
        result[path] = {
            "method": "POST",
            "body": schema(operation["requestBody"]),
            "headers": schema(operation.get("parameters", [])),
            "success_media_types": sorted(operation["responses"]["200"]["content"]),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", dest="print_contract")
    args = parser.parse_args()
    current = request_contract()
    if args.print_contract:
        print(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2))
        return
    baseline = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts/v1-client-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    if current != baseline["requests"]:
        raise SystemExit(
            "Public v1 request contract changed; explicit compatibility review required"
        )
    print("All five existing public request contracts unchanged.")


if __name__ == "__main__":
    main()
