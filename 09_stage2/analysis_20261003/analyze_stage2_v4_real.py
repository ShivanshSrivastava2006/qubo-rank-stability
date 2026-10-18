"""Owner-authorised REAL Stage-2 inference entry point (additive; v3 is not edited).

`analyze_stage2_v3.py` deliberately refuses frozen real-census inference ("real-data runs
are FORMAT tests only") so that no real values could be produced before the five production
slots were verified. This entry point lifts that one refusal only when an owner
authorisation record binds the exact inputs:

    {"authorizes": "g9_stage2_real_inference",
     "results_root": "<resolved merge root>",
     "census_content_sha256": "<census content_sha256>",
     "verify_report_sha256": "<sha256 of the passing verify_outputs_v2 report file>",
     "owner_statement": "<owner's words>", "recorded_by": "...", "recorded_at": "..."}

Everything else is v3 unchanged: it re-runs verify_outputs_v2.build_report (must be 0
failures), writes only under scratch/analysiscomplete, refuses overwrite, calls v3's
build_inference, and marks the result accepted=False / candidate (Gate-9 conditional and
image acceptance stay pending). Run through run_with_collector_b3.py like v3:

    python3 -B run_with_collector_b3.py analyze_stage2_v4_real.py --results-root <merge> \
        --piece-plan <plan> --piece-outputs <collected> --census FROZEN_CENSUS_v2c.json \
        --verify-report <VERIFY.json> --owner-authorization <AUTH.json> --out <scratch/analysiscomplete/...>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import analyze_stage2_v3 as v3
import stage2_schema_v2 as schema
from stage2_schema_v2 import Stage2AnalysisError
from export_certificates_v3 import scratch_only

AUTH_KIND = 'g9_stage2_real_inference'


def check_authorization(auth_path: Path, results_root: Path, census: dict, verify_report: Path) -> str:
    body = auth_path.read_bytes()
    auth = json.loads(body)
    expected = {
        'authorizes': AUTH_KIND,
        'results_root': str(results_root.resolve()),
        'census_content_sha256': census['content_sha256'],
        'verify_report_sha256': schema.sha256_hex(verify_report.read_bytes()),
    }
    for key, value in expected.items():
        if auth.get(key) != value:
            raise Stage2AnalysisError(f'owner authorization mismatch on {key}: {auth.get(key)!r} != {value!r}')
    if not str(auth.get('owner_statement', '')).strip():
        raise Stage2AnalysisError('owner authorization lacks owner_statement')
    return schema.sha256_hex(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Owner-authorised real Stage-2 inference (v3 logic).')
    parser.add_argument('--results-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--verify-report', required=True, type=Path)
    parser.add_argument('--owner-authorization', required=True, type=Path)
    parser.add_argument('--census', required=True, type=Path)
    parser.add_argument('--piece-plan', required=True, type=Path)
    parser.add_argument('--piece-outputs', required=True, type=Path)
    args = parser.parse_args(argv)

    scratch_only(args.out)
    census = schema.load_census_profile(args.census)
    if not schema.is_frozen_census(census):
        raise Stage2AnalysisError('v4_real is for the frozen real census only; use v3 for mock profiles')
    auth_sha = check_authorization(args.owner_authorization, args.results_root, census, args.verify_report)
    target = args.out / 'STAGE2_INFERENCE.json'
    if target.exists():
        raise Stage2AnalysisError('refusing overwrite of inference')

    from verify_outputs_v2 import build_report
    validation = build_report(args.results_root.resolve(), census, args.piece_plan, args.piece_outputs)
    if validation['failure_count']:
        sys.stderr.write(f"incomplete: verification failures={validation['failure_count']}: "
                         + validation['failures'][0]['detail'] + '\n')
        return 2

    payload = v3.build_inference(args.results_root.resolve(), census)
    payload['provenance']['validation_report_content_sha256'] = validation['content_sha256']
    payload['provenance']['verification_scope'] = validation['verification_scope']
    payload['provenance']['verify_outputs_v2_report_sha256'] = schema.sha256_hex(args.verify_report.read_bytes())
    payload['provenance']['owner_real_inference_authorization_sha256'] = auth_sha
    payload['provenance']['real_inference_entrypoint_sha256'] = schema.sha256_hex(Path(__file__).resolve().read_bytes())
    payload['accepted'] = False
    payload['status'] = 'candidate_baseline_piece_merge'
    payload['conditional_and_image_acceptance_pending'] = True

    args.out.mkdir(parents=True, exist_ok=True)
    payload['content_sha256'] = schema.content_sha256(payload)
    body = schema.canonical_bytes(payload) + b'\n'
    target.write_bytes(body)

    print('G9 Stage-2 inference (owner-authorised real run; candidate, not accepted)')
    print('=' * 72)
    print(f'output        : {target}')
    print(f'content sha256: {payload["content_sha256"]}')
    print(f'file sha256   : {schema.sha256_hex(body)}')
    for row in payload['slots']:
        disposition = row['d013_trigger_disposition']
        print(f"  slot {row['slot']} ({row['instance_id']}): D013 {disposition['disposition']}, "
              f"signs {','.join(disposition['signs'])}")
    for name, reduction in payload['cross_instance_reduction'].items():
        print(f"  {name}: count_of_five={reduction['count_of_five']}/5 "
              f"all_five={reduction['all_five']} any_one={reduction['any_one']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
