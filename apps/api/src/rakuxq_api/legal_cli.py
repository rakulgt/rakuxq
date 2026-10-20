"""Expire minimal legal receipts, independently from image retention."""

from __future__ import annotations

import argparse

from .legal import ConsentStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    print(f"Expired legal receipts removed: {ConsentStore(args.database).prune()}")


if __name__ == "__main__":
    main()
