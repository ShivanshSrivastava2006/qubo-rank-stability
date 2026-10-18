"""WP1 draft schema for the Stage-2 PRODUCTION qualification identity.

Scope of this module (owner decision 2, "Bind producer files",
``research/decisions/GATE_9_WP0_D013_CUDA_PATH_AND_IDENTITY_SCOPE_OWNER_DECISION.md``,
lines 36-43; gap audit §3.0.2 and §3.1, round 3): the production identity's
source map is the 12 §A files of the qualified v1 release, plus the new additive
D013 ``+0.0`` CUDA path, plus every host-side file that shapes a scientific
record (coordinate iterator, record writer, D016 reconstruction, the §B item 1
and item 2 harnesses, and the generation-binding code).  Any change to any bound
file forces a new qualification before any further record is written.

Design rules enforced here:

* The numerical payload is produced by composing the FROZEN
  ``qualification_identity()`` of ``stage2_cuda_execution_contract.py``.  Its
  canonicalization is never re-implemented, never forked and never patched; the
  only way this module touches it is to hand it a validated platform map, the
  hashed source map and the compiler flags, and to return what it hands back.
* Image and build values are PLATFORM-REPORTED.  They are carried in a
  structurally separate sub-map that cannot be merged into the numerical
  platform, and the only admissible label in their values is the constant
  ``platform_reported``.  They are never called proof anywhere in this module.
* The transient device UUID and session ID are refused if supplied anywhere.
* Every field of the identity payload is either PINNED to one exact constant by
  ``validate_production_identity()`` or COMPARED field-by-field (and named) by
  ``exact_match()``.  ``FIELD_COVERAGE`` declares which, for every field path,
  and ``check_field_coverage()`` refuses any payload whose field paths are not
  exactly the declared ones, so a field that would be neither is a refusal
  rather than an unnamed difference.
* ``exact_match()`` is total and symmetric: it refuses on ANY difference and
  names every differing field.  There is no tolerance, no allowlist and no
  "close enough" path.

This module is a DRAFT schema builder.  It issues no identity: it only
assembles and compares one.  The identity is qualified in the WP7 dry run and
authorized only by owner acceptance.  This module authorizes nothing, touches no
GPU, no Kaggle account, no network, and no Stage-2 instance or scientific value.
"""
from __future__ import annotations
import hashlib
import json
import os
from typing import Any, Mapping, Sequence
from research.g9.cuda_qualification import stage2_cuda_execution_contract as contract
PRODUCTION_IDENTITY_SCHEMA = 'decisions_os/g9_stage2_production_qualification_identity/draft_v1'
V1_RELEASE_REL = 'research/decisions/GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json'
V1_RELEASE_SHA256 = '585da5d87908738e34c9b9858a0ef6d1c5e5cf4311dd1f6e3ba00a9d0ce6bfb9'
V1_RELEASE_KEYS = frozenset({'plan_content_sha256', 'schema', 'source_sha256', 'status'})
V1_ENGINE_ROLE = 'v1_engine'
V1_ENGINE_FILE_COUNT = 12
DRAFT_STATUS = 'DRAFT_UNQUALIFIED'
NO_AUTHORIZATION = 'NONE'
AUTHORIZATION_NOTE = 'This payload is a DRAFT schema instance. It is not a qualification, not an approval and not an authorization. The identity it describes is issued only after the WP7 non-scientific dry run and owner acceptance.'
SOURCE_MAP_SCHEMA = 'decisions_os/g9_stage2_production_source_map/draft_v1'
HASH_ALGORITHM = 'sha256'
PLATFORM_REPORTED_STATEMENT = 'Image and build values below are PLATFORM-REPORTED by Kaggle. They are not independently measured inside the GPU run, and they are not proof of the executing image. A change in any of them forces requalification.'
ROLE_TABLE: dict[str, str] = {'v1_engine': 'The 12 §A-qualified v1 CUDA core files of GATE_9_CUDA_CORE_CORRUPTION_QUALIFICATION_RELEASE.json. Hashes must match that release exactly or the build is refused. Built.', 'd013_plus_zero_cuda_path': 'The new additive CUDA +0.0 inactive-family path and its host side. Decision 1; needs its own §A corruption qualification. NOT BUILT.', 'coordinate_iterator': 'The per-coordinate 3-D iterator that produces the canonical linear coordinate order sealed by the range plan. Gap G1 / WP4. NOT BUILT.', 'record_writer': 'The production record writer: staged writes, atomic promotion, range manifests, interrupted-range discard, missing-range-only resume, final-set exact-cover audit. Gap G7 / WP4. NOT BUILT.', 'd016_reconstruction': 'D016 reconstruction and label building, host-side by design, including the c_f comparator dimension. Gaps G2 and G3 / WP4. NOT BUILT.', 'section_b1_recheck': 'The §B item 1 pre-write harness: recheck protocol, generator, ground-truth, source, platform and compiler identities, fail closed. Gap G8 / WP2. NOT BUILT.', 'section_b2_harness': 'The §B item 2 in-session full-domain comparison harness and the §B item 3 session output (pass/fail counters, platform/source identities, validation digest). Gap G9 / WP3. NOT BUILT.', 'generation_binding': 'Generation binding: the implementation record pinning generator and validator hashes plus the full runtime fingerprint. WP5. NOT BUILT.', 'per_instance_preparation': 'Per-instance Python preparation required by protocol §4 before any encoding sweep: the original feasible optimum, Lambda_ref, and the D006/D008/D010 ledgers rebuilt under the frozen formulas with instance-specific provenance. WP5b. NOT BUILT.'}
ROLES: frozenset[str] = frozenset(ROLE_TABLE)
NOT_YET_BUILT_ROLES: frozenset[str] = frozenset(ROLES) - frozenset({V1_ENGINE_ROLE})
FORBIDDEN_PATH_COMPONENTS = frozenset({'', '.', '..'})
NUMERICAL_PLATFORM_FIELDS: dict[str, str] = {'gpu_name': 'Allocated accelerator model, reported by the host (e.g. nvidia-smi name).', 'compute_capability': 'Device compute capability major.minor.', 'cuda_driver_version': 'Driver version as reported numerically by the device query.', 'cuda_runtime_version': 'CUDA runtime version reported numerically by the device query.', 'nvcc_version': 'Full nvcc version banner, exactly as the compiler prints it.', 'kaggle_image': "Kaggle image/build string. PLATFORM-REPORTED, carried numerically inside the frozen contract's platform slot because the frozen contract defines no separate channel for it; a change forces requalification.", 'python_version': 'Interpreter version of the executing host.', 'numpy_version': 'numpy.__version__ of the executing host.'}
IMAGE_BUILD_FIELDS: dict[str, str] = {'kaggle_docker_image_platform_reported': 'Value of the Kaggle image channel, exactly as the platform reports it.', 'kaggle_saved_version_build_platform_reported': 'Build identifier of the saved Kaggle kernel version, as reported.', 'kaggle_image_manifest_digest_platform_reported': 'Image manifest digest as reported by the platform. NOT an independent measurement made inside the GPU run; the provider-trust amendment removed the independent pre-write image proof.', 'kaggle_image_config_digest_platform_reported': 'Image config digest as reported by the platform. Same limit as above.', 'kaggle_kernel_version_platform_reported': 'Saved kernel version the run was recorded against, as reported.', 'runtime_build_observed_platform_reported': "Build/env values observed inside the run (CUDA_VERSION, BUILD_DATE, cuda_home, nvcc_path, ...). Observed, not independently attested by the platform's own record.", 'kaggle_environment_pinning_platform_reported': 'The Kaggle environment pinning setting, as the platform reports it. Operational mitigation for image drift: an unpinned environment can move to a new image and invalidate the identity.'}
PLATFORM_REPORTED_LABEL = 'platform_reported'
FORBIDDEN_NESTED_KEY_SUBSTRINGS: tuple[str, ...] = ('uuid', 'session_id', 'pci_bus_id', 'bus_id')
FORBIDDEN_IDENTITY_FIELDS: frozenset[str] = frozenset({'device_uuid', 'device_uuid_hex', 'uuid', 'session_id', 'pci_bus_id', 'bus_id'})
PINNED = 'pinned'
COMPARED = 'compared'
FIELD_COVERAGE: dict[str, str] = {'schema': PINNED, 'status': PINNED, 'authorization': PINNED, 'authorization_note': PINNED, 'qualification_identity.schema': PINNED, 'qualification_identity.content_sha256': PINNED, 'qualification_identity.platform.*': COMPARED, 'qualification_identity.source_sha256.*': COMPARED, 'qualification_identity.compiler_flags.*': COMPARED, 'source_map.schema': PINNED, 'source_map.hash_algorithm': PINNED, 'source_map.v1_engine_release_sha256': PINNED, 'source_map.v1_engine_plan_content_sha256': PINNED, 'source_map.bound_file_count': PINNED, 'source_map.not_yet_built_roles.*': PINNED, 'source_map.roles.*.*.path': COMPARED, 'source_map.roles.*.*.sha256': COMPARED, 'image_build_evidence.evidence_kind': PINNED, 'image_build_evidence.is_proof': PINNED, 'image_build_evidence.statement': PINNED, 'image_build_evidence.kaggle_image_reported_string': PINNED, 'image_build_evidence.fields.*': COMPARED, 'content_sha256': COMPARED}
SEQUENCE_MARK = '[any]'
WILDCARD = '*'

