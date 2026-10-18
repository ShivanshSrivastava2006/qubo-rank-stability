#!/usr/bin/env python3
"""Build the pending, additive Gate-5 per-shard identity registry.

Without ``--write`` this performs the full read-only corpus validation and
builds the canonical registry only in memory.  ``--write`` requires a new
output directory and emits a registry still marked pending independent review
and owner ratification.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.g5_digest_registry import (
    DigestRegistryError,
    REGISTRY_FILENAME,
    build_pending_registry,
    canonical_bytes,
    validate_pending_registry,
)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new(path: Path, payload: dict) -> None:
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.pending-", dir=path.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise DigestRegistryError(f"refusing to overwrite registry: {path}") from exc
        _fsync_directory(path.parent)
    except OSError as exc:
        raise DigestRegistryError(f"atomic registry publication failed for {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="emit one new pending registry; default is in-memory only")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/g5_identity_digest_registry_v1")
    args = parser.parse_args()
    try:
        registry = build_pending_registry()
        validate_pending_registry(registry)
        if not args.write:
            print("PASS pending Gate-5 digest registry validation (in memory; no files written)")
            return 0
        if args.output_dir.exists():
            raise DigestRegistryError(f"refusing to write into existing output directory: {args.output_dir}")
        try:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            os.chmod(args.output_dir, 0o755)
        except OSError as exc:
            raise DigestRegistryError(f"unable to create registry output directory: {args.output_dir}: {exc}") from exc
        _write_new(args.output_dir / REGISTRY_FILENAME, registry)
        print("WROTE pending Gate-5 digest registry; scientific_outputs=intentionally absent")
        return 0
    except DigestRegistryError as exc:
        print(f"FAIL pending Gate-5 digest registry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
