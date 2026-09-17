from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    models_dir = project_root / "models"
    manifest = json.loads((models_dir / "manifest.json").read_text(encoding="utf-8"))
    failures: list[str] = []

    for entry in manifest["files"]:
        path = models_dir / entry["local_name"]
        if not path.is_file():
            failures.append(f"missing: {path.name}")
            continue
        actual_size = path.stat().st_size
        actual_sha256 = sha256(path)
        if actual_size != entry["size"]:
            failures.append(
                f"size mismatch: {path.name}: expected {entry['size']}, got {actual_size}"
            )
        if actual_sha256 != entry["sha256"]:
            failures.append(
                f"sha256 mismatch: {path.name}: expected {entry['sha256']}, got {actual_sha256}"
            )
        if not failures:
            print(f"verified: {path.name} ({actual_size} bytes, {actual_sha256})")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"model version: {manifest['model_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