def _leaf_paths(value: object, prefix: tuple[str, ...]=()) -> list[tuple[str, ...]]:
    """Every LEAF path of a built payload, as a tuple of key components.

    Components are kept as a tuple rather than a dotted string because a bound
    source path such as ``research/g9/stage2_x.py`` contains dots and would be
    ambiguous once joined.  The walk is:

    * a mapping recurses once per key;
    * a non-empty sequence inserts a :data:`SEQUENCE_MARK` component and then
      recurses into its first element, so a list of entry dicts still exposes
      each entry field (``roles.v1_engine.[any].path``) instead of collapsing
      to one opaque row;
    * anything else -- including an EMPTY sequence, which no valid payload
      contains -- is a leaf.

    Sequences of differing element types cannot occur in a valid payload: each
    such list is fixed by a key-set or shape validator before this runs, so
    taking the first element describes the schema and not one particular build.
    """
    if isinstance(value, Mapping):
        paths: list[tuple[str, ...]] = []
        for key in value:
            paths.extend(_leaf_paths(value[key], prefix + (str(key),)))
        return paths
    if isinstance(value, (list, tuple)) and value:
        return _leaf_paths(value[0], prefix + (SEQUENCE_MARK,))
    return [prefix]

def _row_matches(row: tuple[str, ...], observed: tuple[str, ...]) -> bool:
    """True when a declared row pattern covers one observed leaf path.

    A ``*`` matches exactly one component -- including a :data:`SEQUENCE_MARK`.
    The lengths must agree, so a row can neither over- nor under-cover.
    """
    return len(row) == len(observed) and all((declared in (WILDCARD, component) for declared, component in zip(row, observed)))

