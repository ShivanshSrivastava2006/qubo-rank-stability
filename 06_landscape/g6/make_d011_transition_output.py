#!/usr/bin/env python3
"""Plan or explicitly emit the approved mechanical D011 transition output.

The default and ``--plan`` modes validate the completed D011 artifact and
print the fixed output population without creating a file or aggregating any
labels.  ``--write`` requires an independent-review handoff identifier and a
new directory below ``research/g6``.  It emits only the owner-approved label
lattices, exact integer counts, and face-adjacent unequal-label edges.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.g6.d011_transition_output import (
    DEFAULT_OUTPUT_REL,
    INPUT_REL,
    TransitionOutputError,
    build_plan,
    validate_published_transition_output,
    write_transition_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--plan", action="store_true", help="validate D011 input and print the fixed no-write plan")
    mode.add_argument("--write", action="store_true", help="emit a new reviewed mechanical transition output")
    mode.add_argument("--verify", action="store_true", help="validate a published transition output read-only")
    parser.add_argument("--reviewed", help="non-empty independent-review handoff identifier; required with --write")
    parser.add_argument("--input-dir", type=Path, default=ROOT / INPUT_REL)
    parser.add_argument("--output-dir", type=Path, default=ROOT / DEFAULT_OUTPUT_REL)
    args = parser.parse_args()
    try:
        if args.write:
            if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
                raise TransitionOutputError("PYTHONDONTWRITEBYTECODE=1 is required with --write")
            if not args.reviewed or not args.reviewed.strip():
                raise TransitionOutputError("--write requires a non-empty --reviewed handoff identifier")
            result = write_transition_output(args.output_dir, args.reviewed, args.input_dir)
        elif args.verify:
            if not args.reviewed or not args.reviewed.strip():
                raise TransitionOutputError("--verify requires the expected non-empty --reviewed handoff identifier")
            validate_published_transition_output(args.output_dir, args.input_dir, args.reviewed)
            result = {"verdict": "PASS", "output_dir": str(args.output_dir),
                      "writes": "none", "scientific_outputs": "mechanical transition representation only"}
        else:
            result = build_plan(args.input_dir)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except TransitionOutputError as exc:
        print(f"FAIL D011 transition output: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
