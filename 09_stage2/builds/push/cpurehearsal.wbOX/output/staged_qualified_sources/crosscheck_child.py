import sys, json, importlib.util, time, hashlib, shutil, platform, re, uuid
from pathlib import Path

root = Path(sys.argv[1])
site_dirs = json.loads(sys.argv[2])
working = Path(sys.argv[3])
sys.path[:0] = [str(root)] + site_dirs
plan_container = json.loads((root / 'operational_plan.json').read_text())

# THE ROUND-1 DEFECT, MADE IMPOSSIBLE TO REPEAT.
# The container is {module_paths, plan_dict, plan_sha256}. Every PLAN KEY lives
# in plan_dict; none of them live in the container. Round 1 subscripted the
# container and died at 5 s with KeyError: 'session_identity_path'. This assert
# names the container's exact shape and the ONE name below is the only object
# plan keys are ever read from.
EXPECTED_CONTAINER_KEYS = frozenset({'module_paths', 'plan_dict', 'plan_sha256'})
if set(plan_container) != EXPECTED_CONTAINER_KEYS:
    raise ValueError('Plan container key set differs from the exact expected '
                     'shape: got %r, expected %r'
                     % (sorted(plan_container), sorted(EXPECTED_CONTAINER_KEYS)))
plan_dict = plan_container['plan_dict']
if type(plan_dict) is not dict or not plan_dict:
    raise ValueError('The plan dict is absent or empty')
plan_sha256 = plan_container['plan_sha256']


class GpuUnavailable(RuntimeError):
    """The genuine GPU boundary: nvcc or a CUDA device is not present.

    This is the ONE refusal the offline rehearsal is expected to reach and
    stop at. It is deliberately a distinct, named type rather than a bare
    ValueError, so "we stopped where the hardware stops" is distinguishable
    from "the kernel has a bug", and so the rehearsal can assert on the type
    instead of on a message string.
    """


def load_module(name, rel_path):
    path = root / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

RECEIPT = str(working / 'CROSSCHECK_RECEIPT.json')
DIFFERENCE = str(working / 'CROSSCHECK_DIFFERENCE.json')