def _row_components(row: str) -> tuple[str, ...]:
    return tuple(row.split('.'))

def check_field_coverage(payload: Mapping[str, Any]) -> None:
    """Refuse a payload whose leaf paths are not exactly the declared ones.

    This is what makes "every field is pinned or compared" a property the
    module ENFORCES rather than a claim a reader has to trust.  It partitions
    the leaf paths of a real, built payload over :data:`FIELD_COVERAGE` and
    refuses on either failure direction:

    * an observed leaf that NO declared row covers -- a field present in the
      payload but neither pinned nor compared, which is the round-1 defect;
    * a declared row that covers NO observed leaf -- a row that has quietly
      stopped describing the payload, which would hide a future gap.

    It adds no admission of its own: it can only refuse, and it substitutes for
    no other check.
    """
    observed = set(_leaf_paths(payload))
    rows = {name: _row_components(name) for name in FIELD_COVERAGE}
    uncovered = sorted(('.'.join(path) for path in observed if not any((_row_matches(row, path) for row in rows.values()))))
    unexercised = sorted((name for name, row in rows.items() if not any((_row_matches(row, path) for path in observed))))
    _require(not uncovered, 'identity payload carries field(s) that FIELD_COVERAGE declares as neither pinned nor compared: ' + ', '.join(uncovered))
    _require(not unexercised, 'FIELD_COVERAGE declares row(s) that no built payload exhibits: ' + ', '.join(unexercised))

class ProductionIdentityError(ValueError):
    """Typed refusal: the assembled scope, platform or image map is unusable."""

class ProductionIdentityMismatch(ProductionIdentityError):
    """A session identity differs from the accepted identity in named fields."""

    def __init__(self, differing_fields: Sequence[str]) -> None:
        self.differing_fields: tuple[str, ...] = tuple(differing_fields)
        super().__init__('production identity differs in fields: ' + ', '.join(self.differing_fields))

def _require(condition: object, message: str) -> None:
    if not condition:
        raise ProductionIdentityError(message)
SOURCE_MAP_INT_FIELDS = ('bound_file_count',)

