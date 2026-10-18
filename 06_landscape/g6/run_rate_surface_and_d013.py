#!/usr/bin/env python3
"""Plan or explicitly build the Gate-6 exact rate/D013 aggregate artifact (printed; never written here).

Default/plan mode binds the pinned authorities and accepted V-14 plan hashes and prints a no-write plan.
``--run`` requires ``--reviewed`` and both V-14 plan/artifact inputs, reads the ratified Gate-5 corpus,
and prints the aggregate-only payload.  Nothing here writes a project file.
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
from research.g6.rate_surface_and_d013 import (  # noqa: E402
    ACCEPTED_V14_PLANS, AUTHORITIES, SCHEMA, RateSurfaceError, bind_authorities, build_rate_surface,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--reviewed")
    parser.add_argument("--v14-0-5-plan", type=Path)
    parser.add_argument("--v14-0-5-artifacts", type=Path)
    parser.add_argument("--v14-2x-plan", type=Path)
    parser.add_argument("--v14-2x-artifacts", type=Path)
    args = parser.parse_args()
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        print("FAIL rate surface: PYTHONDONTWRITEBYTECODE=1 required", file=sys.stderr)
        return 1
    try:
        authorities = bind_authorities()
        if not args.run:
            print(json.dumps({"schema": SCHEMA, "mode": "plan", "writes": "none", "authorities": authorities,
                              "accepted_v14_plans": dict(ACCEPTED_V14_PLANS), "d013_input": "six Gate-5 primary cells only",
                              "scientific_outputs": "intentionally absent"}, sort_keys=True, separators=(",", ":")))
            return 0
        if not all((args.reviewed, args.v14_0_5_plan, args.v14_0_5_artifacts, args.v14_2x_plan, args.v14_2x_artifacts)):
            print("FAIL rate surface: --run requires --reviewed and both V-14 plan/artifact inputs", file=sys.stderr)
            return 1
        payload = build_rate_surface(v14_0_5_plan=args.v14_0_5_plan, v14_0_5_artifacts=args.v14_0_5_artifacts,
                                     v14_2x_plan=args.v14_2x_plan, v14_2x_artifacts=args.v14_2x_artifacts,
                                     reviewed_handoff=args.reviewed)
    except RateSurfaceError as exc:
        print(f"FAIL rate surface: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
