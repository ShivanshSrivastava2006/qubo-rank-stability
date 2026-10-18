"""Fast CPU fixtures for WP7b packaging, closure, and refusal gates."""
from __future__ import annotations
import ast, base64, hashlib, json, os, subprocess, sys, tempfile, runpy, importlib.util, contextlib, io, shutil, lzma
import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / 'research/g9/kaggle_wp7b/build_wp7b_bundle.py'
sys.path.insert(0, str(ROOT / 'research/g9/kaggle_wp7b'))
import build_wp7b_bundle as builder
import wp7b_child_entry as child_entry

def sha(b):
    return hashlib.sha256(b).hexdigest()

def run():
    import verify_wp7b_child_fixtures as isolated_fixtures
    isolated_fixtures.run()
    def fixture_guard_must_refuse(fixture_mode, draft, approval_record, label):
        try:
            builder.require_fixture_approval(fixture_mode, draft, approval_record)
        except builder.BuildError:
            return
        raise AssertionError(label + ' unexpectedly passed')
    fixture_guard_must_refuse(True, True, None, 'fixture-mode draft')
    fixture_guard_must_refuse(True, True, object(), 'fixture-mode draft with approval')
    fixture_guard_must_refuse(True, False, None, 'fixture-mode without approval')
    if builder.require_fixture_approval(True, False, object()) is not True:
        raise AssertionError('valid armed fixture-mode input was refused')
    if builder.require_fixture_approval(False, True, None) is not True:
        raise AssertionError('ordinary draft input was refused')
    with tempfile.TemporaryDirectory(dir="/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso",prefix='wp7b-fixture-') as td:
        t = Path(td)
        staged=t/'stage'; staged.mkdir()
        staged_file=staged/'leaf.py'; staged_file.write_bytes(b'value = 1\n')
        index_raw=child_entry.canonical([['leaf.py',sha(staged_file.read_bytes())]])
        index_path=staged/'.index'; index_path.write_bytes(index_raw)
        if child_entry.verify_stage(staged,index_path,sha(index_raw))[0][0] != 'leaf.py':
            raise AssertionError('child rejected an intact staged payload')
        staged_file.write_bytes(b'value = 2\n')
        try: child_entry.verify_stage(staged,index_path,sha(index_raw))
        except child_entry.ChildRefusal as exc:
            if 'sha256 mismatch' not in str(exc): raise
        else: raise AssertionError('child accepted a modified staged payload')
        try: child_entry.verify_stage(staged,index_path,'0'*64)
        except child_entry.ChildRefusal as exc:
            if 'archive index sha256 mismatch' not in str(exc): raise
        else: raise AssertionError('child accepted a modified staging index')
        index_link=staged/'.index-link'; index_link.symlink_to(index_path)
        try: child_entry.verify_stage(staged,index_link,sha(index_raw))
        except child_entry.ChildRefusal as exc:
            if 'linked or escaping' not in str(exc): raise
        else: raise AssertionError('child accepted a linked staging index')
        outside_index=t/'.outside-index'; outside_index.write_bytes(index_raw)
        try: child_entry.verify_stage(staged,outside_index,sha(index_raw))
        except child_entry.ChildRefusal as exc:
            if 'linked or escaping' not in str(exc): raise
        else: raise AssertionError('child accepted an index outside the private stage')
        for rows in ((['../escape.py','0'*64],), (['missing.py','0'*64],),
                     (['leaf.py',sha(staged_file.read_bytes())],['leaf.py',sha(staged_file.read_bytes())])):
            candidate=staged/'candidate-index'
            candidate.write_bytes(child_entry.canonical(list(rows)))
            try: child_entry.verify_stage(staged,candidate,sha(candidate.read_bytes()))
            except child_entry.ChildRefusal: pass
            else: raise AssertionError('child accepted an invalid archive index entry')
        file_link=staged/'link.py'; file_link.symlink_to(staged_file)
        linked_index=child_entry.canonical([['link.py',sha(staged_file.read_bytes())]])
        candidate=staged/'linked-file-index'; candidate.write_bytes(linked_index)
        try: child_entry.verify_stage(staged,candidate,sha(linked_index))
        except child_entry.ChildRefusal: pass
        else: raise AssertionError('child accepted a staged symlink')
        if child_entry.validate_site_dirs([str(staged)]) != [str(staged)]:
            raise AssertionError('child rejected an existing absolute site directory')
        for invalid_sites in ([], ['relative/site-packages'], [str(t/'missing-site-packages')]):
            try: child_entry.validate_site_dirs(invalid_sites)
            except child_entry.ChildRefusal: pass
            else: raise AssertionError('child accepted missing or relative site-packages path')
        child_entry.assert_clean_process(modules=(),environment={})
        for modules,environment in ((('socket',),{}),(('kaggle.api',),{}),
                                    ((),{'KAGGLE_USER_SECRETS_TOKEN':'test'})):
            try: child_entry.assert_clean_process(modules=modules,environment=environment)
            except child_entry.ChildRefusal: pass
            else: raise AssertionError('child clean-process guard accepted a prohibited state')
        allow_names=(child_entry.ALLOW_D013,child_entry.ALLOW_CORE,'PYTHONDONTWRITEBYTECODE')
        saved_allow={name:os.environ.get(name) for name in allow_names}
        try:
            for name in allow_names: os.environ.pop(name,None)
            child_entry.arm_permissions(True)
            if any(name in os.environ for name in (child_entry.ALLOW_D013,child_entry.ALLOW_CORE)):
                raise AssertionError('fixture child armed permissions in fixture mode')
            child_entry.arm_permissions(False)
            if any(os.environ.get(name)!='1' for name in (child_entry.ALLOW_D013,child_entry.ALLOW_CORE)):
                raise AssertionError('armed child did not set both permission variables')
        finally:
            for name,value in saved_allow.items():
                if value is None: os.environ.pop(name,None)
                else: os.environ[name]=value
        files = {}
        data = {'instance': {'instance_kind': 'synthetic', 'synthetic': True, 'source': 'synthetic_generator:fixture'}, 'prepared': {'fixture': 'prepared'}, 'seal': None, 'seal_inputs': {'input_hashes': {}, 'production_identity_hash': '0' * 64, 'coordinates': []}, 'config': {'instance_path': 'research/g9/kaggle_wp7b/instance.json', 'prepared_record_path': 'research/g9/kaggle_wp7b/prepared_record.json', 'seal_path': 'research/g9/kaggle_wp7b/seal.json', 'seal_inputs_path': 'research/g9/kaggle_wp7b/seal_inputs.json'}}
        for n, obj in data.items():
            p = t / (n + '.json')
            if n == 'seal':
                p.write_bytes(b'{"fixture":"raw seal bytes"}')
            else:
                p.write_bytes(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode() + b'\n')
            files[n] = p
        out = t / 'out'
        cmd = [sys.executable, '-B', str(BUILDER), '--output-dir', str(out), '--kaggle-user', 'shivanshsrivastava06', '--draft']
        names = {'instance': '--instance', 'prepared': '--prepared-record', 'seal': '--seal', 'seal_inputs': '--seal-inputs', 'config': '--runtime-config'}
        for k, p in files.items():
            cmd += [names[k], str(p), '--' + names[k][2:] + '-sha256', sha(p.read_bytes())]
        guard_args = list(cmd[cmd.index('--output-dir'):]) + ['--fixture-mode']
        guard_args[guard_args.index('--output-dir') + 1] = str(t / 'fixture-guard-output')
        original_guard_loader = builder.load_payload
        builder.load_payload = lambda *_args, **_kwargs: (_ for _ in ()).throw(builder.BuildError('fixture approval guard ran too late'))
        try:
            guard_capture = io.StringIO()
            with contextlib.redirect_stdout(guard_capture), contextlib.redirect_stderr(guard_capture):
                guard_status = builder.main(guard_args)
        finally:
            builder.load_payload = original_guard_loader
        if not (guard_status == 2 and 'fixture-mode build requires an armed test approval record' in guard_capture.getvalue()):
            raise AssertionError('main did not enforce fixture approval before payload loading')
        cp = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if not cp.returncode == 0:
            raise AssertionError(cp.stderr)
        script = next(out.glob('*.py'))
        src = script.read_text()
        runtime = runpy.run_path(str(script))
        decoded = runtime['verify_payload']()
        isolated_fixtures.supervisor(runtime,decoded,t)
        original_environment=dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({'PATH':'/cuda/bin','LD_LIBRARY_PATH':'/cuda/lib','CUDA_HOME':'/cuda',
                'CUDA_VERSION':'12.8','CUDA_VISIBLE_DEVICES':'0','CUDA_DEVICE_ORDER':'PCI_BUS_ID',
                'BUILD_DATE':'fixture','COLAB_IMAGE_TYPE':'gpu','GIT_COMMIT':'abc','HOME':'/home/test',
                'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','NVIDIA_VISIBLE_DEVICES':'all','TMPDIR':'/scratch',
                'KAGGLE_USER_SECRETS_TOKEN':'fixture-secret','PYTHONPATH':'/bad/path','PYTHONHOME':'/bad/home'})
            child_env=runtime['child_environment']()
        finally:
            os.environ.clear(); os.environ.update(original_environment)
        if (any(name.startswith('KAGGLE_') or
                (name.startswith('PYTHON') and name!='PYTHONDONTWRITEBYTECODE') for name in child_env) or
                child_env.get('PYTHONDONTWRITEBYTECODE')!='1' or
                child_env.get('CUDA_VISIBLE_DEVICES')!='0' or child_env.get('NVIDIA_VISIBLE_DEVICES')!='all'):
            raise AssertionError('outer child environment allowlist failed')
        class NamesOnlyExcluded(dict):
            def __getitem__(self,key):
                if key.startswith('KAGGLE_') or (key.startswith('PYTHON') and key!='PYTHONDONTWRITEBYTECODE'):
                    raise AssertionError('outer read an excluded credential/Python environment value')
                return super().__getitem__(key)
            def items(self):
                raise AssertionError('outer enumerated environment values before filtering names')
        original_environ=os.environ
        os.environ=NamesOnlyExcluded(PATH='/toolchain',KAGGLE_USER_SECRETS_TOKEN='never-read',PYTHONPATH='never-read')
        try:
            check_env=runtime['child_environment']()
            if check_env!={'PATH':'/toolchain','PYTHONDONTWRITEBYTECODE':'1'}:
                raise AssertionError('name-filtered environment changed')
        finally: os.environ=original_environ
        if not (len(decoded) == len(runtime['EXPECTED_INDEX']) and decoded['research/g9/kaggle_wp7b/instance.json'] == files['instance'].read_bytes()):
            raise AssertionError('fixture check failed')
        try:
            builder.derive_runtime_closure([])
        except builder.BuildError as exc:
            if 'dependency table absent' not in str(exc):
                raise AssertionError('dependency table refusal reason changed')
        else:
            raise AssertionError('closure accepted a missing dependency table')
        probe_source = b'import research.g9.closure_leaf\n'
        missing_source = b'import research.g9.closure_absent\n'
        relative_source = b'from . import child\n'
        relative_probe = b'from . import leaf\n'
        probe_table = json.dumps({'dependencies': {'research/g9/closure_probe.py': sha(probe_source), 'research/g9/closure_missing.py': sha(missing_source), 'research/g9/closurepkg/__init__.py': sha(relative_source), 'research/g9/closurepkg2/probe.py': sha(relative_probe)}, 'package_files_sha256': {}}, sort_keys=True).encode()
        probe_blobs = [
            (builder.TABLE, sha(probe_table), probe_table),
            ('research/g9/closure_probe.py', sha(probe_source), probe_source),
            ('research/g9/closure_leaf.py', sha(b'VALUE = 1\n'), b'VALUE = 1\n'),
            ('research/g9/closurepkg/__init__.py', sha(relative_source), relative_source),
            ('research/g9/closurepkg/child.py', sha(b'VALUE = 2\n'), b'VALUE = 2\n'),
            # These package members exist in the payload but are not seed
            # dependencies; the relative ImportFrom must discover both.
            ('research/g9/closurepkg2/__init__.py', sha(b'VALUE = 3\n'), b'VALUE = 3\n'),
            ('research/g9/closurepkg2/probe.py', sha(relative_probe), relative_probe),
            ('research/g9/closurepkg2/leaf.py', sha(b'VALUE = 4\n'), b'VALUE = 4\n'),
            ('research/g9/closure_missing.py', sha(missing_source), missing_source),
        ]
        derived = builder.derive_runtime_closure(probe_blobs)
        if not {'research/g9/closure_leaf.py', 'research/g9/closurepkg/child.py', 'research/g9/closurepkg2/__init__.py', 'research/g9/closurepkg2/leaf.py', 'research/g9/closure_absent.py'} <= derived:
            raise AssertionError('closure import graph did not include transitive, relative, and missing modules')
        raw_blobs = [(name, digest, raw) for name, digest, raw in sorted((n, sha(b), b) for n,b in decoded.items())]
        closure = {name for name, _, _ in raw_blobs}
        if not builder.validate_payload_blobs(raw_blobs, closure) is True:
            raise AssertionError('fixture check failed')
        cases = []
        changed = list(raw_blobs)
        n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
        i = next((i for i, row in enumerate(changed) if row[0] == n))
        changed[i] = (n, d, b + b'x')
        cases.append(changed)
        changed = list(raw_blobs)
        n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
        i = next((i for i, row in enumerate(changed) if row[0] == n))
        changed[i] = (n + '.renamed', d, b)
        cases.append(changed)
        cases.append(raw_blobs + [('research/g9/kaggle_wp7b/extra.bin', sha(b'x'), b'x')])
        cases.append(raw_blobs[:-1])
        for tampered in cases:
            try:
                builder.validate_payload_blobs(tampered, closure)
            except builder.BuildError:
                pass
            else:
                raise AssertionError('build-time tamper was accepted')

        def must_refuse(call, label):
            try:
                call()
            except builder.BuildError:
                return
            raise AssertionError(label + ' unexpectedly passed')
        must_refuse(lambda: builder.read(t, 'research/missing.file'), 'missing input')
        symlink_target = t / 'symlink-target'
        symlink_target.write_bytes(b'reviewed')
        symlink = t / 'symlink'
        symlink.symlink_to(symlink_target)
        must_refuse(lambda: builder.read(t, 'symlink'), 'symlink input')
        duplicate = raw_blobs + [raw_blobs[0]]
        must_refuse(lambda: builder.validate_payload_blobs(duplicate, closure), 'duplicate blob')
        changed = list(raw_blobs)
        n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
        i = next((i for i, row in enumerate(changed) if row[0] == n))
        changed[i] = (n.replace('research/', 'outside/'), d, b)
        must_refuse(lambda: builder.validate_payload_blobs(changed, {row[0] for row in changed}), 'non-repo name')
        for bad_name in ('outside/blob', 'research/g9/../escape', 7):
            changed = list(raw_blobs)
            n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
            i = next((i for i, row in enumerate(changed) if row[0] == n))
            changed[i] = (bad_name, d, b)
            must_refuse(lambda changed=changed: builder.validate_payload_blobs(changed, {row[0] for row in changed}), 'invalid blob name')
        changed = list(raw_blobs)
        n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
        i = next((i for i, row in enumerate(changed) if row[0] == n))
        changed[i] = (n, 'bad-digest', b)
        must_refuse(lambda: builder.validate_payload_blobs(changed, closure), 'malformed digest')
        changed = list(raw_blobs)
        n, d, b = next((row for row in raw_blobs if row[0] == 'research/g9/kaggle_wp7b/instance.json'))
        i = next((i for i, row in enumerate(changed) if row[0] == n))
        changed[i] = (n, sha(b + b'x'), b)
        must_refuse(lambda: builder.validate_payload_blobs(changed, closure), 'blob bytes do not match valid digest')
        input_map = {key: str(path) for key, path in [('instance', files['instance']), ('prepared_record', files['prepared']), ('seal', files['seal']), ('seal_inputs', files['seal_inputs']), ('runtime_config', files['config'])]}
        for key, path in [('instance', files['instance']), ('prepared_record', files['prepared']), ('seal', files['seal']), ('seal_inputs', files['seal_inputs']), ('runtime_config', files['config'])]:
            input_map[key + '_sha256'] = sha(path.read_bytes())
        wrong_hash = dict(input_map)
        wrong_hash['instance_sha256'] = '0' * 64
        must_refuse(lambda: builder.load_payload(ROOT, wrong_hash), 'artifact input hash mismatch')
        copied = t / 'copy-root'
        for name, _, raw in raw_blobs:
            dest = copied / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        package_file = copied / 'research/g9/kaggle_wp7/build_wp7_package.py'
        package_file.write_bytes(package_file.read_bytes() + b'\n')
        must_refuse(lambda: builder.load_payload(copied, input_map), 'pinned package byte mismatch')
        dep_root = t / 'dep-root'
        for name, _, raw in raw_blobs:
            dest = dep_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        dependency_path = dep_root / next(iter(json.loads((dep_root / builder.TABLE).read_text())['dependencies']))
        dependency_path.write_bytes(dependency_path.read_bytes() + b'\n')
        must_refuse(lambda: builder.load_payload(dep_root, input_map), 'reviewed dependency byte mismatch')
        anchor_root = t / 'anchor-root'
        for name, _, raw in raw_blobs:
            dest = anchor_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        table_path = anchor_root / builder.TABLE
        original_table = table_path.read_bytes()
        table_path.write_bytes(original_table + b' ')
        must_refuse(lambda: builder.load_payload(anchor_root, input_map), 'reviewed table anchor mismatch')
        table_path.write_bytes(original_table)
        extra_name = next(iter(builder.EXTRAS))
        extra_path = anchor_root / extra_name
        original_extra = extra_path.read_bytes()
        extra_path.write_bytes(original_extra + b'fixture tamper')
        must_refuse(lambda: builder.load_payload(anchor_root, input_map), 'pinned extra hash mismatch')
        extra_path.write_bytes(original_extra)
        original_closure = builder.derive_runtime_closure
        builder.derive_runtime_closure = lambda blobs: {'research/g9/fixture_not_embedded.py'}
        try:
            must_refuse(lambda: builder.load_payload(anchor_root, input_map), 'absent runtime closure member')
        finally:
            builder.derive_runtime_closure = original_closure
        must_refuse(lambda: builder.script_source([], '0' * 64, '', {}, True), 'missing raw seal')
        runtime = runpy.run_path(str(script))
        permission_names=('G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION','G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION','PYTHONDONTWRITEBYTECODE')
        saved_permissions={name:os.environ.pop(name,None) for name in permission_names}
        before_permissions={name:os.environ.get(name) for name in permission_names}
        try:
            runtime['main']()
        except SystemExit:
            pass
        else:
            raise AssertionError('draft launcher did not refuse')
        if {name:os.environ.get(name) for name in permission_names} != before_permissions:
            raise AssertionError('draft path changed permission environment')
        def encoded_container(index, data):
            index_bytes = builder.canon(index)
            packed = lzma.compress(len(index_bytes).to_bytes(8, 'big') + index_bytes + data,
                                   format=lzma.FORMAT_XZ, check=lzma.CHECK_SHA256,
                                   preset=9 | lzma.PRESET_EXTREME)
            encoded = base64.b85encode(packed).decode('ascii')
            chunks = tuple(encoded[i:i + 76] for i in range(0, len(encoded), 76))
            return chunks, sha(packed)
        def runtime_refuses(chunks, archive_sha=None, max_size=None, label='tamper'):
            kwargs = {'chunks': chunks}
            if archive_sha is not None: kwargs['archive_sha'] = archive_sha
            if max_size is not None: kwargs['max_size'] = max_size
            try:
                runtime['decode_archive'](**kwargs)
            except runtime['TransportError']:
                return
            raise AssertionError(label + ' was accepted')
        original_chunks = runtime['ARCHIVE_CHUNKS']
        original_archive_sha = runtime['ARCHIVE_SHA']
        flipped = bytearray(base64.b85decode(''.join(original_chunks).encode('ascii')))
        flipped[len(flipped) // 2] ^= 1
        flipped_text = base64.b85encode(bytes(flipped)).decode('ascii')
        runtime_refuses(tuple(flipped_text[i:i+76] for i in range(0,len(flipped_text),76)), original_archive_sha, label='archive byte flip')
        runtime_refuses(original_chunks, '0' * 64, label='wrong archive sha literal')
        index = [[n,d,offset,length] for n,d,offset,length in (lambda packed: json.loads(packed[8:8+int.from_bytes(packed[:8],'big')]))(builder.make_archive(raw_blobs))]
        data_bytes = b''.join(b for _,_,b in raw_blobs)
        def check_index(mutated, raw_data=data_bytes, label='index mutation'):
            chunks, digest = encoded_container(mutated, raw_data)
            runtime_refuses(chunks, digest, label=label)
        renamed = [row[:] for row in index]; renamed[0][0] += '.renamed'; check_index(renamed, label='renamed index entry')
        duplicated = [row[:] for row in index]; duplicated[1] = duplicated[0][:]; check_index(duplicated, label='duplicate index entry')
        check_index(index[:-1], label='dropped index entry')
        added = [row[:] for row in index] + [['research/g9/extra.bin', sha(b'x'), len(data_bytes), 1]]
        check_index(added, data_bytes+b'x', label='added index entry')
        overlap = [row[:] for row in index]; overlap[1][2] -= 1; check_index(overlap, label='overlap offset')
        gap = [row[:] for row in index]; gap[1][2] += 1; check_index(gap, label='gap offset')
        bad_length = [row[:] for row in index]; bad_length[0][3] += 1; check_index(bad_length, label='overlap length')
        trailing_chunks, trailing_sha = encoded_container(index, data_bytes+b'x')
        runtime_refuses(trailing_chunks, trailing_sha, label='trailing bytes')
        bomb_chunks, bomb_sha = encoded_container([], b'x' * 4096)
        runtime_refuses(bomb_chunks, bomb_sha, max_size=128, label='decompressed-size bomb')
        changed_data = bytearray(data_bytes); changed_data[0] ^= 1
        bad_blob_chunks, bad_blob_sha = encoded_container(index, bytes(changed_data))
        runtime_refuses(bad_blob_chunks, bad_blob_sha, label='blob digest mismatch')
        runtime_globals = runtime['decode_archive'].__globals__
        runtime_globals['SEAL_RAW_SHA'] = '0' * 64
        runtime_refuses(original_chunks, original_archive_sha, label='raw seal digest mismatch')
        runtime_globals['SEAL_RAW_SHA'] = sha(decoded['research/g9/kaggle_wp7b/seal.json'])
        if builder.SCRIPT_SIZE_LIMIT != 950_000:
            raise AssertionError('armed builder size limit changed')
        try:
            builder.enforce_script_size('x' * 950_000, 950_000)
        except builder.BuildError:
            pass
        else:
            raise AssertionError('builder accepted script at injected size limit')
        if builder.enforce_script_size('x' * 949_999, 950_000) != 949_999:
            raise AssertionError('builder test size injection did not preserve below-limit source')
        manifest = json.loads((out / 'wp7b_bundle_manifest.json').read_text())
        expected = {'bundle_sha256': manifest['bundle_sha256'], 'reviewed_table_anchor': builder.ANCHOR, 'seal_sha256': sha(files['seal'].read_bytes()), 'kernel_id': 'shivanshsrivastava06/g9-wp7-nonscientific-dry-run-' + manifest['bundle_sha256'][:8], 'account': 'shivanshsrivastava06', 'action': 'push_and_run_wp7_dry_run'}
        valid = expected | {'expiry': '2099-12-31', 'nonce': 'fixture-once'}
        builder.validate_record(valid, expected)
        for field, value in [('bundle_sha256', '0' * 64), ('reviewed_table_anchor', '0' * 64), ('seal_sha256', '0' * 64), ('kernel_id', 'other/kernel'), ('account', 'other'), ('action', 'run')]:
            invalid = dict(valid)
            invalid[field] = value
            try:
                builder.validate_record(invalid, expected)
            except builder.BuildError:
                pass
            else:
                raise AssertionError('build-time approval mismatch accepted: ' + field)
        expired = dict(valid)
        expired['expiry'] = '2000-01-01'
        try:
            builder.validate_record(expired, expected)
        except builder.BuildError:
            pass
        else:
            raise AssertionError('expired approval accepted at build time')
        must_refuse(lambda: builder.validate_record(valid | {'expiry': '20991231'}, expected), 'noncanonical ISO expiry')
        for invalid in [valid | {'expiry': 'tomorrow'}, valid | {'expiry': '2026-99-99'}, valid | {'expiry': None}, valid | {'nonce': ''}, valid | {'nonce': None}, valid | {'nonce': 7}]:
            must_refuse(lambda invalid=invalid: builder.validate_record(invalid, expected), 'malformed approval value')
        must_refuse(lambda: builder.validate_record({k: v for k, v in valid.items() if k != 'nonce'}, expected), 'missing approval field')

        class DictSubclass(dict):
            pass
        must_refuse(lambda: builder.validate_record(DictSubclass(valid), expected), 'non-exact approval mapping type')
        record_path = t / 'owner-approval.json'
        record_path.write_text(json.dumps(valid, sort_keys=True) + '\n')
        base_args = [item for item in cmd[cmd.index('--output-dir'):] if item != '--draft']

        def invoke_builder(extra, suffix):
            args = list(base_args)
            args[args.index(str(out))] = str(t / ('check-' + suffix))
            args += extra
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                status = builder.main(args)
            return (status, capture.getvalue())
        original_loader = builder.load_payload
        builder.load_payload = lambda root, inputs: original_loader(root, inputs) + [original_loader(root, inputs)[0]]
        try:
            status, _ = invoke_builder(['--draft'], 'payload-validator')
            if not status == 2:
                raise AssertionError('fixture check failed')
        finally:
            builder.load_payload = original_loader
        original_source_builder = builder.script_source
        builder.script_source = lambda *args, **kwargs: original_source_builder(*args, **kwargs).replace("SELF_SHA='" + '0' * 64 + "'", '', 1)
        try:
            status, _ = invoke_builder(['--draft'], 'missing-self-hash-marker')
            if not status == 2:
                raise AssertionError('fixture check failed')
        finally:
            builder.script_source = original_source_builder
        status, message = invoke_builder([], 'missing-record')
        if not (status == 2 and 'armed build requires owner approval record' in message):
            raise AssertionError('fixture check failed')
        for extra, suffix in [(['--draft', '--owner-approval-record', str(record_path)], 'draft-record-without-hash'), (['--draft', '--owner-approval-record-sha256', sha(record_path.read_bytes())], 'draft-hash-without-record'), (['--owner-approval-record', str(record_path)], 'armed-record-without-hash'), (['--owner-approval-record-sha256', sha(record_path.read_bytes())], 'armed-hash-without-record')]:
            status, message = invoke_builder(extra, suffix)
            if not status == 2:
                raise AssertionError('fixture check failed')
            if suffix == 'armed-hash-without-record':
                if not 'armed build requires owner approval record' in message:
                    raise AssertionError('fixture check failed')
            if suffix == 'armed-record-without-hash':
                if not 'armed build requires owner approval sha256' in message:
                    raise AssertionError('fixture check failed')
        status, _ = invoke_builder(['--draft', '--kaggle-user', 'INVALID USER'], 'invalid-user')
        if not status == 2:
            raise AssertionError('fixture check failed')
        status,_=invoke_builder(['--draft','--kaggle-user','different-valid-user'],'wrong-valid-username')
        if not status == 2:
            raise AssertionError('wrong valid username was accepted')
        status, _ = invoke_builder(['--owner-approval-record', str(record_path), '--owner-approval-record-sha256', '0' * 64], 'wrong-record-hash')
        if not status == 2:
            raise AssertionError('fixture check failed')
        status, _ = invoke_builder(['--draft', '--owner-approval-record', str(record_path), '--owner-approval-record-sha256', sha(record_path.read_bytes())], 'draft-with-record')
        if not status == 2:
            raise AssertionError('fixture check failed')
        wrong_record = dict(valid)
        wrong_record['action'] = 'forbidden'
        wrong_path = t / 'wrong-action.json'
        wrong_path.write_text(json.dumps(wrong_record, sort_keys=True) + '\n')
        status, _ = invoke_builder(['--owner-approval-record', str(wrong_path), '--owner-approval-record-sha256', sha(wrong_path.read_bytes())], 'wrong-action')
        if not status == 2:
            raise AssertionError('fixture check failed')
        placeholder_args = list(cmd[cmd.index('--output-dir'):])
        placeholder_args[placeholder_args.index(str(out))] = str(t / 'placeholder')
        placeholder_args[placeholder_args.index('shivanshsrivastava06')] = 'shivanshsrivastava06'
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            status = builder.main(placeholder_args)
        if not (status == 0 and json.loads((t / 'placeholder/wp7b_bundle_manifest.json').read_text())['push_command'].startswith('/home/shivansh-srivastava/venv/bin/kaggle kernels push -p ')):
            raise AssertionError('fixture check failed')
        if not (t / 'placeholder/kernel-metadata.json').is_file():
            raise AssertionError('fixture check failed')
        ordinary_args = list(cmd[cmd.index('--output-dir'):])
        ordinary_args[ordinary_args.index(str(out))] = str(t / 'ordinary')
        ordinary_args[ordinary_args.index('shivanshsrivastava06')] = 'shivanshsrivastava06'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ordinary_status = builder.main(ordinary_args)
        if not (ordinary_status == 0 and json.loads((t / 'ordinary/kernel-metadata.json').read_text())['id'].startswith('shivanshsrivastava06/')):
            raise AssertionError('fixture check failed')
        atomic_parent = t / 'atomic-parent' / 'nested'
        atomic_target = atomic_parent / 'file.bin'
        builder.atomic_write(atomic_target, b'atomic')
        if not atomic_target.read_bytes() == b'atomic':
            raise AssertionError('fixture check failed')
        original_fsync = builder.os.fsync
        fsync_calls = []
        builder.os.fsync = lambda fd: (fsync_calls.append(fd), original_fsync(fd))[1]
        try:
            builder.atomic_write(atomic_parent / 'synced.bin', b'durable')
        finally:
            builder.os.fsync = original_fsync
        if not len(fsync_calls) == 1:
            raise AssertionError('fixture check failed')
        failed_target = atomic_parent / 'failed.bin'
        original_replace = builder.os.replace
        builder.os.replace = lambda *args: (_ for _ in ()).throw(OSError('fixture rename failure'))
        try:
            try:
                builder.atomic_write(failed_target, b'cleanup')
            except OSError:
                pass
            else:
                raise AssertionError('atomic rename failure was ignored')
        finally:
            builder.os.replace = original_replace
        if not not list(atomic_parent.glob('failed.bin.*')):
            raise AssertionError('fixture check failed')
        armed_out = t / 'armed'
        armed_cmd = [item for item in cmd if item != '--draft'] + ['--owner-approval-record', str(record_path), '--owner-approval-record-sha256', sha(record_path.read_bytes()), '--output-dir', str(armed_out), '--fixture-mode']
        armed_cp = subprocess.run(armed_cmd, capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if not armed_cp.returncode == 0:
            raise AssertionError(armed_cp.stderr)
        armed_script = next(armed_out.glob('*.py'))
        armed_ns = runpy.run_path(str(armed_script))
        validate_approval = armed_ns['validate_approval']
        armed_decoded = armed_ns['verify_payload']()
        validate_approval(armed_decoded, datetime.date(2026, 9, 28))
        if not armed_ns['verify_launcher_bytes'](armed_script.read_bytes()) is True:
            raise AssertionError('fixture check failed')
        try:
            armed_ns['verify_launcher_bytes'](armed_script.read_bytes() + b'\n# edited after build\n')
        except ValueError:
            pass
        else:
            raise AssertionError('edited launcher accepted')
        try:
            validate_approval(armed_decoded, datetime.date(2100, 1, 1))
        except ValueError as exc:
            if not 'expired' in str(exc):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('expired approval accepted at runtime')
        armed_globals = validate_approval.__globals__
        expected_fields = armed_globals['APPROVAL_FIELDS']
        for field in ('bundle_sha256', 'reviewed_table_anchor', 'seal_sha256', 'kernel_id', 'account', 'action'):
            altered = dict(expected_fields)
            altered[field] = 'wrong-value'
            armed_globals['APPROVAL_FIELDS'] = altered
            try:
                validate_approval(armed_decoded, datetime.date(2026, 9, 28))
            except ValueError as exc:
                if not 'approval field mismatch' in str(exc):
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('runtime approval field mismatch accepted: ' + field)
        armed_globals['APPROVAL_FIELDS'] = expected_fields
        bad_decoded = dict(armed_decoded)
        bad_decoded['research/g9/kaggle_wp7b/owner_approval_record.json'] = b'{}\n'
        try:
            validate_approval(bad_decoded, datetime.date(2026, 9, 28))
        except ValueError:
            pass
        else:
            raise AssertionError('tampered approval hash accepted at runtime')
        runtime_out = t / 'runtime-out'
        run_env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'KAGGLE_WORKING_DIR': str(runtime_out)}
        refused = subprocess.run([sys.executable, '-B', str(armed_script)], capture_output=True, text=True, env=run_env)
        if not (refused.returncode == 2 and 'environment' in refused.stderr.lower()):
            raise AssertionError('armed environment refusal mismatch: rc=' + str(refused.returncode) +
                                 ' stderr=' + refused.stderr[-2000:])
        difference = json.loads((runtime_out / 'wp7b_difference.json').read_text())
        if not (difference['status'] == 'refused' and difference['scientific_outputs'] == []):
            raise AssertionError('fixture check failed')
        if not ('nvcc compile failed' not in refused.stderr and 'qualification' not in refused.stderr.lower()):
            raise AssertionError('fixture check failed')
        import types
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / 'research/g9/kaggle_wp7b'))
        import wp7b_launcher as launcher
        import research.g9 as g9_package
        worker_seal_path = t / 'worker-seal.bin'
        worker_seal_path.write_bytes(b'host-worker fixture seal')
        worker_calls = []
        class WorkerSeal:
            @staticmethod
            def open_for_session(sealed, inputs):
                if sealed != worker_seal_path.read_bytes() or inputs['production_identity_hash'] != 'a' * 64:
                    raise AssertionError('WP3 host worker opened unexpected seal inputs')
                return lambda *_args, **_kwargs: {}
        class WorkerHarness:
            @staticmethod
            def run_section_b2(*_args, **_kwargs):
                return {'malformed': 'fixture record'}
            @staticmethod
            def validate_section_b2_record(record):
                worker_calls.append(record)
                if record != {'accepted': 'fixture record'}:
                    raise ValueError('fixture record validator rejected malformed record')
        class WorkerIdentity:
            @staticmethod
            def validate_production_identity(_payload):
                return 'a' * 64
            @staticmethod
            def exact_match(_left, _right):
                return True
        class WorkerBackend:
            supports_inactive_positive_zero = True
            def __init__(self, *_args, **_kwargs):
                pass
        previous_worker_modules = {name: getattr(g9_package, name, None) for name in
                                   ('stage2_reference_seal', 'stage2_section_b2_harness', 'stage2_production_identity')}
        previous_worker_backend = launcher.Wp7bDeviceBackend
        g9_package.stage2_reference_seal = WorkerSeal
        g9_package.stage2_section_b2_harness = WorkerHarness
        g9_package.stage2_production_identity = WorkerIdentity
        launcher.Wp7bDeviceBackend = WorkerBackend
        worker_config = {'seal_inputs': {'input_hashes': {}, 'production_identity_hash': 'a' * 64, 'coordinates': []},
                         'seal_path': str(worker_seal_path), 'compiled_core_library': 'fixture-core.so',
                         'compiled_d013_library': 'fixture-d013.so', 'verified_d013_release_token': 'fixture-token',
                         'coordinates': [], 'd013_coordinates': [], 'accepted_identity': {},
                         'production_identity': {}, 'accepted_identity_sha256': 'a' * 64,
                         'protocol_identity_sha256': 'b' * 64}
        try:
            try:
                launcher._wp3_host_worker(worker_config)
            except ValueError as exc:
                if 'fixture record validator rejected malformed record' not in str(exc):
                    raise AssertionError('WP3 host worker changed record validation refusal')
            else:
                raise AssertionError('WP3 host worker returned a malformed harness record')
            if worker_calls != [{'malformed': 'fixture record'}]:
                raise AssertionError('WP3 host worker did not validate its harness record')
        finally:
            launcher.Wp7bDeviceBackend = previous_worker_backend
            for name, module in previous_worker_modules.items():
                if module is None:
                    delattr(g9_package, name)
                else:
                    setattr(g9_package, name, module)
        script_globals=armed_ns['main'].__globals__
        script_globals['DRAFT']=False
        script_globals['FIXTURE_MODE']=False
        script_globals['verify_launcher_bytes']=lambda _source:True
        script_globals['verify_payload']=lambda:armed_decoded
        script_globals['validate_approval']=lambda _decoded:(_ for _ in ()).throw(ValueError('approval deliberately failed'))
        failure_dir=t/'failed-approval-output'; os.environ['KAGGLE_WORKING_DIR']=str(failure_dir)
        try:
            try: armed_ns['main']()
            except SystemExit: pass
            else: raise AssertionError('failed approval path did not refuse')
            if {name:os.environ.get(name) for name in permission_names} != before_permissions:
                raise AssertionError('failed-approval path changed permission environment: '+repr({name:os.environ.get(name) for name in permission_names})+' vs '+repr(before_permissions))
        finally:
            os.environ.pop('KAGGLE_WORKING_DIR',None)
            for name in permission_names: os.environ.pop(name,None)
        permission_names=('G9_ALLOW_NONSCIENTIFIC_D013_CUDA_CORRUPTION_QUALIFICATION',
                          'G9_ALLOW_NONSCIENTIFIC_CUDA_CORRUPTION_QUALIFICATION','PYTHONDONTWRITEBYTECODE')
        saved_permissions={name:os.environ.get(name) for name in permission_names}
        budget_out=t/'generated-budget-out'
        prior_working=os.environ.get('KAGGLE_WORKING_DIR')
        prior_budget=os.environ.get('WP7B_TEST_FORCE_BUDGET')
        os.environ['KAGGLE_WORKING_DIR']=str(budget_out)
        os.environ['WP7B_TEST_FORCE_BUDGET']='fixture-budget-step'
        try:
            runpy.run_path(str(armed_script))['main']()
        finally:
            if prior_working is None: os.environ.pop('KAGGLE_WORKING_DIR',None)
            else: os.environ['KAGGLE_WORKING_DIR']=prior_working
            if prior_budget is None: os.environ.pop('WP7B_TEST_FORCE_BUDGET',None)
            else: os.environ['WP7B_TEST_FORCE_BUDGET']=prior_budget
        if {name:os.environ.get(name) for name in permission_names} != saved_permissions:
            raise AssertionError('outer fixture path changed armed permission environment')
        generated_budget = json.loads((budget_out / 'wp7b_receipt.json').read_text())
        if not (generated_budget['status'] == 'incomplete_budget' and generated_budget['last_completed_step'] == 'fixture-budget-step'):
            raise AssertionError('fixture check failed')
        if not (generated_budget['scientific_outputs'] == [] and sorted((p.name for p in budget_out.iterdir())) == ['wp7b_nonce_'+sha(b'fixture-once')+'.consumed','wp7b_receipt.json']):
            raise AssertionError('fixture check failed')
        if not '.DRAFT.py' in script.name:
            raise AssertionError('fixture check failed')
        if not 'research/g9/kaggle_wp7b/owner_approval_record.json' not in decoded:
            raise AssertionError('fixture check failed')
        if not 'DRAFT bundle is intentionally non-runnable' in src:
            raise AssertionError('fixture check failed')
        if not ('archive payload closure' in src and 'blob digest mismatch' in src and ('approval record hash mismatch' in src)):
            raise AssertionError('fixture check failed')
        if not manifest['push_command'].endswith('--accelerator NvidiaTeslaT4 -t 36600'):
            raise AssertionError('push timeout is shorter than child budget window')
        if not manifest['approval_record_sha256'] is None:
            raise AssertionError('fixture check failed')
        if not len([x for x in manifest['blobs'] if x['name'].startswith('research/g9/')]) >= 30:
            raise AssertionError('fixture check failed')
        shaped = launcher.result(counters={'n': 1}, identities={'id': 'x'}, digests={'sha256': '0' * 64})
        if not set(shaped) == {'counters', 'identities', 'digests', 'status', 'output'}:
            raise AssertionError('fixture check failed')
        child_src=(ROOT/'research/g9/kaggle_wp7b/wp7b_child_entry.py').read_text()
        if not all(term in src for term in ("'-I','-S','-B'",'STAGE_INDEX_SHA',
                'child_environment','36300','KAGGLE_','PYTHON')):
            raise AssertionError('fixture check failed')
        if 'from research.g9.kaggle_wp7 import wp7_session' in src or 'from research.g9.kaggle_wp7b import wp7b_launcher' in src:
            raise AssertionError('outer template imports runtime payload')
        if 'os.environ[ALLOW_D013]' in src or 'os.environ[ALLOW_CORE]' in src:
            raise AssertionError('outer template sets armed permission variables')
        if not all(term in child_src for term in ('verify_stage(root, args.index, args.index_sha256)',
                'assert_clean_process()', 'validate_site_dirs(site_dirs)', 'arm_permissions(fixture_mode)',
                'ALLOW_D013] = "1"', 'ALLOW_CORE] = "1"')):
            raise AssertionError('child runtime guards or armed launch path changed')
        if not (child_src.index('        verify_stage(root, args.index, args.index_sha256)') <
                child_src.index('        from research.g9.kaggle_wp7 import wp7_session') and
                child_src.index('        assert_clean_process()') <
                child_src.index('        arm_permissions(fixture_mode)')):
            raise AssertionError('child imported runtime or armed permissions before isolation checks')
        if not 'emulation_hooks' not in src[src.index('def main():'):]:
            raise AssertionError('fixture check failed')
        launcher.START = 0
        try:
            launcher.guard(lambda: launcher.BUDGET_SECONDS + 1, 'fixture-step')
        except RuntimeError as e:
            if not str(e) == 'incomplete_budget:last_completed=fixture-step':
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('budget guard did not fire')
        converted = launcher.budget_receipt_for_error(RuntimeError('step failed: incomplete_budget:last_completed=fixture-step'), launcher.BUDGET_SECONDS + 1)
        if not (converted['status'] == 'incomplete_budget' and converted['last_completed_step'] == 'fixture-step'):
            raise AssertionError('fixture check failed')
        if not (converted['scientific_outputs'] == [] and set(converted) == {'status', 'scientific_outputs', 'last_completed_step', 'elapsed_seconds', 'counters', 'identities', 'digests'}):
            raise AssertionError('fixture check failed')
        module_marker = t / 'loaded-module.txt'
        module_source = t / 'fixture_module.py'
        module_source.write_text('from pathlib import Path\nPath(' + repr(str(module_marker)) + ').write_text("loaded")\nVALUE=7\n')
        loaded = launcher._load(module_source, 'wp7b_fixture_module')
        if not (loaded.VALUE == 7 and module_marker.read_text() == 'loaded'):
            raise AssertionError('fixture check failed')
        fake = [0]
        timed_reference = launcher.budgeted_reference(lambda *a: {'ok': 1}, lambda: fake[0], lambda: 'wp3-batch')
        fake[0] = launcher.BUDGET_SECONDS + 1
        try:
            timed_reference((1, 2, 3), 'unbalanced')
        except RuntimeError as e:
            if not str(e) == 'incomplete_budget:last_completed=wp3-batch':
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('WP3 between-batch budget guard did not fire')
        fake[0] = 0
        sealed_value={'energy_minimum_words':['3ff8000000000000'],
            'canonical_minimum_index':0,'tie_flags':[7],
            'd015_d016_reconstruction':{'c_h':2048,'c_f':2048,'set_label':'L',
                                        'tie_count':1,'x_e_size':1}}
        seen=[]
        adapted_reference = launcher.budgeted_reference(lambda coordinate, encoding: seen.append((coordinate,encoding)) or sealed_value, lambda: fake[0], lambda: 'wp3-batch')
        adapted_row={'family':'primary','coordinate':(30,30,30),'r':1.0,
            'comparator':'primary','grid':'primary_61_cubed','inactive_positive_zero':False}
        adapted_result=adapted_reference(adapted_row,(2048,2048),'unbalanced')
        if not (seen == [({'family':'primary','point':[30,30,30],'r_hex':'0x1.0000000000000p+0',
            'comparator':'primary','grid':'primary_61_cubed','inactive_positive_zero':'no',
            'c_h':2048,'c_f':2048},'unbalanced')] and
            adapted_result == {'energy_minimum_words':[1.5],'canonical_minimum_index':0,
            'tie_flags':[7],'reconstruction':'{"c_f":2048,"c_h":2048,"set_label":"L","tie_count":1,"x_e_size":1}'}):
            raise AssertionError('fixture check failed')

        def fallback(*args):
            return ('fallback', args)
        fallback_reference = launcher.budgeted_reference(fallback, lambda: fake[0], lambda: 'wp3-batch')
        non_dict_with_coordinate = type('CoordinateMap', (), {'__contains__': lambda self, key: key == 'coordinate', '__getitem__': lambda self, key: {'x': 1}})()
        for args in (({'coordinate': {'x': 1}}, 'two args'), (non_dict_with_coordinate, 'second', 'third'), ({'not_coordinate': 1}, 'second', 'third')):
            if not fallback_reference(*args) == ('fallback', args):
                raise AssertionError('fixture check failed')
        budget = launcher.incomplete_budget_receipt('wp3-batch', launcher.BUDGET_SECONDS + 1)
        if not (budget['status'] == 'incomplete_budget' and budget['scientific_outputs'] == [] and (budget['last_completed_step'] == 'wp3-batch')):
            raise AssertionError('fixture check failed')
        try:
            launcher.require_wp2_passed(False)
        except RuntimeError as e:
            if not 'WP2 identity recheck refused' in str(e):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('WP2 refusal result passed')
        from research.g9.kaggle_wp7 import wp7_session as session
        pin = json.loads((ROOT / 'research/g9/kaggle_wp7/wp7_environment_pin.json').read_text())
        probes = launcher.build_probes(pin)
        if not set(probes) == {'platform_reported', 'image_reported'}:
            raise AssertionError('fixture check failed')
        observed_gpu = {'gpu_name': 'Tesla T4', 'compute_capability': '7.5', 'cuda_driver_version': '13000', 'cuda_runtime_version': '12080'}
        original_which = launcher.shutil.which
        original_run = launcher.subprocess.run
        fake_gpu_payload = [observed_gpu]

        def fake_nvcc_run(command, **kwargs):
            if command[1:] == ['--version']:
                return subprocess.CompletedProcess(command, 0, stdout='Cuda compilation tools, release 12.8, V12.8.93\n', stderr='')
            if '-o' in command:
                source = Path(command[-3])
                return subprocess.CompletedProcess(command, 0 if source.is_file() else 1, stdout='', stderr='')
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(fake_gpu_payload[0]), stderr='')
        launcher.shutil.which = lambda name: 'nvcc-fixture'
        launcher.subprocess.run = fake_nvcc_run
        try:
            probed = launcher.build_probes(pin)
            if not probed['platform_reported']()['gpu_name'] == 'Tesla T4':
                raise AssertionError('fixture check failed')
            if not probed['platform_reported']()['nvcc_version_release'] == '12.8, V12.8.93':
                raise AssertionError('fixture check failed')
            for invalid_gpu in (observed_gpu | {'gpu_name': ''}, observed_gpu | {'gpu_name': 1}, observed_gpu | {'extra': 'value'}):
                fake_gpu_payload[0] = invalid_gpu
                invalid_probe = launcher.build_probes(pin)['platform_reported']()
                if not {k: invalid_probe[k] for k in observed_gpu} == {k: None for k in observed_gpu}:
                    raise AssertionError('fixture check failed')
            fake_gpu_payload[0] = observed_gpu
        finally:
            launcher.shutil.which = original_which
            launcher.subprocess.run = original_run
        if not launcher.POST_RUN_ONLY_IMAGE_FIELDS == ('kaggle_image', 'image_manifest_sha256', 'image_config_id', 'image_name'):
            raise AssertionError('fixture check failed')
        exact_pin_copy = json.loads(json.dumps(pin))
        for image_key in launcher.POST_RUN_ONLY_IMAGE_FIELDS:
            del exact_pin_copy['image_reported'][image_key]
        if not launcher.environment_comparison_pin(pin) == exact_pin_copy:
            raise AssertionError('fixture check failed')
        for malformed_pin in ([], {'image_reported': None}):
            try:
                launcher.environment_comparison_pin(malformed_pin)
            except RuntimeError:
                pass
            else:
                raise AssertionError('malformed environment pin was accepted')
        for malformed_image_pin in ({}, {'image_reported': None}, {'image_reported': {}}):
            try:
                launcher.post_run_image_expectations(malformed_image_pin)
            except RuntimeError:
                pass
            else:
                raise AssertionError('malformed post-run image expectations were accepted')
        for missing_post_run_field in launcher.POST_RUN_ONLY_IMAGE_FIELDS:
            incomplete = json.loads(json.dumps(pin))
            del incomplete['image_reported'][missing_post_run_field]
            for helper in (launcher.environment_comparison_pin, launcher.post_run_image_expectations):
                try:
                    helper(incomplete)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('missing post-run image field was accepted: ' + missing_post_run_field)
        altered_image_pin = json.loads(json.dumps(pin))
        altered_image_pin['image_reported']['image_manifest_sha256'] = 'changed-pinned-manifest'
        if not launcher.post_run_image_expectations(altered_image_pin)['image_manifest_sha256'] == 'changed-pinned-manifest':
            raise AssertionError('fixture check failed')
        if not 'image_manifest_sha256' not in launcher.environment_comparison_pin(altered_image_pin)['image_reported']:
            raise AssertionError('fixture check failed')
        if not set(probes['platform_reported']()) == set(pin['platform_reported']):
            raise AssertionError('fixture check failed')
        if not set(probes['image_reported']()) == set(pin['image_reported']) - set(launcher.POST_RUN_ONLY_IMAGE_FIELDS):
            raise AssertionError('fixture check failed')
        if not set(probes['image_reported']()['build_env']) == set(pin['image_reported']['build_env']):
            raise AssertionError('fixture check failed')
        filtered = launcher.environment_comparison_pin(pin)
        if not set(filtered['image_reported']) == set(probes['image_reported']()):
            raise AssertionError('fixture check failed')
        for dropped in set(pin['platform_reported']) | set(pin['image_reported']) - set(launcher.POST_RUN_ONLY_IMAGE_FIELDS):
            candidate = json.loads(json.dumps(filtered))
            group = 'platform_reported' if dropped in candidate['platform_reported'] else 'image_reported'
            candidate[group].pop(dropped)
            observed = {'platform_reported': probes['platform_reported'](), 'image_reported': probes['image_reported']()}
            try:
                session.compare_environment_pin(observed, candidate)
            except session.Wp7EnvironmentAbort:
                pass
            else:
                raise AssertionError('dropping non-image pin field passed: ' + dropped)
        observed = session.capture_platform_identity(probes)
        try:
            session.compare_environment_pin(observed, launcher.environment_comparison_pin(pin))
        except session.Wp7EnvironmentAbort:
            pass
        else:
            raise AssertionError('CPU host unexpectedly matched platform/image pin')
        stage = t / 'stage'
        for rel, raw in decoded.items():
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        staged_table = json.loads((stage / builder.TABLE).read_text())
        staged_session_path = stage / 'research/g9/kaggle_wp7/wp7_session.py'
        staged_spec = importlib.util.spec_from_file_location('wp7b_fixture_pinned_session', staged_session_path)
        staged_session = importlib.util.module_from_spec(staged_spec)
        staged_spec.loader.exec_module(staged_session)
        fixture_instance = {'instance_kind': 'synthetic', 'synthetic': True, 'source': 'synthetic_generator:tiny-fixture'}
        coords = [{'coordinate': {'fixture': 'tiny'}, 'encoding': 'unbalanced'}, {'coordinate': {'fixture': 'tiny'}, 'encoding': 'slack'}]
        seal_inputs = {name: 'a' * 64 for name in ('instance_digest', 'coefficient_ledger_digest', 'protocol_digest', 'original_objective_digest', 'frozen_source_digest', 'decision_digest')}
        seal_inputs.update({'coordinates': coords, 'production_identity_hash': 'b' * 64})
        try:
            launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {}, emulation_hooks={'wp1': lambda *a: None})
        except RuntimeError as exc:
            if not 'fixture-only' in str(exc):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('production adapter accepted emulation hooks')
        failed_wp2_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {'production_identity': {}}, emulation_hooks={'wp2': lambda *args: {'gate_passed': False, 'checks_passed': 0}}, fixture_only=True)
        try:
            failed_wp2_steps['section_b_item_1_recheck_synthetic']()
        except RuntimeError as e:
            if not 'WP2 identity recheck refused' in str(e):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('WP2 adapter ignored a failed recheck')
        from research.g9 import stage2_reference_seal as seal_module
        sealed = seal_module.seal(seal_inputs, coords, 'b' * 64, runner=lambda coordinate, encoding: {'energy_minimum_words': ['0000000000000000'], 'canonical_minimum_index': 0, 'tie_flags': [7], 'd015_d016_reconstruction': {'fixture': 1}})
        seal_path = stage / 'research/g9/kaggle_wp7b/seal.json'
        seal_path.parent.mkdir(parents=True, exist_ok=True)
        seal_path.write_bytes(sealed)
        runtime_cfg = {'coordinates': coords}

        def existing_host_emulation(root, td, cfg):
            host_path = ROOT / 'research/g9/verify_stage2_cuda_core_stream_engine_host_emulation.py'
            host_spec = importlib.util.spec_from_file_location('wp7b_existing_host_emulation', host_path)
            host_mod = importlib.util.module_from_spec(host_spec)
            host_spec.loader.exec_module(host_mod)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = host_mod.main()
            if not (code == 0 and 'PASS Stage-2 core-stream engine host emulation' in output.getvalue()):
                raise AssertionError('fixture check failed')
            return {'counters': {'host_emulation_pass': 1}, 'identities': {}, 'digests': {'host_emulation_sha256': sha(output.getvalue().encode())}, 'status': 'ok', 'output': {'host_emulation': 'pass'}}
        hooks = {'wp6b': existing_host_emulation, 'wp1': lambda root, inst, prep, cfg: {'fixture_identity': 'tiny-host-emulation'}, 'wp2': lambda inst, identity, cfg: {'checks_passed': 6, 'fixture': 'pass'}, 'wp3': lambda reference, inst, identity, cfg: {'rows_visited': sum((1 for row in coords if reference(row['coordinate'], row['encoding']))), 'fixture': 'sealed-reference-used'}, 'wp4b': lambda output, inst, identity, prep, cfg: (output / 'synthetic-fixture.range').write_bytes(b'non-scientific host-emulation fixture\n') and {'ranges_written': 1, 'fixture': 'pass'}}
        steps, out_dir, step_times = launcher.run_adapters(stage, fixture_instance, {'fixture': 'prepared'}, seal_inputs, runtime_cfg, emulation_hooks=hooks, fixture_only=True)
        e2e_pin = launcher.environment_comparison_pin(pin)
        e2e_probes = {'platform_reported': lambda: pin['platform_reported'], 'image_reported': lambda: e2e_pin['image_reported']}
        sys.path.insert(0, str(stage))
        receipt = staged_session.run_session(root=stage, dependency_table=staged_table['dependencies'], environment_pin=e2e_pin, probes=e2e_probes, instance=fixture_instance, output_dir=out_dir, steps=steps, sealed_reference_path='research/g9/kaggle_wp7b/seal.json', seal_inputs=seal_inputs)
        receipt['status'] = 'pending_image_metadata_audit'
        receipt['package_status'] = 'pending_image_metadata_audit'
        receipt['identities']['post_run_only_image_fields'] = list(launcher.POST_RUN_ONLY_IMAGE_FIELDS)
        receipt['identities']['post_run_only_image_expected'] = launcher.post_run_image_expectations(pin)
        receipt['content_sha256'] = staged_session.content_sha256(receipt)
        receipt = staged_session.validate_receipt(receipt)
        if not receipt['status'] == 'pending_image_metadata_audit':
            raise AssertionError('fixture check failed')
        if not receipt['identities']['post_run_only_image_expected'] == {k: pin['image_reported'][k] for k in launcher.POST_RUN_ONLY_IMAGE_FIELDS}:
            raise AssertionError('fixture check failed')
        if not (receipt['package_status'] == 'pending_image_metadata_audit' and receipt['scientific_outputs'] == []):
            raise AssertionError('fixture check failed')
        if not set(staged_session.REQUIRED_STEPS) <= set(receipt['steps_executed']):
            raise AssertionError('fixture check failed')
        if not set(step_times) == {'synthetic_instance_gate', 'wp6b', 'wp1', 'wp2', 'wp3', 'wp4b'}:
            raise AssertionError('fixture check failed')
        del sys.path[0]
        direct_launcher = subprocess.run([sys.executable, '-B', str(ROOT / 'research/g9/kaggle_wp7b/wp7b_launcher.py')], capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if not (direct_launcher.returncode != 0 and 'Use the generated armed bundle entrypoint' in direct_launcher.stderr):
            raise AssertionError('fixture check failed')
        invalid_cfg = {'batch_ids': []}
        invalid_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, invalid_cfg)
        try:
            invalid_steps['wp4b_writer_synthetic_ranges']()
        except RuntimeError as e:
            if not 'sealed batch list absent' in str(e):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('WP4b accepted an empty sealed batch list')
        nonlist_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {'batch_ids': None})
        try:
            nonlist_steps['wp4b_writer_synthetic_ranges']()
        except RuntimeError as e:
            if not 'batch list must be a list' in str(e):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('WP4b accepted a non-list batch set')
        original_loader = launcher._load

        class FailedRecheck:

            @staticmethod
            def recheck_before_first_write(**kwargs):
                validate = kwargs['validate_identity']
                if not validate({'production_identity': fake_identity}) == '0' * 64:
                    raise AssertionError('fixture check failed')
                for malformed in ({}, ['production_identity']):
                    try:
                        validate(malformed)
                    except RuntimeError as exc:
                        if not 'wrapper is malformed' in str(exc):
                            raise AssertionError('fixture check failed')
                    else:
                        raise AssertionError('malformed WP2 identity wrapper was accepted')
                return ({}, False)

        class IdentityHelpers:

            @staticmethod
            def validate_production_identity(value):
                return '0' * 64

            @staticmethod
            def exact_match(left, right):
                return {'verdict': 'exact_match'}

        def fake_loader(path, name):
            return FailedRecheck if str(path).endswith('stage2_section_b1_recheck.py') else IdentityHelpers
        launcher._load = fake_loader
        try:
            fake_identity = {'qualification_identity': {'platform': {'nvcc_version': 'fixture'}, 'source_sha256': {}, 'compiler_flags': []}, 'image_build_evidence': {'fields': {'kaggle_saved_version_build_platform_reported': 'fixture [platform_reported]'}, 'kaggle_image_reported_string': 'fixture'}}
            actual_wp2_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {'production_identity': fake_identity, 'accepted_identity': fake_identity, 'observed_approval_sha256': '0' * 64, 'expected_approval_sha256': '0' * 64, 'generator_implementation_record_sha256': '0' * 64, 'expected_generator_implementation_record_sha256': '0' * 64, 'ground_truth_provenance_sha256': '0' * 64, 'expected_ground_truth_provenance_sha256': '0' * 64})
            try:
                actual_wp2_steps['section_b_item_1_recheck_synthetic']()
            except RuntimeError as e:
                if not 'WP2 identity recheck refused' in str(e):
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('WP2 accepted failed recheck result')
        finally:
            launcher._load = original_loader
        budget_stage = t / 'budget-stage'
        shutil.copytree(stage, budget_stage)
        clock_values = iter([0, 0, 0, 0, launcher.BUDGET_SECONDS + 1, launcher.BUDGET_SECONDS + 2])
        fake_clock = lambda: next(clock_values, launcher.BUDGET_SECONDS + 2)
        fake_writer = type('FixtureWriter', (), {
            'validate_production_identity': staticmethod(lambda value: '0' * 64),
            'exact_match': staticmethod(lambda left, right: None),
            'seal_range_plan': staticmethod(lambda *args, **kwargs: {'ranges': [
                {'batch_id': 'first'}, {'batch_id': 'second'}]}),
            'write_range': staticmethod(lambda *args, **kwargs: {'batch': 'pass'})})
        original_loader = launcher._load
        launcher._load = lambda *args, **kwargs: fake_writer
        try:
            bsteps, _, _ = launcher.run_adapters(budget_stage, fixture_instance, {}, seal_inputs, {
                'batch_ids': ['first', 'second'], 'records_by_batch': {'first': [], 'second': []},
                'result_schema': {}, 'production_identity': {}, 'accepted_identity': {},
                'writer_family': 'fixture', 'writer_total_coordinates': 2,
                'writer_root': 'fixture-output'}, clock=fake_clock)
            try:
                bsteps['wp4b_writer_synthetic_ranges']()
            except RuntimeError as e:
                if not str(e).startswith('incomplete_budget:last_completed=none'):
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('WP4b inter-batch budget guard did not fire')
        finally:
            launcher._load = original_loader
        expired_stage = t / 'expired-stage'
        shutil.copytree(stage, expired_stage)
        sequence = iter([0, launcher.BUDGET_SECONDS + 1, launcher.BUDGET_SECONDS + 2])
        never_called = []
        exp_steps, _, _ = launcher.run_adapters(expired_stage, fixture_instance, {}, seal_inputs, {}, clock=lambda: next(sequence, launcher.BUDGET_SECONDS + 2), emulation_hooks={'wp6b': lambda *a: never_called.append('ran')}, fixture_only=True)
        try:
            exp_steps['synthetic_instance_gate']()
        except RuntimeError as e:
            if not 'incomplete_budget' in str(e):
                raise AssertionError('fixture check failed')
        else:
            raise AssertionError('inter-step budget guard did not fire')
        if not not never_called:
            raise AssertionError('fixture check failed')
        compile_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {})
        original_which = launcher.shutil.which
        original_run = launcher.subprocess.run
        launcher.shutil.which = lambda name: None
        try:
            try:
                compile_steps['wp6b_section_a_qualification_plan']()
            except RuntimeError as e:
                if not str(e) == 'nvcc unavailable: no nvcc compiler found':
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('missing nvcc was accepted')
        finally:
            launcher.shutil.which = original_which
        compile_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {})
        original_which = launcher.shutil.which
        original_run = launcher.subprocess.run
        launcher.shutil.which = lambda name: 'nvcc-fixture'
        launcher.subprocess.run = lambda command, **kwargs: subprocess.CompletedProcess(command, 1 if command[-1] == '--self-test' else 0, stdout='', stderr='fixture self-test refusal' if command[-1] == '--self-test' else '')
        try:
            try:
                compile_steps['wp6b_section_a_qualification_plan']()
            except RuntimeError as e:
                if not 'compiled v1 core self-test failed' in str(e):
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('failed compiled core self-test was accepted')
        finally:
            launcher.shutil.which = original_which
            launcher.subprocess.run = original_run

        def assert_abi_load_refusal(reject_name, expected_message):
            abi_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {})
            old_which, old_run, old_load = (launcher.shutil.which, launcher.subprocess.run, launcher._load)
            launcher.shutil.which = lambda name: 'nvcc-fixture'

            def compiled_run(command, **kwargs):
                if command[-1] == '--self-test':
                    return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'fixture-compiled-library')
                return subprocess.CompletedProcess(command, 0, stdout='', stderr='')

            class Bridge:

                def __init__(self, name):
                    self.name = name

                def _load_checked_abi(self, path):
                    if self.name == reject_name:
                        raise RuntimeError(expected_message)
                    return None

            class Qualification:

                @staticmethod
                def run_qualification(_release):
                    return {'mutations': []}

            def fake_load(path, name):
                if name == 'wp7b_core_abi':
                    return Bridge('core')
                if name == 'wp7b_d013_abi':
                    return Bridge('d013')
                return Qualification
            launcher.subprocess.run = compiled_run
            launcher._load = fake_load
            try:
                try:
                    abi_steps['wp6b_section_a_qualification_plan']()
                except RuntimeError as exc:
                    if not str(exc) == expected_message:
                        raise AssertionError('fixture check failed')
                else:
                    raise AssertionError('compiled ABI refusal was ignored: ' + reject_name)
            finally:
                launcher.shutil.which = old_which
                launcher.subprocess.run = old_run
                launcher._load = old_load
        assert_abi_load_refusal('core', 'fixture core ABI rejected')
        assert_abi_load_refusal('d013', 'fixture D013 ABI rejected')
        old_loader = launcher._load
        launcher._load = lambda path, name: object()
        try:
            for wp3_config, expected_error in (({}, 'WP3 device backend has no compiled core/D013 libraries'), ({'compiled_d013_library': 'fixture'}, 'WP3 device backend has no compiled core/D013 libraries'), ({'compiled_core_library': 'fixture'}, 'WP3 device backend has no compiled core/D013 libraries'), ({'compiled_core_library': 'fixture', 'compiled_d013_library': 'fixture'}, 'WP3 requires the approved D013 VerifiedReleaseToken')):
                wp3_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, wp3_config)
                try:
                    wp3_steps['section_b_item_2_full_domain_synthetic'](lambda coordinate, encoding: {})
                except RuntimeError as exc:
                    if not str(exc) == expected_error:
                        raise AssertionError('fixture check failed')
                else:
                    raise AssertionError('WP3 accepted an incomplete compiled backend configuration')
        finally:
            launcher._load = old_loader
        compile_steps, _, _ = launcher.run_adapters(stage, fixture_instance, {}, seal_inputs, {})
        commands = []

        def fake_nvcc(command, **kwargs):
            commands.append(list(command))
            code = 0 if len(commands) == 1 else 1
            if len(commands) < 3:
                code = 0
            return subprocess.CompletedProcess(command, code, '', 'fixture compile error')
        launcher.shutil.which = lambda name: '/fixture/nvcc'
        launcher.subprocess.run = fake_nvcc
        try:
            try:
                compile_steps['wp6b_section_a_qualification_plan']()
            except RuntimeError as e:
                if not 'nvcc compile failed' in str(e):
                    raise AssertionError('fixture check failed')
            else:
                raise AssertionError('nvcc compile failure was accepted')
        finally:
            launcher.shutil.which = original_which
            launcher.subprocess.run = original_run
        if not (len(commands) == 3 and all((all((flag in command for flag in launcher.FLAGS)) for command in commands))):
            raise AssertionError('fixture check failed')
        if not ('-shared' not in commands[0] and '-shared' in commands[1] and ('-shared' in commands[2])):
            raise AssertionError('fixture check failed')
        if not commands[0][commands[0].index('-o') - 1].endswith('stage2_cuda_core_stream_engine.cu'):
            raise AssertionError('fixture check failed')
        if not commands[2][commands[2].index('-o') - 1].endswith('stage2_cuda_d013_inactive.cu'):
            raise AssertionError('fixture check failed')
        # Keep the fast guard-yard fixtures inside the full fixture contract, so
        # targeted mutation sweeps exercise checks that the full run also owns.
        for fixture_name in ('verify_wp7b_builder_sweep_fixture.py',
                             'verify_wp7b_launcher_sweep_fixture.py',
                             'verify_wp7b_embedded_source_syntax.py'):
            fixture_path = ROOT / 'research/g9/kaggle_wp7b' / fixture_name
            fixture_run = subprocess.run([sys.executable, '-B', str(fixture_path)],
                                         cwd=ROOT, capture_output=True, text=True,
                                         env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            if fixture_run.returncode != 0:
                raise AssertionError(fixture_name + ' failed: ' + fixture_run.stderr[-2000:])
        print(json.dumps({'status': 'PASS', 'bundle_sha256': manifest['bundle_sha256'], 'embedded_blob_count': len(decoded), 'draft_refuses': True}, sort_keys=True))
if __name__ == '__main__':
    run()
