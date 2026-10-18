"""Run an analysis_20261003 script with the reviewed collector fix (collect_verify_v4k_b).

The analysis scripts import `collect_verify_v4k`; this runner aliases that module name to
`collect_verify_v4k_b` (the lead fix that proves the gate's canonical WP3 hash and the
sessions' content hash describe the same reconstructed record), then runs the target
script unchanged. Usage: python3 -B run_with_collector_b.py <script.py> [args...]
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent / 'multiacct_20261003/production_v4_release'
sys.path.insert(0, str(RELEASE))
sys.path.insert(0, str(HERE))
import collect_verify_v4k_b  # noqa: E402
sys.modules['collect_verify_v4k'] = collect_verify_v4k_b

target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]
runpy.run_path(str(HERE / target), run_name='__main__')
