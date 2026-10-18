#!/usr/bin/env python3
"""Explicitly emit Gate-6 pre-execution ledgers after independent review.

Without ``--write`` this command only validates the three ledgers in memory.
It never evaluates an energy, a tie set, a label, or a rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.ledgers import (
    LedgerError,
    build_d011_ledger,
    build_v14_ledger,
    canonical_bytes,
    validate_preexecution_ledger,
    verify_nested_primary_coordinates,
)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new(path: Path, payload: dict) -> None:
    """Publish one canonical file without ever replacing an existing file."""
    output_parent = path.parent
    if not output_parent.is_dir():
        raise LedgerError(f"ledger output parent does not exist: {output_parent}")
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.pending-", dir=output_parent)
        temporary = Path(temporary_name)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise LedgerError(f"refusing to overwrite existing ledger: {path}") from exc
        _fsync_directory(output_parent)
    except OSError as exc:
        raise LedgerError(f"atomic ledger publication failed for {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            if temporary is not None:
                temporary.unlink()
        except FileNotFoundError:
            pass


def _ledger_file_sha256(payload: dict) -> str:
    """The emitted file is canonical JSON with no trailing newline."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write new ledgers; omitted means validate in memory only")
    parser.add_argument("--reviewed", help="independent-review handoff identifier; required with --write")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/g6/preexecution_ledgers")
    args = parser.parse_args()
    try:
        ledgers = {
            "d011_curvature_companion.json": build_d011_ledger(),
            "v14_expansion_0_5x.json": build_v14_ledger("0.5x"),
            "v14_expansion_2x.json": build_v14_ledger("2x"),
        }
        for payload in ledgers.values():
            validate_preexecution_ledger(payload)
        verify_nested_primary_coordinates()
        if not args.write:
            print("PASS Gate-6 preexecution ledger validation (in memory; no files written)")
            return 0
        if not args.reviewed or not args.reviewed.strip():
            raise LedgerError("--write requires a non-empty --reviewed handoff identifier")
        if args.output_dir.exists():
            raise LedgerError(f"refusing to write into existing output directory: {args.output_dir}")
        try:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            os.chmod(args.output_dir, 0o755)
        except FileExistsError as exc:
            raise LedgerError(f"refusing to write into existing output directory: {args.output_dir}") from exc
        for name, payload in ledgers.items():
            _write_new(args.output_dir / name, payload)
        manifest = {"schema": "decisions_os/g6_preexecution_ledger_manifest/v1",
                    "reviewed_handoff": args.reviewed,
                    "producer_source_sha256": {
                        "src/g6/ledgers.py": hashlib.sha256((ROOT / "src/g6/ledgers.py").read_bytes()).hexdigest(),
                        "research/g6/make_preexecution_ledgers.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    },
                    "ledgers": {
                        name: {
                            "content_sha256": payload["content_sha256"],
                            "file_sha256": _ledger_file_sha256(payload),
                        }
                        for name, payload in ledgers.items()
                    },
                    "scientific_outputs": "intentionally absent"}
        manifest["content_sha256"] = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        _write_new(args.output_dir / "manifest.json", manifest)
        print("WROTE Gate-6 preexecution ledgers; scientific_outputs=intentionally absent")
        return 0
    except LedgerError as exc:
        print(f"FAIL Gate-6 preexecution ledger validation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
