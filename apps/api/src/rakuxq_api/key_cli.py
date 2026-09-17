from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from .api_keys import APIKeyStore


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage RakuXQ hosted API keys.")
    parser.add_argument("--database", required=True, help="SQLite key database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new API key")
    create.add_argument("--label", required=True)
    create.add_argument("--days", type=int, default=365)
    create.add_argument(
        "--output",
        help="Write the one-time plaintext result to a private file instead of stdout",
    )

    renew = subparsers.add_parser("renew", help="Extend an existing API key")
    renew.add_argument("--id", required=True)
    renew.add_argument("--days", type=int, default=365)

    revoke = subparsers.add_parser("revoke", help="Revoke an API key")
    revoke.add_argument("--id", required=True)

    subparsers.add_parser("list", help="List key metadata without plaintext keys")
    args = parser.parse_args()
    store = APIKeyStore(args.database)

    if args.command == "create":
        key_id, plaintext, expires_at = store.create(args.label, args.days)
        result = {
            "id": key_id,
            "api_key": plaintext,
            "expires_at": _iso(expires_at),
            "warning": "This is the only plaintext display; store it securely.",
        }
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if os.name != "nt":
                output.chmod(0o600)
            print(
                json.dumps(
                    {"id": key_id, "expires_at": _iso(expires_at), "output": str(output)},
                    ensure_ascii=False,
                )
            )
        else:
            print(json.dumps(result, ensure_ascii=False))
    elif args.command == "renew":
        expires_at = store.renew(args.id, args.days)
        print(json.dumps({"id": args.id, "expires_at": _iso(expires_at)}))
    elif args.command == "revoke":
        store.revoke(args.id)
        print(json.dumps({"id": args.id, "revoked": True}))
    else:
        print(json.dumps(store.list_keys(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
