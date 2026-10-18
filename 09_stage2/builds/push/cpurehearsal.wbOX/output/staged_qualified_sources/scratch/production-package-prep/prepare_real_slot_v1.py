"""Hosted real-instance preparation through actual WP8bV2 and WP8dV2.

The parent pins exact inputs, entry and complete import closure independently.
Standing owner authority is prospective: this derives a per-content nonce grant
only after the actual concrete release gate passes. No unknown-hash acceptance
or scientific result is fabricated here.
"""
import datetime
import hashlib
import json
from pathlib import Path
import uuid
from research.g9 import stage2_instance_preparation as instance_prep
from research.g9.wp8b import wp8b_non_synthetic_preparation_v2 as preparation
from research.g9.wp8d_production import wp8d_production_layout_v2 as layout


def prepare_slot(*, slot, root, parameters_file, expected_parameters_sha256,
                 returns_file, expected_returns_sha256, canonical_file,
                 screening_file, expected_screening_sha256, ledger_file,
                 expected_ledger_sha256, release_authority):
    root = Path(root)
    def pinned(path, pin):
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ValueError("Independent real preparation input pin mismatch")
        return raw
    # Validate actual authority/source closure before deriving a content grant.
    release = preparation._require_production_release_pinned(root=root, release_authority=release_authority)
    params = json.loads(pinned(parameters_file, expected_parameters_sha256))
    raw_returns = pinned(returns_file, expected_returns_sha256)
    canonical = json.loads(pinned(canonical_file, "c4615d9b5066597c4754a1e06d2b3a7906c218965a7d6d530cf54f75c4b5f243"))
    screening = json.loads(pinned(screening_file, expected_screening_sha256))
    ledger = json.loads(pinned(ledger_file, expected_ledger_sha256))
    if params["attempt"] != 0:
        raise ValueError("This exact first-valid campaign has only attempt0; refuse unsupported history")
    name = "stage2_" + str(slot).zfill(2)
    if type(slot) is not int or slot not in range(1, 6) or params["slot"] != slot or params["instance_id"] != name:
        raise ValueError("Exact accepted slot identity required")
    if params["label"] != "non_synthetic" or params["returns_sha256"] != expected_returns_sha256:
        raise ValueError("Actual return draw identity mismatch")
    if params["generation_ledger_file_sha256"] != expected_ledger_sha256:
        raise ValueError("Return parameters belong to a different first-valid ledger")
    if params["screening_inputs_file_sha256"] != expected_screening_sha256:
        raise ValueError("Return screening input identity mismatch")
    if params["implementation_record_content_sha256"] != release["implementation_record_content_sha256"]:
        raise ValueError("Return implementation is outside concrete release")
    accepted = [row for row in ledger["attempts"] if row["slot"] == slot and row["outcome"] == "accepted"]
    if len(accepted) != 1 or accepted[0]["attempt"] != params["attempt"] or accepted[0]["partition_sha256"] != params["partition_sha256"]:
        raise ValueError("Exact accepted attempt required")
    order = tuple(canonical["universe"]["canonical_order"])
    if list(order) != params["canonical_order"]:
        raise ValueError("Canonical asset order drift")
    labels = tuple(canonical["universe"]["sector_labels"])
    partition = params["partition"]
    sector_of = {order[index]: labels[group] for group, members in enumerate(partition) for index in members}
    instance = instance_prep.SyntheticInstance(
        instance_id=name, synthetic=False, order=order,
        mu=tuple(float.fromhex(x) for x in params["mu_hex"]),
        Sigma=tuple(tuple(float.fromhex(x) for x in row) for row in params["Sigma_hex"]),
        p=tuple(screening["prices"]), K=screening["K"], C=screening["C"], B=screening["B"],
        kappa=float(canonical["kappa_risk"]["value"]), sector_of=sector_of, sector_labels=labels, approval=None)
    digest = preparation.instance_content_sha256(instance)
    approval = dict(schema=preparation.APPROVAL_SCHEMA, status=preparation.APPROVAL_STATUS,
                    label=preparation.OWNER_APPROVAL_LABEL, scope=preparation.OWNER_APPROVAL_SCOPE,
                    approves_instance_content_sha256=digest, instance_id=name,
                    expiry=datetime.date.today().isoformat(), nonce=uuid.uuid4().hex,
                    statement=preparation.APPROVAL_STATEMENT)
    # This grant records actual scoped owner authority, not acceptance of unknown inputs.
    authority_evidence = dict(schema="decisions_os/g9_derived_preparation_authority/v1",
        instance_id=name, approves_instance_content_sha256=digest,
        owner_authority_sha256="8937dc59212931b75d7706ac91e3aa0c5621b645cbedec6d2493ee26612770e7",
        concrete_release_sha256=release["release_sha256"],
        parameters_file_sha256=expected_parameters_sha256, returns_file_sha256=expected_returns_sha256,
        scope="Prospectively owner-authorized real preparation for exact reviewed and drawn instance")
    evidence_dir = root / "operational" / name
    evidence_dir.mkdir(parents=True, exist_ok=False)
    (evidence_dir / "PREPARATION_APPROVAL.json").write_bytes(_canonical(approval))
    (evidence_dir / "AUTHORITY_DERIVATION.json").write_bytes(_canonical(authority_evidence))
    record = preparation.prepare_non_synthetic(instance, approval, root=str(root), release_authority=release_authority)
    (evidence_dir / "PREPARED_RECORD.json").write_bytes(_canonical(record))
    # The production writer revalidates actual provenance against the real instance.
    written = layout.write_instance(slot=slot, attempt=params["attempt"], instance_id=name,
        sector_partition_sha256=params["partition_sha256"], feasible_count=accepted[0]["feasible_count"],
        return_matrix=raw_returns, prepared_record=record, instance=instance,
        implementation_record_content_sha256=release["implementation_record_content_sha256"],
        mu_new=params["mu_hex"], sigma_new=params["Sigma_hex"],
        rejected_attempt_history=[], root=root, release_authority=release_authority)
    return dict(status="PREPARED_AND_WRITTEN", instance_id=name, prepared_record_sha256=record["content_sha256"],
                results=record["results"], layout=written, sweep_started=False)


def _canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()+b"\n"