def _no_non_string_leaf(value: object, label: str) -> None:
    """Refuse non-string leaves, recursively, as the frozen contract does.

    A ``bool`` is an ``int`` subclass in Python, so one ``isinstance`` test
    covers both: a float, a ``None``, a bool and any other integer are all
    refused, and only strings and containers recurse.
    """
    if isinstance(value, (float, type(None))):
        raise ProductionIdentityError(f'{label} may not contain a non-string control leaf')
    if isinstance(value, int):
        raise ProductionIdentityError(f'{label} may not contain an integer or bool control leaf')
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _no_non_string_leaf(nested, f'{label}[{key!r}]')
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _no_non_string_leaf(nested, f'{label}[...]')

def _check_forbidden_keys(value: object, label: str) -> None:
    """Refuse a transient field name anywhere in the supplied mapping.

    A single case-folded substring test is the whole rule; see
    :data:`FORBIDDEN_NESTED_KEY_SUBSTRINGS` for why a second exact-name list
    would be unreachable.
    """
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            for needle in FORBIDDEN_NESTED_KEY_SUBSTRINGS:
                _require(needle not in lowered, f'{label} key {key!r} is a forbidden transient field')
            _check_forbidden_keys(nested, f'{label}[{key!r}]')
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _check_forbidden_keys(nested, f'{label}[...]')

def _label_is_platform_reported(key: str) -> bool:
    """True when the key itself carries the platform-reported label."""
    return key.endswith('_' + PLATFORM_REPORTED_LABEL)

def _leaf_is_platform_reported(value: str) -> bool:
    """True when the value itself ends with the platform-reported marker."""
    return value.endswith(' [' + PLATFORM_REPORTED_LABEL + ']')

def _is_hex_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all((char in '0123456789abcdef' for char in value))

def load_v1_release(repo_root: str) -> dict[str, Any]:
    """Read the §A v1 release file and refuse if it is not the accepted one.

    The structural checks run BEFORE the SHA-256 pin so that each of them is
    reachable and names the defect it found; the pin then refuses anything
    that is structurally valid but is not the accepted release.  Putting the
    pin first would make every structural check dead code, because any edit to
    the file changes its hash.
    """
    _require(isinstance(repo_root, str) and repo_root, 'repo_root must be a non-empty string')
    release_path = os.path.join(repo_root, V1_RELEASE_REL)
    try:
        with open(release_path, 'rb') as handle:
            raw = handle.read()
    except OSError as exc:
        raise ProductionIdentityError(f'v1 release file is unreadable: {exc}') from exc
    try:
        release = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionIdentityError(f'v1 release file is not decodable JSON: {exc}') from exc
    _require(isinstance(release, dict) and set(release) == set(V1_RELEASE_KEYS), 'v1 release file has the wrong top-level key set')
    _require(release.get('schema') == 'decisions_os/g9_cuda_core_corruption_qualification_release/v1', 'v1 release schema mismatch')
    _require(release.get('status') == 'approved', 'v1 release is not approved')
    sources = release.get('source_sha256')
    _require(isinstance(sources, dict) and len(sources) == V1_ENGINE_FILE_COUNT, f'v1 release source_sha256 must hold exactly {V1_ENGINE_FILE_COUNT} entries')
    for path, digest_value in sources.items():
        _require(_is_hex_sha256(digest_value), f'v1 release entry {path!r} is not a sha256')
        _require(path.endswith(('.py', '.cu')), f'v1 release entry {path!r} is not a source file')
    _require(_is_hex_sha256(release.get('plan_content_sha256')), 'v1 release plan_content_sha256 is not a sha256')
    digest = hashlib.sha256(raw).hexdigest()
    _require(digest == V1_RELEASE_SHA256, f'v1 release file sha256 {digest} is not the accepted release {V1_RELEASE_SHA256}')
    return release

