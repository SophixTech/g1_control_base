#!/usr/bin/env python3
"""Export gripper diagnostics without treating raw feedback as radians or commands."""
import argparse
import csv
import json
from pathlib import Path


def export(session):
    rows = []
    for stream in ('client', 'robot'):
        for line in (session / f'{stream}.jsonl').read_text().splitlines():
            row = json.loads(line)
            row['stream'] = stream
            rows.append(row)
    if not any(r.get('joint') == 15 for r in rows):
        raise ValueError('Not a right gripper trace')
    rows.sort(key=lambda r: r['mono_ns'])
    start = rows[0]['mono_ns']
    fields = ['pc_seconds', 'stream', 'event', 'chunk_id', 'command_id', 'fitted_index',
              'sample_index', 'planned_offset_s', 'q', 'input_target', 'source',
              'reason', 'sdk_pair_stamp_ns', 'stamp_source', 'details']
    output = session / 'gripper.csv'
    with output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = row.get('q')
            samples = enumerate(values) if row['event'] == 'model_chunk' else [(None, values)]
            for index, value in samples:
                record = {k: row.get(k) for k in fields}
                record.update(pc_seconds=(row['mono_ns']-start)/1e9,
                              sample_index=index, q=value, details=json.dumps(row, ensure_ascii=False))
                if index is not None:
                    record['planned_offset_s'] = index * row['raw_period_s']
                writer.writerow(record)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    args = parser.parse_args()
    print(export(args.session).resolve())
