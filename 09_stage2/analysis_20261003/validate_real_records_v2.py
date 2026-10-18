"""Stream a complete production family, validating format only."""
import argparse
import gzip
import json
from pathlib import Path
import sys

import stage2_schema_v2 as schema


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family-root', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    family = args.family_root.name
    if family not in schema.FAMILY_CENSUS:
        print('incomplete: unknown family key')
        return 2
    files = sorted((args.family_root / 'full_records').glob('*.jsonl.gz'))
    counts = dict(files=len(files), records=0, passed=0, failed=0)
    first_error = None
    cursor = 0
    for path in files:
        try:
            with gzip.open(path, 'rt', encoding='ascii') as stream:
                for number, line in enumerate(stream, 1):
                    counts['records'] += 1
                    try:
                        record = schema.check_record(json.loads(line), family,
                                                     f'{path.name}:{number}')
                        schema._require(record['linear_index'] == cursor,
                                        f'{path.name}:{number}: noncontiguous linear_index')
                        counts['passed'] += 1
                    except (schema.Stage2AnalysisError, ValueError, KeyError,
                            TypeError) as exc:
                        counts['failed'] += 1
                        if first_error is None:
                            first_error = f'{type(exc).__name__}: {exc}'
                    cursor += 1
        except (OSError, EOFError, UnicodeError) as exc:
            counts['failed'] += 1
            if first_error is None:
                first_error = f'{type(exc).__name__}: {path.name}: {exc}'
    total = schema.FAMILY_CENSUS[family][1]
    if counts['records'] != total or len(files) != schema.sealed_range_count(total):
        if first_error is None:
            first_error = 'incomplete: missing family rows or sealed range files'
    result = dict(counts, family=family, expected_records=total, first_error=first_error)
    if args.report is not None:
        args.report.write_text(json.dumps(result, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return int(first_error is not None or counts['failed'] != 0)


if __name__ == '__main__':
    sys.exit(main())
