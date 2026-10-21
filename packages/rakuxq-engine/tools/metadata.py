#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.metadata
# Role: Verify file identity, source attribution and experimental delivery boundaries.
# Inputs: Component manifest and source files. Outputs: diagnostics and optional hash receipt.
# Provenance: Project-authored, AI-assisted. State: metadata checks, NOT legal certification.
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "SPDX-License-Identifier: MIT",
    "Copyright (c) 2026 Li Guotai",
    "Artifact-ID:",
    "Role:",
    "Inputs:",
    "Outputs:",
    "Provenance:",
    "State:",
)


def validate(root: Path = ROOT) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["production_approved"] is not False or manifest["status"] != "experimental":
        raise ValueError("This component has no approved promotion mechanism or parity evidence")
    artifacts = manifest["artifacts"]
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and (
            p.suffix in {".cpp", ".h", ".hpp", ".py", ".mjs", ".toml"} or p.name == "CMakeLists.txt"
        )
    }
    if actual != set(artifacts):
        raise ValueError(f"Source manifest drift: {sorted(actual ^ set(artifacts))}")
    seen = set()
    hashes = {}
    for relative, identity in artifacts.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Artifact escapes the component")
        content = path.read_text(encoding="utf-8")
        header = "\n".join(content.splitlines()[:14])
        if (
            any(field not in header for field in REQUIRED)
            or f"Artifact-ID: {identity}" not in header
        ):
            raise ValueError(f"Incomplete or wrong source metadata: {relative}")
        if identity in seen:
            raise ValueError("Duplicate artifact identity")
        if any(line.startswith("@@@FILE:") for line in content.splitlines()):
            raise ValueError("Transport wrapper leaked into executable source")
        seen.add(identity)
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    baseline = json.loads((root / "contracts/v1-client-baseline.json").read_text(encoding="utf-8"))
    if baseline["_meta"]["artifact_id"] != "rakuxq.native.v1-baseline":
        raise ValueError("Missing data-artifact metadata")
    return {
        "artifact_id": "rakuxq.native.source-receipt",
        "component_version": manifest["version"],
        "source_sha256": hashes,
        "metadata_valid": True,
        "production_approved": False,
        "notice": "Metadata is not legal or playing-strength certification",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = validate()
    if args.receipt:
        if args.receipt.exists():
            raise ValueError("Refusing to overwrite a prior evidence receipt")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
    print(
        f"Verified {len(receipt['source_sha256'])} source artifacts; production promotion disabled."
    )


if __name__ == "__main__":
    main()
