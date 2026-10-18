#!/usr/bin/env python3
"""Read-only verifier for a pending Gate-5 per-shard digest registry."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.g5_digest_registry import (
    DigestRegistryError,
    REGISTRY_FILENAME,
    _read_json,
    validate_pending_registry,
    verify_pending_registry_against_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=ROOT / "research/g6/g5_identity_digest_registry_v1" / REGISTRY_FILENAME)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "research/g5/core_pass_output")
    args = parser.parse_args()
    try:
        registry = _read_json(args.registry)
        validate_pending_registry(registry)
        verify_pending_registry_against_corpus(registry, args.corpus_dir)
    except DigestRegistryError as exc:
        print(f"FAIL pending Gate-5 digest registry verification: {exc}", file=sys.stderr)
        return 1
    print("PASS pending Gate-5 digest registry verification")
    print(f"shards={len(registry['shards'])} status={registry['ratification_status']}")
    print("scientific_outputs=intentionally absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
