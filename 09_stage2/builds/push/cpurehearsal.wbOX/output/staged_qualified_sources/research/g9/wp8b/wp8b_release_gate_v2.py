"""Candidate production release gate. No record is approved by this module.

Caller pins come from independent review; no pin is derived from the candidate.
This must be integrated into additive WP8b/WP8d/WP8c versions before use.
"""
import hashlib
import inspect
import importlib.util
import sys
import json
from pathlib import Path

OWNER_AUTHORITY_SHA256 = '8937dc59212931b75d7706ac91e3aa0c5621b645cbedec6d2493ee26612770e7'
SCHEMA = 'decisions_os/g9_wp8b_production_release/v2'
KEYS = {'schema', 'status', 'owner_authority_sha256', 'acceptance_record_sha256',
        'source_manifest_sha256', 'implementation_record_content_sha256',
        'acceptance_module_sha256'}


def validate_release(*, root, release_file, expected_release_sha256,
                     owner_authority_file, acceptance_module,
                     expected_acceptance_module_sha256, acceptance_record,
                     reviewed_acceptance_sha256, session_identity,
                     source_manifest_file, expected_source_manifest_sha256,
                     implementation_record_content_sha256):
    root = Path(root).resolve()
    def pinned_file(path, expected):
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
            raise ValueError('Refused: independent pin must be a SHA256 digest')
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Refused: authority/source escapes staged root')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Refused: independent authority/source pin mismatch')
        return raw
    raw = pinned_file(release_file, expected_release_sha256)
    record = json.loads(raw)
    if set(record) != KEYS or record['schema'] != SCHEMA or record['status'] != 'owner_authorized_conditional_release':
        raise ValueError('Refused: release shape/status')
    authority = json.loads(pinned_file(owner_authority_file, OWNER_AUTHORITY_SHA256))
    if authority.get('owner_message') != 'approved':
        raise ValueError('Refused: recorded owner authority is absent')
    expected = dict(acceptance_module_sha256=expected_acceptance_module_sha256,
                    owner_authority_sha256=OWNER_AUTHORITY_SHA256,
                    acceptance_record_sha256=reviewed_acceptance_sha256,
                    source_manifest_sha256=expected_source_manifest_sha256,
                    implementation_record_content_sha256=implementation_record_content_sha256)
    if any(record[k] != v for k, v in expected.items()):
        raise ValueError('Refused: release does not bind concrete accepted artifacts')
    manifest = json.loads(pinned_file(source_manifest_file, expected_source_manifest_sha256))
    for relative, pin in manifest['source_sha256'].items():
        if Path(relative).is_absolute():
            raise ValueError('Refused: absolute source path')
        pinned_file(root / relative, pin)
    # Load the record-bound source anew; caller monkeypatches grant no authority.
    module_path = Path(acceptance_module.__file__).resolve()
    pinned_file(module_path, record['acceptance_module_sha256'])
    relative = str(module_path.relative_to(root))
    if manifest['source_sha256'].get(relative) != record['acceptance_module_sha256']:
        raise ValueError('Refused: acceptance module is outside the pinned closure')
    name = '_release_acceptance_' + record['acceptance_module_sha256']
    if name in sys.modules:
        raise ValueError('Refused: release acceptance module name already loaded')
    spec = importlib.util.spec_from_file_location(name, module_path)
    actual = importlib.util.module_from_spec(spec)
    sys.modules[name] = actual
    try:
        spec.loader.exec_module(actual)
        for function in (actual.accept_production_identity, actual.exact_match_session):
            if (Path(inspect.getsourcefile(function)).resolve() != module_path or
                    function.__globals__ is not actual.__dict__):
                raise ValueError('Refused: acceptance functions do not belong to pinned module')
        accepted = actual.accept_production_identity(
            acceptance_record, reviewed_record_sha256=reviewed_acceptance_sha256,
            repo_root=str(root))
        actual.exact_match_session(
            session_identity, acceptance_record,
            reviewed_record_sha256=reviewed_acceptance_sha256, repo_root=str(root))
    finally:
        sys.modules.pop(name, None)
    return {'release_sha256': expected_release_sha256,
            'accepted_identity': accepted, 'source_manifest_sha256': expected_source_manifest_sha256,
            'implementation_record_content_sha256': implementation_record_content_sha256,
            'source_sha256': dict(manifest['source_sha256']),
            'acceptance_record_sha256': reviewed_acceptance_sha256}
