"""Read-only layout/completeness plumbing; no scientific reductions."""
from pathlib import Path
import hashlib
import json
import sys
import stage2_schema_v2 as schema


def family_root(slot_dir, family):
    staged = next((p for p in slot_dir.parents
                   if p.name == 'staged_qualified_sources'), None)
    legacy = slot_dir / 'sweep' / family
    modern = (staged / 'scratch/v4_sweep' / slot_dir.name / family
              if staged else legacy)
    found = list(dict.fromkeys(p for p in (modern, legacy) if p.is_dir()))
    if len(found) > 1:
        raise schema.Stage2AnalysisError(
            f'ambiguous family paths: {slot_dir.name}/{family}')
    return found[0] if found else modern


def inventory(root, census):
    """List every absent slot/family/range without opening coordinate records."""
    problems = []
    for number, name in enumerate(schema.SLOT_NAMES, 1):
        try:
            slot = schema.find_slot_dir(root, number)
        except schema.Stage2AnalysisError as exc:
            problems.append(f'incomplete: missing slot {name}: {exc}')
            continue
        for family in schema.BASELINE_FAMILIES:
            try:
                base = family_root(slot, family)
                if not base.is_dir():
                    problems.append(f'incomplete: missing family {name}/{family}')
                    continue
                plan_path = base / schema.PLAN_NAME
                if not plan_path.is_file():
                    problems.append(f'incomplete: missing {plan_path}')
                    continue
                plan = schema.rebuild_range_plan(
                    schema.read_sealed(plan_path, str(plan_path)),
                    census['records_per_range'])
                schema._require(plan['family'] == family and
                                plan['total_coordinates'] == census['family_census'][family]['coordinates'],
                                f'plan family/census mismatch: {plan_path}')
                for row in plan['ranges']:
                    batch = row['batch_id']
                    paths = (base / 'ranges' / batch / 'records.json',
                             base / 'ranges' / batch / 'RANGE_MANIFEST.json',
                             base / 'full_records' / (batch + '.jsonl.gz'))
                    for path in paths:
                        if not path.is_file():
                            problems.append(f'incomplete: missing {path}')
            except (schema.Stage2AnalysisError, OSError, ValueError,
                    KeyError, TypeError) as exc:
                problems.append(f'incomplete: invalid {name}/{family}: {exc}')
    return problems


def merged_evidence_path(slot, relative):
    """Bind unchanged receipt bytes across the two supported layout prefixes."""
    staged = next(p for p in slot.parents if p.name == 'staged_qualified_sources')
    for family in schema.BASELINE_FAMILIES:
        prefixes = (f'scratch/v4_sweep/{slot.name}/{family}/',
                    f'{schema.INSTANCE_ROOT}/{slot.name}/sweep/{family}/')
        for prefix in prefixes:
            if relative.startswith(prefix):
                return family_root(slot, family) / relative[len(prefix):]
    return staged / relative


def collector_evidence(merge_root, plan_path, outputs):
    """Reverify all pieces and bind their files to the collector's merged tree.

    Imports the collector's read-only verifier; never calls its CLI/download
    functions, creates a merge, or uses account credentials.
    """
    release = Path(__file__).resolve().parents[1] / 'multiacct_20261003/production_v4_release'
    sys.path.insert(0, str(release))
    from collect_verify_v4k import verify_slot, key
    plan = json.loads(Path(plan_path).read_bytes())
    proofs = {}
    for number in range(1, 6):
        entries = [e for e in plan['slots'] if e['slot'] == number]
        proof = verify_slot(entries, Path(outputs))
        slot = schema.find_slot_dir(Path(merge_root), number)
        for entry in entries:
            receipt_path = Path(outputs) / key(entry) / 'PIECE_RECEIPT.json'
            receipt = json.loads(receipt_path.read_bytes())
            for rel, evidence in receipt['output_files'].items():
                path = merged_evidence_path(slot, rel)
                if not path.is_file() or path.is_symlink():
                    raise schema.Stage2AnalysisError(f'incomplete: missing merged evidence {path}')
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                if digest.hexdigest() != evidence['sha256']:
                    raise schema.Stage2AnalysisError(f'merged evidence hash mismatch: {path}')
        prepared = schema.read_prepared_metadata(slot / 'instance/PREPARED.json', 'merged PREPARED')
        if prepared['content_sha256'] != proof['identity']['prepared_record_sha256']:
            raise schema.Stage2AnalysisError(f'merged PREPARED identity mismatch: {slot.name}')
        proofs[number] = proof
    return proofs
