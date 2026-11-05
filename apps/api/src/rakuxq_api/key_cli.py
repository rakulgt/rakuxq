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
        "--uses", type=int, help="Successful-call quota; absent keeps time-only keys",
    )
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
    status = subparsers.add_parser("status", help="Inspect one quota without exposing its key")
    status.add_argument("--id", required=True)
    args = parser.parse_args()
    store = APIKeyStore(args.database)

    if args.command == "create":
        output = Path(args.output).resolve() if args.output else None
        if output is not None and output.exists():
            parser.error("Private output already exists; choose a new filename")
        key_id, plaintext, expires_at = store.create(args.label, args.days, uses=args.uses)
        result = {
            "id": key_id,
            "api_key": plaintext,
            "expires_at": _iso(expires_at),
            "quota": store.quota(key_id),
            "warning": "This is the only plaintext display; store it securely.",
        }
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(result, stream, ensure_ascii=False, indent=2)
            except OSError:
                store.revoke(key_id)
                raise
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
    elif args.command == "status":
        print(json.dumps({"quota": store.quota(args.id)}))
    else:
        print(json.dumps(store.list_keys(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
