"""Run an analysis script with (1) the collector fix and (2) the per-family CUDA-flush census fix.

(1) aliases `collect_verify_v4k` to the reviewed `collect_verify_v4k_b`.
(2) stage2_schema_v2 is aliased to stage2_schema_v2c (per-family flush formula). Production batches rows PER FAMILY (cuda_range_producer per family space,
    ROW_CAPACITY=2), so a slot's flush count is sum over families of ceil(rows/2)
    = 1,040,284, not ceil(2,080,562/2) = 1,040,281 as the v2 schema constant assumed.
    The correct value is DERIVED here from the module's own FAMILY_CENSUS and applied
    to stage2_schema_v2 / stage2_schema before the target script runs. Nothing else
    changes; no reviewed file is edited.
Usage: python3 -B run_with_collector_b2.py <script.py> [args...]
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

import stage2_schema_v2c  # noqa: E402  per-family flush census fix
sys.modules['stage2_schema_v2'] = stage2_schema_v2c

if __name__ == '__main__':
    target = sys.argv[1]
    sys.argv = [target] + sys.argv[2:]
    runpy.run_path(str(HERE / target), run_name='__main__')
