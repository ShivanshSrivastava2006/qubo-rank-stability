#!/usr/bin/env python3
"""G3-C — emit ADNYE-002 (D010 three-axis s-domain box) only.

Authority: the same direct human authorization of 2026-08-25 recorded in `DECISIONS.md` under
*Process Approval — Gate 3 bounded execution: CONTROLLING AUTHORIZATION TEXT (correction)*,
clause (b).  Chronology per D014 and the recorded clarification: ADNYE-002 executes after
**sidecar-verifying** a nonzero ADNYE-001, not after final resolved-branch acceptance.

This script emits exactly two files — `ADNYE-002_s_domain_box.json` and its sidecar — and
nothing else.  It computes no grid coordinate, no coefficient, no QUBO, and no result, and it
does not accept either record: full D014 branch validation and Codex's independent audit do that.

`Delta_full` is NOT re-serialized (contract §4.4): ADNYE-002 references ADNYE-001's `delta_full`
field plus its sidecar-verified record digest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DECISIONS = os.path.join(ROOT, "research/decisions/DECISIONS.md")
MEMO = os.path.join(ROOT, "research/decisions/ADNYE_OUTPUT_CONTRACT_MEMO.md")
ADNYE_DIR = os.path.join(ROOT, "research/adnye")
ONE = os.path.join(ADNYE_DIR, "ADNYE-001_Lambda_ref.json")
TWO = os.path.join(ADNYE_DIR, "ADNYE-002_s_domain_box.json")

D010_HEADING = "## D010 — Three-axis `s`-domain box (U-04)"
SECTION_END = re.compile(r"^## D[0-9]{3} — ")

# D014 / contract memo revision 6 §4.2 — exact permitted byte string, no ellipsis,
# each displayed line break one LF, no final LF.  Verified against the memo below.
D010_RULE_VERBATIM = (
    "Delta_full = max_{x in {0,1}^20} f(x) - min_{x in {0,1}^20} f(x)\n"
    "rho_box = Delta_full / Lambda_ref\n"
    "s_max = 10^(ceil(log10(rho_box)) + 1)\n"
    "s_min = 10^(floor(log10(rho_box)) - 4)\n"
    "COMMON CUBE [s_min, s_max] on ALL THREE axes: s_card, s_sector, s_budget\n"
    "m_hi = 1\n"
    "m_lo = 4"
)

M_HI = 1
M_LO = 4


def die(msg: str) -> None:
    print(f"\nFAIL: {msg}")
    sys.exit(1)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def power_of_ten(q: int) -> float:
    """10**q by exact-integer construction, cross-checked against three other routes.

    D010's rule is a power of ten at an integer exponent.  Building it from exact integer
    arithmetic avoids relying on a library `pow`; the cross-check fails closed if any route
    disagrees, so no silent 1-ulp choice is made on the resolver's behalf.
    """
    exact = float(10 ** q) if q >= 0 else 1.0 / float(10 ** (-q))
    others = (10.0 ** q, float(f"1e{q}"), math.pow(10.0, q))
    for other in others:
        if other != exact or math.copysign(1.0, other) != math.copysign(1.0, exact):
            die(f"10^{q} is route-dependent: {exact!r} vs {other!r} — fail closed")
    return exact


def main() -> int:
    print("=" * 78)
    print("G3-C — ADNYE-002 (D010 three-axis s-domain box)")
    print("=" * 78)

    # ---------------------------------------------------------------------------------
    print("\n[1] Predecessor: sidecar-verify ADNYE-001")
    if not os.path.isfile(ONE):
        die("ADNYE-001 is absent; ADNYE-002 may not be emitted")
    with open(ONE, "rb") as fh:
        one = json.loads(fh.read().decode("utf-8"))
    one_digest = sha256_hex(canonical_bytes(one))
    with open(ONE + ".sha256", "rb") as fh:
        sidecar = fh.read()
    expected = f"{one_digest}  ADNYE-001_Lambda_ref.json\n".encode("utf-8")
    if sidecar != expected:
        die("ADNYE-001 sidecar does not match its canonical record digest")
    print(f"  [OK ] ADNYE-001 sidecar verifies: {one_digest}")

    if one.get("adnye_id") != "ADNYE-001" or one.get("quantity") != "Lambda_ref":
        die("ADNYE-001 identity fields are wrong")
    if one.get("status") == "stopped_zero" or one.get("value") == 0:
        die("ADNYE-001 is on the stopped_zero branch — D008 forbids ADNYE-002. STOP.")
    if one.get("status") != "resolved":
        die(f"ADNYE-001 status must be 'resolved', found {one.get('status')!r}")
    print(f"  [OK ] status=resolved, value != 0")

    # Both records must attest the same register bytes, or their intakes disagree.
    with open(DECISIONS, "rb") as fh:
        dec_raw = fh.read()
    dec_digest = sha256_hex(dec_raw)
    if one["governing_decision_source"]["source_file_digest"] != "sha256:" + dec_digest:
        die("DECISIONS.md has changed since ADNYE-001 was emitted; re-emit ADNYE-001 first so "
            "both records attest the same register bytes")
    print(f"  [OK ] register intake still valid for ADNYE-001: {dec_digest}")

    # ---------------------------------------------------------------------------------
    print("\n[2] D010 rule string, verified byte-equal to the approved contract")
    with open(MEMO, encoding="utf-8") as fh:
        memo = fh.read()
    m = re.search(r"\*\*For ADNYE-002 / D010:\*\*\n\n```text\n(.*?)\n```", memo, re.S)
    if not m:
        die("could not locate the ADNYE-002 rule block in the contract memo")
    if m.group(1) != D010_RULE_VERBATIM:
        die("D010 rule string differs from the approved contract block — fail closed")
    print("  [OK ] governing_rule_verbatim is byte-equal to the contract's permitted string")

    # ---------------------------------------------------------------------------------
    print("\n[3] D010 box, from ADNYE-001's referenced fields only")
    Lambda_ref = one["value"]
    Delta_full = one["delta_full"]
    if not (Lambda_ref > 0.0):
        die("Lambda_ref must be positive to form rho_box")
    rho_box = Delta_full / Lambda_ref
    if not (rho_box >= 1.0):
        die(f"rho_box = {rho_box!r} < 1; F is a subset of {{0,1}}^20 so this is impossible")
    lg = math.log10(rho_box)
    q_max = math.ceil(lg) + M_HI
    q_min = math.floor(lg) - M_LO
    s_max = power_of_ten(q_max)
    s_min = power_of_ten(q_min)
    if not (0.0 < s_min <= s_max):
        die(f"box invariant violated: 0 < s_min <= s_max, got {s_min!r} / {s_max!r}")
    print(f"  Lambda_ref = {Lambda_ref!r}   Delta_full = {Delta_full!r}")
    print(f"  rho_box    = {rho_box!r}")
    print(f"  log10(rho_box) = {lg!r}  ->  q_min = floor - {M_LO} = {q_min}, "
          f"q_max = ceil + {M_HI} = {q_max}")
    print(f"  s_min = {s_min!r}   s_max = {s_max!r}   ({q_max - q_min} decades)")

    # ---------------------------------------------------------------------------------
    print("\n[4] D010 decision snapshot (capture_rule decision_section_v1)")
    lines = dec_raw.decode("utf-8").splitlines(keepends=True)
    start = None
    fence = False
    snapshot = []
    for ln in lines:
        if ln.lstrip().startswith("```"):
            fence = not fence
        if start is None:
            if not fence and ln.rstrip("\n") == D010_HEADING:
                start = True
                snapshot.append(ln)
            continue
        if not fence and SECTION_END.match(ln):
            break
        snapshot.append(ln)
    if start is None:
        die(f"could not locate {D010_HEADING!r} in DECISIONS.md")
    snapshot_text = "".join(snapshot)
    print(f"  captured {len(snapshot)} lines, {len(snapshot_text.encode('utf-8'))} bytes")

    now = datetime.now(timezone.utc)
    approved_date = "2026-08-24"          # copied verbatim from D010; no time invented
    if not (approved_date < now.strftime("%Y-%m-%d")):
        die(f"D014 §4.2.1 chronology: {approved_date} is not strictly earlier than the UTC date "
            f"{now.strftime('%Y-%m-%d')} — fail closed")
    print(f"  [OK ] chronology: {approved_date} < {now.strftime('%Y-%m-%d')} (UTC)")

    # ---------------------------------------------------------------------------------
    print("\n[5] Emit ADNYE-002")
    import numpy  # noqa: E402  — recorded for the D014 resolver field only
    record = {
        "adnye_id": "ADNYE-002",
        "quantity": "s_domain_box",
        "units": "dimensionless",
        "governing_decision": "D010",
        "governing_decision_approved_date": approved_date,
        "governing_decision_source": {
            "path": "research/decisions/DECISIONS.md",
            "section_heading": D010_HEADING,
            "source_file_digest": "sha256:" + dec_digest,
            "capture_rule": "decision_section_v1",
        },
        "governing_decision_snapshot": snapshot_text,
        "governing_decision_digest": "sha256:" + sha256_hex(snapshot_text.encode("utf-8")),
        "governing_rule_verbatim": D010_RULE_VERBATIM,
        "governing_rule_digest": "sha256:" + sha256_hex(D010_RULE_VERBATIM.encode("utf-8")),
        "execution_point": "G3.exit.resolve_box",
        "inputs": [
            {"name": "Lambda_ref", "adnye_id": "ADNYE-001", "field": "value",
             "digest": "sha256:" + one_digest},
            {"name": "Delta_full", "adnye_id": "ADNYE-001", "field": "delta_full",
             "digest": "sha256:" + one_digest},
        ],
        "status": "resolved",
        "resolved_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolver": {"python": f"CPython {sys.version.split()[0]}",
                     "numpy": numpy.__version__},
        "rho_box": rho_box,
        "s_min": s_min,
        "s_max": s_max,
    }
    if "delta_full" in record or "Delta_full" in record:
        die("contract §4.4: Delta_full must not be re-serialized in ADNYE-002")

    digest = sha256_hex(canonical_bytes(record))
    with open(TWO, "w") as fh:
        json.dump(record, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    with open(TWO + ".sha256", "w") as fh:
        fh.write(f"{digest}  ADNYE-002_s_domain_box.json\n")

    with open(TWO, "rb") as fh:
        reparsed = json.loads(fh.read().decode("utf-8"))
    if sha256_hex(canonical_bytes(reparsed)) != digest:
        die("canonical digest does not round-trip through the emitted file")
    print(f"  wrote {os.path.relpath(TWO, ROOT)}")
    print(f"  record digest = {digest}")
    print("  [OK ] sidecar written and canonical digest round-trips")

    present = sorted(os.listdir(ADNYE_DIR))
    expected_names = sorted(["ADNYE-001_Lambda_ref.json", "ADNYE-001_Lambda_ref.json.sha256",
                             "ADNYE-002_s_domain_box.json", "ADNYE-002_s_domain_box.json.sha256"])
    if present != expected_names:
        die(f"resolved-branch whitelist violation: {present}")
    print(f"  [OK ] research/adnye/ holds exactly the four resolved-branch files")

    print("\n" + "=" * 78)
    print("DONE.  ADNYE-002 is PRODUCED, NOT ACCEPTED.  Full D014 branch validation and Codex's")
    print("independent audit decide acceptance.  No grid, coefficient, QUBO, certification,")
    print("experiment, or conclusion was produced; G4+ remains unauthorized.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