observed = {}
try:
    modules = {}
    for name, rel_path in plan_container['module_paths'].items():
        modules[name] = load_module(name, rel_path)
    load_module('xcheck_parent', 'scratch/production-package-prep/xcheck_parent.py')
    parent_mod = load_module(
        'xcheck_parent_r2',
        'scratch/production-package-prep/xcheck_parent_r2.py')

    # The ONE non-scientific authorization for this kernel. It is NOT read here:
    # xcheck_parent_r2.run_crosscheck_r2 validates it through
    # validate_crosscheck_authorization() against values this child re-derives,
    # and the nonce is never consumed, because consuming one would register a
    # scientific session that does not exist here.

    # THE LIVE PLATFORM PROBE, AS AN INJECTED CALLABLE.
    #
    # Round 1 ran this FIRST, which meant an offline host refused at ~1 s
    # having proven nothing -- no identity check, no seal, no pins. Round 2
    # defines it here but INJECTS it into the parent, which calls it at the one
    # documented point: after every pin, every identity check, the real seal
    # opening and the session start, and immediately before the device is
    # constructed. That is the first moment the hardware is genuinely required,
    # and it is the moment the offline rehearsal is expected to stop at.
    def live_platform_probe():
        from research.g9.cuda_qualification import stage2_cuda_core_qualification as qualification
        import subprocess, numpy as np, os
        identity = json.loads((root / plan_dict['session_identity_path']).read_bytes())
        expected = identity['qualification_identity']['platform']
        nvcc = shutil.which('nvcc')
        if not nvcc:
            raise GpuUnavailable(
                'Actual nvcc unavailable: this kernel requires the real T4 CUDA '
                'toolchain. shutil.which("nvcc") returned None on PATH=%r'
                % (os.environ.get('PATH'),))
        version = subprocess.run([nvcc, '--version'], capture_output=True, text=True, timeout=30)
        match = re.search(r'release\s+(\d+\.\d+),\s+V(\d+\.\d+\.\d+)', version.stdout)
        if version.returncode or not match:
            raise GpuUnavailable('Actual compiler version probe failed: rc=%r'
                                 % (version.returncode,))
        probe_dir = root / 'scratch' / ('xcheck-platform-probe-' + uuid.uuid4().hex)
        probe_dir.mkdir()
        probe_source = probe_dir / 'platform_probe.cu'
        probe_source.write_text(qualification.PLATFORM_PROBE)
        probe_binary = probe_dir / 'platform_probe'
        compiled = subprocess.run(
            [nvcc, *identity['qualification_identity']['compiler_flags'],
             str(probe_source), '-o', str(probe_binary)],
            capture_output=True, text=True, timeout=180)
        (probe_dir / 'COMPILE_LOG.txt').write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise GpuUnavailable('Actual live platform probe compile failed')
        observed_run = subprocess.run([str(probe_binary)], capture_output=True, text=True, timeout=60)
        if observed_run.returncode:
            raise GpuUnavailable('Actual live platform probe failed')
        seen = json.loads(observed_run.stdout)
        seen.update(nvcc_version=match.group(1) + ', V' + match.group(2),
                    python_version=platform.python_version(),
                    numpy_version=np.__version__)
        if set(seen) != {'gpu_name', 'compute_capability', 'cuda_driver_version',
                         'cuda_runtime_version', 'nvcc_version', 'python_version',
                         'numpy_version'} or any(seen[k] != expected[k] for k in seen):
            raise ValueError('Live T4/runtime/compiler differs from accepted qualification identity')
        (probe_dir / 'OBSERVED_PLATFORM.json').write_text(json.dumps(seen, sort_keys=True))
        print('Actual live T4/runtime/compiler matched qualified identity', flush=True)
        observed.update(seen)
        return seen

    start = time.monotonic()
    receipt = parent_mod.run_crosscheck_r2(
        root=root,
        plan=plan_dict,
        expected_plan_sha256=plan_sha256,
        modules=modules,
        live_platform_probe=live_platform_probe,
        receipt_path=RECEIPT,
        difference_path=DIFFERENCE,
    )
    print(json.dumps({'slot': receipt['slot'],
                      'wp3_record_content_sha256': receipt['wp3_record_content_sha256'],
                      'comparisons': receipt['comparison_counts']['counters']['comparisons'],
                      'total_row_seconds': receipt['per_row_wall_seconds']['total_row_seconds']}, indent=2), flush=True)
except Exception as exc:
    diffs = getattr(exc, 'differences', [])
    try:
        diff_body = dict(schema='decisions_os/g9_b2_wp3_crosscheck_difference/v1',
                         status='REFUSED_CROSSCHECK_DIFFERENCE_OR_REFUSAL',
                         scope=plan_dict.get('scope'),
                         slot=plan_dict.get('slot'),
                         kernel_id=plan_dict.get('kernel_id'),
                         instance_id=plan_dict.get('instance_id'),
                         prepared_record_sha256=plan_dict.get('prepared_record_content_sha256'),
                         plan_sha256=plan_sha256,
                         stage=getattr(exc, 'stage', 'child_exception'),
                         detail=type(exc).__name__ + ': ' + str(exc),
                         differences=diffs,
                         comparisons_completed=getattr(exc, 'comparisons_completed', 0),
                         gpu=observed,
                         receipt_written=Path(RECEIPT).exists(),
                         scientific_writes=[])
        diff_body['content_sha256'] = hashlib.sha256(
            json.dumps(diff_body, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()
        Path(DIFFERENCE).write_text(json.dumps(diff_body, indent=2) + '\n')
        print(json.dumps(diff_body, indent=2), flush=True)
    except Exception:
        pass
    raise