def _read_bound_file(repo_root: str, role: str, path: str) -> str:
    """Validate one bound path and hash it.

    The order of these checks is load-bearing and is covered one-by-one by the
    mutation table: each refusal must be reachable, and each must be
    distinguishable, or two of them would be dead code.  In particular the
    per-component traversal check is the single normalization guard — on POSIX
    every change ``os.path.normpath`` could make to such a path (a leading
    ``//``, a trailing ``/``, a ``.`` or ``..`` component, a doubled separator)
    is also a forbidden component or an absolute path, so a separate
    ``normpath`` comparison added no coverage and was removed.
    """
    _require(path == path.strip(), f'role {role!r} path {path!r} has surrounding whitespace')
    _require(not os.path.isabs(path) and (not path.startswith('/')), f'role {role!r} path {path!r} is absolute')
    _require('\\' not in path, f'role {role!r} path {path!r} contains a backslash')
    _require(':' not in path, f'role {role!r} path {path!r} contains a colon')
    _require(path.endswith('.py') or path.endswith('.cu'), f'role {role!r} path {path!r} is neither a .py nor a .cu source file')
    for component in path.split('/'):
        _require(component not in FORBIDDEN_PATH_COMPONENTS, f'role {role!r} path {path!r} has an empty or traversing component {component!r}')
    full = os.path.join(repo_root, path)
    resolved = os.path.realpath(full)
    root_resolved = os.path.realpath(repo_root)
    _require(resolved == root_resolved or resolved.startswith(root_resolved + os.sep), f'role {role!r} path {path!r} escapes the repository root')
    _require(os.path.isfile(full), f'role {role!r} path {path!r} is not an existing regular file')
    try:
        with open(full, 'rb') as handle:
            raw = handle.read()
    except OSError as exc:
        pass
    return hashlib.sha256(raw).hexdigest()

