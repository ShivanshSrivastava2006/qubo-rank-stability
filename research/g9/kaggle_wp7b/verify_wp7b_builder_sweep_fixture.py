"""Fast direct guard fixture for the WP7b bundle builder mutation sweep."""
from __future__ import annotations
import contextlib, datetime, hashlib, io, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'research/g9/kaggle_wp7b'))
import build_wp7b_bundle as builder

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def refuse(call, error_type, label):
    try:
        call()
    except error_type:
        return
    raise RuntimeError(label + ' unexpectedly passed')

def run():
    with tempfile.TemporaryDirectory(dir='/home/shivansh-srivastava/decisions_os/g9_jobs/scratch/wp7biso', prefix='wp7b-builder-sweep-') as td:
        temp = Path(td)
        data = b'fixture payload'
        rows = [('research/g9/fixture.py', sha(data), data)]
        require(builder.validate_payload_blobs(rows, {'research/g9/fixture.py'}) is True, 'valid payload refused')
        refuse(lambda: builder.validate_payload_blobs(rows + rows, {'research/g9/fixture.py'}), builder.BuildError, 'duplicate payload')
        refuse(lambda: builder.validate_payload_blobs(rows, {'research/g9/other.py'}), builder.BuildError, 'payload closure mismatch')
        for bad_name in ('outside/fixture.py', 'research/g9/../escape.py', 7):
            bad = [(bad_name, sha(data), data)]
            refuse(lambda bad=bad: builder.validate_payload_blobs(bad, {bad[0][0]}), builder.BuildError, 'bad blob name')
        refuse(lambda: builder.validate_payload_blobs([('research/g9/fixture.py', sha(data + b'x'), data)], {'research/g9/fixture.py'}), builder.BuildError, 'bad blob digest')
        missing = temp / 'missing'
        refuse(lambda: builder.read(temp, 'missing'), builder.BuildError, 'missing file')
        target = temp / 'target'; target.write_bytes(data)
        link = temp / 'link'; link.symlink_to(target)
        refuse(lambda: builder.read(temp, 'link'), builder.BuildError, 'symlink file')

        refuse(lambda: builder.derive_runtime_closure([]), builder.BuildError, 'missing closure table')
        probe = b'import research.g9.sweep_leaf\n'
        relative = b'from . import child\n'
        absent_import = b'import research.g9.sweep_absent\n'
        table = json.dumps({'dependencies': {
            'research/g9/sweep_probe.py': sha(probe),
            'research/g9/sweep_missing.py': sha(absent_import),
            'research/g9/sweeppkg/__init__.py': sha(relative)},
            'package_files_sha256': {}}, sort_keys=True).encode()
        closure_rows = [
            (builder.TABLE, sha(table), table),
            ('research/g9/sweep_probe.py', sha(probe), probe),
            ('research/g9/sweep_leaf.py', sha(data), data),
            ('research/g9/sweep_missing.py', sha(absent_import), absent_import),
            ('research/g9/sweeppkg/__init__.py', sha(relative), relative),
            ('research/g9/sweeppkg/child.py', sha(data), data),
        ]
        closure = builder.derive_runtime_closure(closure_rows)
        require({'research/g9/sweep_leaf.py', 'research/g9/sweeppkg/child.py', 'research/g9/sweep_absent.py'} <= closure, 'import closure missed a transitive or relative module')

        assets = {}
        for key, content in [('instance', b'{}'), ('prepared_record', b'{}'), ('seal', b'raw sealed test bytes'), ('seal_inputs', b'{}'), ('runtime_config', b'{}')]:
            path = temp / (key + '.json'); path.write_bytes(content)
            assets[key] = str(path); assets[key + '_sha256'] = sha(content)
        payload = builder.load_payload(builder.ROOT, assets)
        seal_blob = next(raw for name, _, raw in payload if name == 'research/g9/kaggle_wp7b/seal.json')
        require(seal_blob == b'raw sealed test bytes', 'seal was not stored raw')
        original_read = builder.read
        first_extra = next(iter(builder.EXTRAS))
        try:
            builder.read = lambda root, rel: b'tampered' if rel == first_extra else original_read(root, rel)
            refuse(lambda: builder.load_payload(builder.ROOT, assets), builder.BuildError, 'extra hash mismatch')
        finally:
            builder.read = original_read
        original_derive = builder.derive_runtime_closure
        try:
            builder.derive_runtime_closure = lambda blobs: {'research/g9/absent_runtime.py'}
            refuse(lambda: builder.load_payload(builder.ROOT, assets), builder.BuildError, 'missing embedded closure member')
        finally:
            builder.derive_runtime_closure = original_derive
        refuse(lambda: builder.script_source([], '0' * 64, '', {}, True), builder.BuildError, 'missing raw seal')
        refuse(lambda: builder.make_archive([('research/g9/blob', sha(b'x'), b'y')]), builder.BuildError, 'invalid blob digest')

        expected = {'bundle_sha256': 'a' * 64, 'reviewed_table_anchor': builder.ANCHOR,
                    'seal_sha256': 'b' * 64, 'kernel_id': 'user/kernel', 'account': 'user',
                    'action': 'push_and_run_wp7_dry_run'}
        record = expected | {'expiry': (datetime.date.today() + datetime.timedelta(days=1)).isoformat(), 'nonce': 'once'}
        builder.validate_record(record, expected)
        refuse(lambda: builder.validate_record(record | {'account': 'other'}, expected), builder.BuildError, 'approval mismatch')
        expired = record | {'expiry': '2000-01-01'}
        refuse(lambda: builder.validate_record(expired, expected), builder.BuildError, 'expired approval')

        draft_out = temp / 'draft-output'
        options = ['--output-dir', str(draft_out), '--kaggle-user', 'shivanshsrivastava06', '--draft']
        for key, flag in [('instance', '--instance'), ('prepared_record', '--prepared-record'), ('seal', '--seal'), ('seal_inputs', '--seal-inputs'), ('runtime_config', '--runtime-config')]:
            options.extend([flag, assets[key], flag + '-sha256', assets[key + '_sha256']])
        with contextlib.redirect_stdout(io.StringIO()):
            require(builder.main(options) == 0, 'valid draft build refused')
        require(len(list(draft_out.glob('*.py'))) == 1, 'draft launcher was not written')
        require((draft_out / 'kernel-metadata.json').is_file(), 'kernel metadata was not written')
        require((draft_out / 'wp7b_bundle_manifest.json').is_file(), 'bundle manifest was not written')
        wrong_user = list(options)
        wrong_user[wrong_user.index('--kaggle-user') + 1] = 'invalid username'
        with contextlib.redirect_stderr(io.StringIO()):
            require(builder.main(wrong_user) == 2, 'wrong username accepted')
        print('WP7B builder sweep fixture: PASS')

if __name__ == '__main__':
    run()
