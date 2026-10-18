"""Execute the single owner-authorized Gate-5 primary named point.

This harness is deliberately not parameterized: its only permitted point is
the primary r=1 ledger centre (30, 30, 30), for both accepted encodings.  It
writes one immutable result and sidecar, then stops.  It is not a grid runner.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.g4.classification import DecodedClassifier, OriginalObjectiveService
from src.g4.energy import objective
from src.g4.instance import load_instance
from src.g4.parameters import load_coefficients, load_coordinate
from src.g5.domains import build_slack_domain_cache, prepare_active_domains
from src.g5.runner import certify_prepared_grid


RESULT_PATH = ROOT / "research/g5/G5_NAMED_POINT_RESULT.json"
SIDECAR_PATH = ROOT / "research/g5/G5_NAMED_POINT_RESULT.json.sha256"
INSTANCE_PATH = ROOT / "research/canonical/stage1_instance.json"
GROUND_TRUTH_PATH = ROOT / "research/ground_truth/G3_GROUND_TRUTH.json"
ADNYE_001_PATH = ROOT / "research/adnye/ADNYE-001_Lambda_ref.json"
LEDGER_PATH = ROOT / "research/g4/G4_PRIMARY_LEDGER.json"
WORKER_PATH = ROOT / "research/g5/verify_worker.py"

POINT_INDEX = 30
POINT_R = 1.0
POINT_COORDINATE_HEX = "0x1.999999999999ap-4"

# Accepted infrastructure, frozen inputs, and the governing owner decision.
# Any mismatch quarantines the run before primary-domain construction.
EXPECTED_SHA256 = {
    "research/canonical/stage1_instance.json": "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243",
    "research/ground_truth/G3_GROUND_TRUTH.json": "13229ad17e0a109731c0682c1ce22a820ea3ca412364fd882a897d036fc475db",
    "research/adnye/ADNYE-001_Lambda_ref.json": "9473c205a002697492c75af9ab694920b6bf822b38b5bd5c58f8f240ca66116a",
    "research/adnye/ADNYE-002_s_domain_box.json": "9d634366be5c737dbefd1ade5be5f76ceb960c9af4fa4b3d4cbc5ab3b35a2992",
    "research/g4/G4_PRIMARY_LEDGER.json": "9f1277cb642697786f8a7216382199e376c28a40e272d1d7039c5c693c4dad71",
    "src/g4/instance.py": "645419374fd30891c2f9ff14d030ed65a032d52d8fe88fab068ad23417b58187",
    "src/g4/parameters.py": "cbbdebbe44b9af0d47fa1d5da7e00303e492d70d21abd696e6bdd5a4cd5be97c",
    "src/g4/classification.py": "9a35f0829de8216ff47e6b1dd257e5dbc5a0dd96c9a051dd058bfe54bd672da1",
    "src/g4/energy.py": "0ba83c0d33e0d2996352370e26bf0e782002ec49cb79e1628b74a2a74dd5fa11",
    "src/g5/domains.py": "89d3b1cadf660ec7ea4a127af09a73073afb03d5c78a74e7a15b5808999dadf7",
    "src/g5/certify.py": "018b0a67ae1d1fdf8cf797cd38296ed0a98ec3bd0d2e5c1124dc51e36e614d64",
    "src/g5/runner.py": "262fda09db033cc3195c8447042836274b195907b772f827f3f21a9311f963cd",
    "research/g5/verify_worker.py": "1ab5e0113829795607a3f5ded4330b5f8624a1ff59d44679ad8eb5c5dce14d7a",
    "research/g5/worker_self_test.json": "3653b6272c14acb36f4f1e79138c06e1f0d1d40f54defa63a8b491fc714f5730",
    "research/decisions/DECISIONS.md": "d746f2711993406963af049faf65f340adb95daaea3eea699c5cc13cbddf9984",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot() -> dict[str, str]:
    observed = {}
    for relative, expected in EXPECTED_SHA256.items():
        path = ROOT / relative
        require(path.is_file(), f"required artifact missing: {relative}")
        digest = sha256(path)
        require(digest == expected, f"snapshot mismatch for {relative}: {digest}")
        observed[relative] = digest
    return observed


def worker_gate() -> list[dict[str, object]]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = (
        [sys.executable, str(WORKER_PATH)],
        [sys.executable, "-O", str(WORKER_PATH)],
    )
    records = []
    for command in commands:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed = time.perf_counter() - started
        require(completed.returncode == 0, f"worker gate failed: {completed.stderr}")
        require(completed.stdout.strip() == "PASS worker self test", "unexpected worker-gate output")
        records.append(
            {
                "command": " ".join(command),
                "exit_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "elapsed_seconds": elapsed,
                "elapsed_seconds_hex": elapsed.hex(),
            }
        )
    return records


def hard_feasible(instance, x: tuple[int, ...]) -> bool:
    require(len(x) == len(instance.tickers), "decoded width mismatch")
    require(all(type(bit) is int and bit in (0, 1) for bit in x), "decoded state is not binary")
    if sum(x) != instance.K:
        return False
    for members in instance.sectors:
        if sum(x[index] for index in members) > instance.C:
            return False
    spend = +0.0
    for index, bit in enumerate(x):
        spend = spend + instance.prices[index] * float(bit)
    return spend <= instance.B


def encoded_state(state, encoding: str, instance) -> dict[str, object]:
    if encoding == "unbalanced":
        x = state
        payload = {"x_bits": list(x)}
    elif encoding == "slack":
        x, y = state
        payload = {"x_bits": list(x), "auxiliary_bits": list(y)}
    else:
        raise RuntimeError("unknown encoding")
    payload["selected_tickers"] = [
        ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit
    ]
    return payload


def decoded_state(x: tuple[int, ...], classifier, f_star: float, instance) -> dict[str, object]:
    return {
        "x_bits": list(x),
        "selected_tickers": [
            ticker for ticker, bit in zip(instance.tickers, x, strict=True) if bit
        ],
        "objective": objective(instance, x),
        "objective_hex": objective(instance, x).hex(),
        "hard_feasible": hard_feasible(instance, x),
        "label": classifier.label(x, f_star),
    }


def cpu_flags() -> list[str]:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.is_file():
        return []
    for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("flags") and ":" in line:
            return sorted(line.split(":", 1)[1].split())
    return []


def main() -> int:
    require(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 is required")
    require(not RESULT_PATH.exists() and not SIDECAR_PATH.exists(), "named-point output already exists")

    overall_start = time.perf_counter()
    snapshot = verify_snapshot()
    worker_records = worker_gate()

    instance = load_instance(INSTANCE_PATH)
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    adnye_001 = json.loads(ADNYE_001_PATH.read_text(encoding="utf-8"))
    f_star = float(ground_truth["results"]["f_star"])
    lambda_ref = float(ground_truth["results"]["Lambda_ref"])
    require(lambda_ref == float(adnye_001["value"]), "Lambda_ref authorities disagree")

    coordinate = load_coordinate(LEDGER_PATH, POINT_INDEX)
    require(coordinate.hex() == POINT_COORDINATE_HEX, "named coordinate differs from owner declaration")
    coefficients = load_coefficients(
        LEDGER_PATH, POINT_INDEX, POINT_INDEX, POINT_INDEX
    )
    classifier = DecodedClassifier(
        OriginalObjectiveService(lambda x: objective(instance, x), lambda_ref),
        lambda x: hard_feasible(instance, x),
    )

    cache_start = time.perf_counter()
    slack_cache = build_slack_domain_cache(instance, coefficients)
    cache_seconds = time.perf_counter() - cache_start

    preparation_start = time.perf_counter()
    domains = prepare_active_domains(instance, slack_cache)
    preparation_seconds = time.perf_counter() - preparation_start

    certification_start = time.perf_counter()
    certifications = certify_prepared_grid(
        domains=domains,
        coefficient_points=(coefficients,),
        lambda_ref=lambda_ref,
        f_star=f_star,
        classifier=classifier,
    )
    certification_seconds = time.perf_counter() - certification_start
    require(len(certifications) == 1, "named-point runner returned an unexpected number of points")
    record = certifications[0]

    encodings = {}
    for name, result in (("unbalanced", record.unbalanced), ("slack", record.slack)):
        h_min, t_e, x_e, set_label = result
        atomic = [decoded_state(x, classifier, f_star, instance) for x in x_e]
        require(set_label == classifier.label_set(x_e, f_star), f"{name} set label mismatch")
        require(all(item["hard_feasible"] == (item["label"] != "C") for item in atomic),
                f"{name} feasibility/label mismatch")
        encodings[name] = {
            "H_E_min": h_min,
            "H_E_min_hex": h_min.hex(),
            "T_E_size": len(t_e),
            "T_E": [encoded_state(state, name, instance) for state in t_e],
            "X_E_size": len(x_e),
            "X_E": atomic,
            "set_label": set_label,
        }

    script_path = Path(__file__).resolve()
    peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    total_seconds = time.perf_counter() - overall_start
    payload = {
        "schema": "decisions_os/g5_single_named_point/v1",
        "status": "PRODUCED — pending controlling independent review; Gate 5 remains open",
        "authority": {
            "approved_date": "2026-08-27",
            "decision_file_sha256": snapshot["research/decisions/DECISIONS.md"],
            "scope": "exactly one primary r=1 point at ledger indices (30,30,30), both encodings",
        },
        "point": {
            "r": POINT_R,
            "indices": {"cardinality": POINT_INDEX, "sector": POINT_INDEX, "budget": POINT_INDEX},
            "coordinates": {"cardinality": coordinate, "sector": coordinate, "budget": coordinate},
            "coordinate_hex": {
                "cardinality": coordinate.hex(), "sector": coordinate.hex(), "budget": coordinate.hex()
            },
        },
        "inputs": {
            "Lambda_ref": lambda_ref,
            "Lambda_ref_hex": lambda_ref.hex(),
            "f_star": f_star,
            "f_star_hex": f_star.hex(),
            "coefficients_hex": {name: value.hex() for name, value in coefficients.__dict__.items()},
        },
        "domain": {
            "unbalanced_states": len(domains.unbalanced),
            "slack_states": len(domains.slack),
            "slack_logical_sha256": slack_cache.logical_sha256(),
            "slack_packed_bytes": slack_cache.packed_bytes,
        },
        "encodings": encodings,
        "worker_gate": worker_records,
        "timing": {
            "slack_cache_seconds": cache_seconds,
            "domain_preparation_seconds": preparation_seconds,
            "certification_seconds": certification_seconds,
            "total_seconds": total_seconds,
        },
        "resources": {
            "peak_rss_kib": peak_rss_kib,
            "peak_rss_mib": peak_rss_kib / 1024.0,
        },
        "platform": {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "python_compiler": platform.python_compiler(),
            "python_build": list(platform.python_build()),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "libc": list(platform.libc_ver()),
            "cpu_flags": cpu_flags(),
        },
        "artifact_sha256": {
            **snapshot,
            "research/g5/run_named_point.py": sha256(script_path),
        },
        "explicit_non_actions": [
            "no additional grid point",
            "no grid sweep or full core pass",
            "no Rust-produced primary value",
            "no Gate-6 work",
            "no interpretation or conclusion",
            "no Gate-5 acceptance or exit",
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    with RESULT_PATH.open("xb") as handle:
        handle.write(encoded)
    file_digest = hashlib.sha256(encoded).hexdigest()
    with SIDECAR_PATH.open("xb") as handle:
        handle.write(f"{file_digest}  {RESULT_PATH.name}\n".encode("ascii"))

    print(f"PASS produced {RESULT_PATH.relative_to(ROOT)}")
    print(f"file_sha256={file_digest}")
    print(f"content_sha256={payload['content_sha256']}")
    print(f"unbalanced H_min={encodings['unbalanced']['H_E_min_hex']} T_E={encodings['unbalanced']['T_E_size']} X_E={encodings['unbalanced']['X_E_size']} label={encodings['unbalanced']['set_label']}")
    print(f"slack H_min={encodings['slack']['H_E_min_hex']} T_E={encodings['slack']['T_E_size']} X_E={encodings['slack']['X_E_size']} label={encodings['slack']['set_label']}")
    print(f"elapsed_seconds={total_seconds:.6f} peak_rss_mib={peak_rss_kib / 1024.0:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