def build_source_map(repo_root: str, role_paths: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Hash every file of every role and return the source map.

    Refuses: a missing role, an unknown role, an empty role, a duplicate path
    across roles, an absolute or escaping path, and an unreadable file.  For the
    ``v1_engine`` role it additionally refuses unless the file set and every
    hash match the accepted §A release exactly.
    """
    _require(isinstance(repo_root, str) and repo_root, 'repo_root must be a non-empty string')
    _require(isinstance(role_paths, Mapping) and role_paths, 'role map must be a non-empty mapping')
    supplied = set(role_paths)
    unknown = sorted(supplied - ROLES)
    _require(not unknown, f'unknown role(s) in role map: {', '.join(unknown)}')
    missing = sorted(ROLES - supplied)
    _require(not missing, f'missing role(s) in role map: {', '.join(missing)}')
    seen: dict[str, str] = {}
    role_map: dict[str, list[dict[str, str]]] = {}
    for role in sorted(ROLES):
        paths = role_paths[role]
        _require(isinstance(paths, Sequence) and (not isinstance(paths, (str, bytes))), f'role {role!r} must map to a non-string sequence of paths')
        listed = list(paths)
        _require(listed, f'role {role!r} is empty; every role must bind at least one file')
        _require(len(set(listed)) == len(listed), f'role {role!r} repeats a path')
        for path in listed:
            _require(type(path) is str, f'role {role!r} has a non-string path entry')
            if path in seen:
                raise ProductionIdentityError(f'path {path!r} is bound by more than one role ({seen[path]!r} and {role!r})')
            seen[path] = role
        role_map[role] = [{'path': path, 'sha256': _read_bound_file(repo_root, role, path)} for path in sorted(listed)]
    v1_entries = role_map[V1_ENGINE_ROLE]
    v1_paths = [entry['path'] for entry in v1_entries]
    release = load_v1_release(repo_root)
    expected = release['source_sha256']
    _require(len(v1_paths) == V1_ENGINE_FILE_COUNT, f"role 'v1_engine' must bind exactly {V1_ENGINE_FILE_COUNT} files, got {len(v1_paths)}")
    _require(set(v1_paths) == set(expected), "role 'v1_engine' does not bind exactly the accepted §A release file set")
    mismatched = sorted((entry['path'] for entry in v1_entries if entry['sha256'] != expected[entry['path']]))
    _require(not mismatched, "role 'v1_engine' hash mismatch against the accepted §A release: " + ', '.join(mismatched))
    return {'schema': SOURCE_MAP_SCHEMA, 'v1_engine_release_sha256': V1_RELEASE_SHA256, 'v1_engine_plan_content_sha256': release['plan_content_sha256'], 'roles': role_map, 'bound_file_count': sum((len(entries) for entries in role_map.values())), 'not_yet_built_roles': sorted(NOT_YET_BUILT_ROLES), 'hash_algorithm': HASH_ALGORITHM}

def validate_numerical_platform(platform: Mapping[str, Any]) -> dict[str, str]:
    """Validate the numerical platform map and return it as the frozen contract wants."""
    _require(isinstance(platform, Mapping), 'numerical platform must be a mapping')
    _check_forbidden_keys(platform, 'numerical platform')
    _no_non_string_leaf(platform, 'numerical platform')
    _require(set(platform) == set(NUMERICAL_PLATFORM_FIELDS), 'numerical platform keys mismatch: expected exactly ' + ', '.join(sorted(NUMERICAL_PLATFORM_FIELDS)))
    out: dict[str, str] = {}
    for key in sorted(NUMERICAL_PLATFORM_FIELDS):
        value = platform[key]
        _require(type(value) is str and value.strip() == value and value, f'numerical platform field {key!r} must be a non-empty stripped string')
        out[key] = value
    return out

def validate_image_build_fields(image_build: Mapping[str, Any]) -> dict[str, str]:
    """Validate the platform-reported image/build map.

    Every field must be present, must be named with the ``_platform_reported``
    suffix, and must be a non-empty string whose value ends with the
    ``[platform_reported]`` marker.  Nothing here is ever proof.
    """
    _require(isinstance(image_build, Mapping), 'image/build map must be a mapping')
    _check_forbidden_keys(image_build, 'image/build map')
    _require(set(image_build) == set(IMAGE_BUILD_FIELDS), 'image/build keys mismatch: expected exactly ' + ', '.join(sorted(IMAGE_BUILD_FIELDS)))
    out: dict[str, str] = {}
    for key in sorted(IMAGE_BUILD_FIELDS):
        value = image_build[key]
        _require(type(value) is str and value.strip() == value and value, f'image/build field {key!r} must be a non-empty stripped string')
        _require(_leaf_is_platform_reported(value), f"image/build field {key!r} value does not carry the '[{PLATFORM_REPORTED_LABEL}]' marker")
        out[key] = value
    return out

def image_and_build_evidence(platform: Mapping[str, Any], image_build: Mapping[str, Any]) -> dict[str, Any]:
    """The recordable statement about image and build values.

    It is an explicit platform-reported label plus the fields themselves, and it
    says in words that these are reported, not proven.
    """
    numerical = validate_numerical_platform(platform)
    reported = validate_image_build_fields(image_build)
    return {'evidence_kind': PLATFORM_REPORTED_LABEL, 'is_proof': False, 'statement': PLATFORM_REPORTED_STATEMENT, 'kaggle_image_reported_string': numerical['kaggle_image'], 'fields': reported}

def build_production_identity(*, repo_root: str, role_paths: Mapping[str, Sequence[str]], platform: Mapping[str, Any], image_build: Mapping[str, Any], compiler_flags: Sequence[str]) -> dict[str, Any]:
    """Compose the frozen qualification identity with the source map and image block.

    The numerical payload is the frozen contract's own output, unchanged: the
    platform, the source hashes and the compiler flags are handed to
    ``qualification_identity()`` and its payload is embedded verbatim.  No
    canonicalization is re-implemented here.
    """
    source_map = build_source_map(repo_root, role_paths)
    numerical_platform = validate_numerical_platform(platform)
    evidence = image_and_build_evidence(platform, image_build)
    flags = list(compiler_flags)
    flat_sources: dict[str, str] = {}
    for role, entries in source_map['roles'].items():
        for entry in entries:
            flat_sources[entry['path']] = entry['sha256']
    numerical_identity = contract.qualification_identity(numerical_platform, flat_sources, flags)
    payload: dict[str, Any] = {'schema': PRODUCTION_IDENTITY_SCHEMA, 'status': DRAFT_STATUS, 'authorization': NO_AUTHORIZATION, 'authorization_note': AUTHORIZATION_NOTE, 'qualification_identity': numerical_identity, 'source_map': source_map, 'image_build_evidence': evidence}
    payload['content_sha256'] = contract.content_sha256(payload)
    return payload

def validate_source_map_shape(source_map: Mapping[str, Any]) -> None:
    """Validate the source map's structure and re-derive its bookkeeping fields.

    This runs on an untrusted payload, so nothing in it is taken on trust: the
    role set, the per-entry shape, the sorted order, the single-use path rule
    and ``bound_file_count`` are all re-derived and compared.
    """
    _require(set(source_map) == {'schema', 'v1_engine_release_sha256', 'v1_engine_plan_content_sha256', 'roles', 'bound_file_count', 'not_yet_built_roles', 'hash_algorithm'}, 'source map has the wrong key set')
    _require(source_map['schema'] == SOURCE_MAP_SCHEMA, f'source_map.schema mismatch: source map schema mismatch; {source_map['schema']!r} is not the pinned schema')
    _require(source_map['hash_algorithm'] == HASH_ALGORITHM, f'source_map.hash_algorithm mismatch: source map hash algorithm mismatch; {source_map['hash_algorithm']!r} is not the pinned algorithm')
    _require(_is_hex_sha256(source_map['v1_engine_release_sha256']), 'source map v1_engine_release_sha256 is not a lowercase sha256; the v1 release anchor must be a lowercase sha256')
    _require(_is_hex_sha256(source_map['v1_engine_plan_content_sha256']), 'source map v1_engine_plan_content_sha256 is not a lowercase sha256; the v1 plan content hash must be a lowercase sha256')
    roles = source_map['roles']
    _require(isinstance(roles, dict) and set(roles) == ROLES, 'source map does not carry exactly the fixed role set')
    total = 0
    seen: set[str] = set()
    for role in sorted(ROLES):
        entries = roles[role]
        _require(isinstance(entries, list) and entries, f'source map role {role!r} is empty or not a list')
        for entry in entries:
            _require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'}, f'source map role {role!r} has a malformed entry')
            _require(_is_hex_sha256(entry['sha256']), f'source map role {role!r} entry {entry['path']!r} is not a sha256')
            _require(entry['path'] not in seen, f'path {entry['path']!r} appears in more than one role in the source map')
            seen.add(entry['path'])
        _require([entry['path'] for entry in entries] == sorted((entry['path'] for entry in entries)), f'source map role {role!r} entries are not in sorted path order')
        total += len(entries)
    _require(type(source_map['bound_file_count']) is int and source_map['bound_file_count'] == total, f'source_map.bound_file_count does not equal the number of bound files')
    _require(source_map['not_yet_built_roles'] == sorted(NOT_YET_BUILT_ROLES), f'source_map.not_yet_built_roles does not match the fixed role table')

def validate_production_identity(payload: Any) -> str:
    """Validate a composed production identity and return its content hash.

    The embedded numerical payload is re-validated by the frozen contract's own
    ``validate_qualification_identity()``, so a non-canonical or tampered inner
    identity is refused by the frozen code, not by a re-implementation here.
    """
    _require(isinstance(payload, dict), 'production identity must be a mapping')
    expected_keys = {'schema', 'status', 'authorization', 'authorization_note', 'qualification_identity', 'source_map', 'image_build_evidence', 'content_sha256'}
    _require(set(payload) == expected_keys, 'production identity has the wrong key set')
    _require(payload['schema'] == PRODUCTION_IDENTITY_SCHEMA, f'production identity schema mismatch: payload schema is not the pinned {PRODUCTION_IDENTITY_SCHEMA!r}')
    _require(payload['status'] == DRAFT_STATUS, f'production identity status mismatch: payload status is not the pinned {DRAFT_STATUS!r}')
    _require(payload['authorization'] == NO_AUTHORIZATION, f'production identity authorization mismatch: {payload['authorization']!r} is not the pinned {NO_AUTHORIZATION!r}; an identity may not claim authorization; it authorizes nothing')
    _require(payload['authorization_note'] == AUTHORIZATION_NOTE, 'production identity authorization_note is not the pinned draft note; an identity may not describe itself as qualified, approved or authorized')
    try:
        contract.validate_qualification_identity(payload['qualification_identity'])
    except contract.CUDAExecutionContractError as exc:
        raise ProductionIdentityError(f'frozen contract refused the numerical identity: {exc}') from exc
    _check_forbidden_keys(payload['source_map'], 'source map')
    validate_source_map_shape(payload['source_map'])
    evidence = payload['image_build_evidence']
    _require(isinstance(evidence, dict), 'image/build evidence must be a mapping')
    _check_forbidden_keys(evidence, 'image/build evidence')
    _require(set(evidence) == {'evidence_kind', 'is_proof', 'statement', 'kaggle_image_reported_string', 'fields'}, 'image/build evidence has the wrong key set')
    _require(evidence['evidence_kind'] == PLATFORM_REPORTED_LABEL, f'image_build_evidence.evidence_kind is not labelled platform-reported: {evidence['evidence_kind']!r}')
    _require(evidence['is_proof'] is False, f'image_build_evidence.is_proof may not be presented as proof: it is {evidence['is_proof']!r}')
    _require(evidence['statement'] == PLATFORM_REPORTED_STATEMENT, 'image/build evidence statement is not the pinned platform-reported wording; it must state verbatim that the values are reported, not measured and not proof')
    _require(isinstance(evidence['fields'], Mapping), 'image/build evidence fields must be a mapping')
    validate_image_build_fields(evidence['fields'])
    _require(evidence['kaggle_image_reported_string'] == payload['qualification_identity']['platform']['kaggle_image'], f'image_build_evidence.kaggle_image_reported_string differs from the numerical platform slot')
    rebuilt = contract.content_sha256({k: v for k, v in payload.items() if k != 'content_sha256'})
    _require(payload['content_sha256'] == rebuilt, f"production identity content_sha256 mismatch: the payload's content_sha256 is {payload['content_sha256']!r} but the payload commits to {rebuilt!r}")
    check_field_coverage(payload)
    return rebuilt

def _platform_differences(left: Mapping[str, Any], right: Mapping[str, Any], prefix: str) -> list[str]:
    differences: list[str] = []
    for key in sorted(set(left) | set(right)):
        in_left, in_right = (key in left, key in right)
        if not in_left:
            differences.append(f'{prefix}.{key}=<absent-from-session>')
        elif not in_right:
            differences.append(f'{prefix}.{key}=<absent-from-accepted>')
        elif left[key] != right[key]:
            differences.append(f'{prefix}.{key}: {left[key]!r} != {right[key]!r}')
    return differences

def exact_match(session_identity: Mapping[str, Any], accepted_identity: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse on ANY difference; return the comparison record on exact equality.

    The rule is deliberately total: a missing field, an extra field, a changed
    flag order, one flipped byte in a bound file, one changed platform digit, or
    one changed image label is a difference, and every difference is named.  The
    comparison is symmetric, so neither argument can be the privileged one.
    """
    session_digest = validate_production_identity(session_identity)
    accepted_digest = validate_production_identity(accepted_identity)
    differences: list[str] = []
    session_numerical = session_identity['qualification_identity']
    accepted_numerical = accepted_identity['qualification_identity']
    differences.extend(_platform_differences(session_numerical['platform'], accepted_numerical['platform'], 'qualification_identity.platform'))
    differences.extend(_platform_differences(session_numerical['source_sha256'], accepted_numerical['source_sha256'], 'qualification_identity.source_sha256'))
    session_flags = session_numerical['compiler_flags']
    accepted_flags = accepted_numerical['compiler_flags']
    if list(session_flags) != list(accepted_flags):
        differences.append(f'qualification_identity.compiler_flags: {list(session_flags)!r} != {list(accepted_flags)!r}')
    if session_numerical['source_sha256'] != accepted_numerical['source_sha256']:
        changed = sorted((path for path in set(session_numerical['source_sha256']) | set(accepted_numerical['source_sha256']) if session_numerical['source_sha256'].get(path) != accepted_numerical['source_sha256'].get(path)))
        differences.append('bound file(s) differ: ' + ', '.join(changed))
    session_map = session_identity['source_map']
    accepted_map = accepted_identity['source_map']
    for field in ('schema', 'v1_engine_release_sha256', 'v1_engine_plan_content_sha256'):
        if session_map.get(field) != accepted_map.get(field):
            differences.append(f'source_map.{field}: {session_map.get(field)!r} != {accepted_map.get(field)!r}')
    for role in sorted(set(session_map['roles']) | set(accepted_map['roles'])):
        differences.extend(_platform_differences({entry['path']: entry['sha256'] for entry in session_map['roles'].get(role, [])}, {entry['path']: entry['sha256'] for entry in accepted_map['roles'].get(role, [])}, f'source_map.roles.{role}'))
    for label, identity, numerical in (('session', session_identity, session_numerical), ('accepted', accepted_identity, accepted_numerical)):
        flat = {entry['path']: entry['sha256'] for entries in identity['source_map']['roles'].values() for entry in entries}
        if flat != numerical['source_sha256']:
            changed = sorted((path for path in set(flat) | set(numerical['source_sha256']) if flat.get(path) != numerical['source_sha256'].get(path)))
            differences.append(f'{label} source_map and frozen qualification_identity disagree on bound file(s): ' + ', '.join(changed))
    differences.extend(_platform_differences(session_identity['image_build_evidence']['fields'], accepted_identity['image_build_evidence']['fields'], 'image_build_evidence.fields'))
    if session_digest != accepted_digest:
        differences.append(f'content_sha256: {session_digest} != {accepted_digest}')
    if differences:
        raise ProductionIdentityMismatch(differences)
    return {'verdict': 'exact_match', 'session_content_sha256': session_digest, 'accepted_content_sha256': accepted_digest, 'differing_fields': []}