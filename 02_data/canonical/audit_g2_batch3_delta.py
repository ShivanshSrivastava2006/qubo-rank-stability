#!/usr/bin/env python3
"""Independent reviewer delta-audit gate for G2 Batch 3 remediation.

This is deliberately kept apart from research/audit/: it is an
auditor-owned acceptance harness, not a replacement for the lead's assembly verifiers.
It checks the five Batch-2 remediation requirements directly against stable expected
facts and runs the two submitted G2 verifiers as supplementary evidence.  It creates
only an isolated temporary directory for its negative D005 integrity test.

This script is a bounded G2 provenance/conformance audit.  It neither computes nor
records any G3+ object and a PASS is not an U-07 closure decision.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "research" / "canonical"
ART = CANONICAL / "stage1_instance.json"
PROVENANCE = CANONICAL / "G2_PROVENANCE.md"
MANIFEST = CANONICAL / "DIGESTS.txt"
DECISIONS = ROOT / "research" / "decisions" / "DECISIONS.md"
CANONICAL_VERIFY = ROOT / "research" / "audit" / "verify_g2_canonical.py"
D005_VERIFY = ROOT / "research" / "audit" / "verify_g2_d005.py"

SUBMISSION = ROOT / "previous_work" / "QDTRINITY_sTAGE_2" / "Jupyter_Notebook_For_Submission.ipynb"
PIPELINE = ROOT / "previous_work" / "QDTRINITY_sTAGE_2" / "datasets" / "QD_Trinity_Data_Pipeline_Setup (2).ipynb"

EXPECTED_FILES = {
    SUBMISSION: "0a5a8522a9efab432cdbacea4c2dd3de8a3bdce156808585dd78a347b4374788",
    PIPELINE: "d488551ff5923a7cc97c27d06930ef7b1e0b14d37006cfd4b2595be5a028b996",
}
EXPECTED_CELLS = {
    SUBMISSION: {
        12: "ca5ec2e98c61395fc562fa7c2197e6c952e0eb4b69d4d498736a5beb6c83b8ec",
        17: "1ede5b728df9c82336ef11136875996f10363978cb135d89aef2ee34e73d6ff8",
        80: "449cb02ae612ae224ea071fa8228d618fb233aca924177c2a14c82df1eb67e25",
    },
    PIPELINE: {
        11: "7c69857a12ce7091ea59e31af2be2db67f36928c1223bc0c319d435a1d6a4b26",
        14: "479bb4047b5b05592801d21f553a47d316c391cf2724d35e03608fd45cc3aa89",
        17: "a28acaee78957e712252080c36d8f6151442c7d974a11054a8aaa2c46896eebf",
        20: "8c8f128ea67cedb78c8fc0706e08b73f455812df3a8ce436a64a94b0b57055a4",
    },
}
XNYS_CLOSURES = {
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
}

failures: list[str] = []


def check(label: str, actual: object, expected: object = True) -> bool:
    ok = actual == expected
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(f"{label}: got {actual!r}, expected {expected!r}")
    return ok


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_digest(path: Path, index: int) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    source = "".join(notebook["cells"][index]["source"])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def sessions() -> list[date]:
    first, end = date(2025, 6, 2), date(2026, 5, 31)
    closures = {date.fromisoformat(value) for value in XNYS_CLOSURES}
    result: list[date] = []
    current = first
    while current < end:
        if current.weekday() < 5 and current not in closures:
            result.append(current)
        current += timedelta(days=1)
    return result


def run(label: str, command: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    check(label, result.returncode, 0)
    if result.returncode:
        print(result.stdout)
    return result


def test_d005_rejects_bad_internal_digest() -> None:
    """A standalone D005 verifier must not evaluate a tampered artifact."""
    source = D005_VERIFY.read_text(encoding="utf-8")
    marker = 'ART = os.path.join(ROOT, "research", "canonical", "stage1_instance.json")'
    if marker not in source:
        check("D005 verifier has the expected auditable artifact binding", False)
        return
    with tempfile.TemporaryDirectory(prefix="reviewer-g2-delta-") as tmp:
        bad = Path(tmp) / "stage1_instance_bad.json"
        tampered = json.loads(ART.read_text(encoding="utf-8"))
        ticker = tampered["universe"]["canonical_order"][0]
        tampered["p_by_ticker"][ticker] += 1  # Do not recompute content_sha256.
        bad.write_text(json.dumps(tampered), encoding="utf-8")
        probe = Path(tmp) / "verify_d005_probe.py"
        probe.write_text(source.replace(marker, f"ART = {str(bad)!r}"), encoding="utf-8")
        outcome = subprocess.run([sys.executable, str(probe)], cwd=ROOT, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        check("D005 verifier rejects an artifact with a stale content digest", outcome.returncode != 0)


def main() -> None:
    print("\n[1] Independent source notebook and cell anchors")
    for path, expected in EXPECTED_FILES.items():
        check(f"{path.name} whole-file SHA-256", digest(path), expected)
    for path, cells in EXPECTED_CELLS.items():
        for index, expected in cells.items():
            check(f"{path.name} cell {index} source SHA-256", cell_digest(path, index), expected)

    artifact = json.loads(ART.read_text(encoding="utf-8"))
    artifact_text = ART.read_text(encoding="utf-8")
    provenance_text = PROVENANCE.read_text(encoding="utf-8")
    combined = artifact_text + "\n" + provenance_text

    print("\n[2] Approved decision is current, not stale")
    heading = "## Process Approval — G2 / U-07 Canonical-Input Package"
    check("decision register contains the direct approval", heading in DECISIONS.read_text(encoding="utf-8"))
    check("artifact identifies the decision-register record", heading in artifact_text)
    check("current artifact does not claim decision register is PENDING", "decision_register_entry\": \"PENDING" not in artifact_text)
    # Batch 3 must preserve the historical fact that the register was absent at initial
    # assembly, so do not reject that historical sentence.  Reject only a *current* open
    # gap and require the present record to name the now-authoritative decision entry.
    check("current provenance does not retain an OPEN approval gap", "OPEN PROVENANCE GAP" not in provenance_text)
    check("provenance identifies the current decision-register record", heading in provenance_text)

    print("\n[3] Adopted notebook evidence is pinned in the assembled record")
    for expected in [*EXPECTED_FILES.values(),
                     *(digest_value for cells in EXPECTED_CELLS.values()
                       for digest_value in cells.values())]:
        check(f"assembled record contains evidence hash {expected[:12]}", expected in combined)

    print("\n[4] Calendar derivation is explicit and mechanically corroborated")
    derived = sessions()
    check("weekdays-minus-pinned-closures count", len(derived), 250)
    check("calendar-derived first session", derived[0].isoformat(), "2025-06-02")
    check("calendar-derived terminal session", derived[-1].isoformat(), "2026-05-29")
    for closure in sorted(XNYS_CLOSURES):
        check(f"assembled record names closure {closure}", closure in combined)
    check("record labels terminal session not observed",
          artifact["provenance"]["window"]["realized_terminal_session"]["observed"], False)
    check("record labels calculation calendar-derived", "calendar-derived" in combined)
    check("record gives a weekday/half-open algorithm",
          ("weekday" in combined.lower() and "half-open" in combined.lower()))

    print("\n[5] Digest manifest is runnable from one documented base")
    run("sha256sum -c DIGESTS.txt from research/canonical", ["sha256sum", "-c", "DIGESTS.txt"], CANONICAL)

    print("\n[6] Submitted verifiers and independent D005-integrity negative test")
    run("submitted canonical verifier", [sys.executable, str(CANONICAL_VERIFY)])
    run("submitted D005 verifier", [sys.executable, str(D005_VERIFY)])
    test_d005_rejects_bad_internal_digest()

    print("\n" + "=" * 76)
    if failures:
        print("RESULT: FAIL — Batch 3 remediation is not yet independently accepted")
        for failure in failures:
            print("  - " + failure)
        print("=" * 76)
        raise SystemExit(1)
    print("RESULT: PASS — bounded Batch-3 delta-audit checks passed")
    print("        This is NOT an U-07 closure decision or G3+ authorization.")
    print("=" * 76)


if __name__ == "__main__":
    main()
