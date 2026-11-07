#!/usr/bin/env python3
"""Replace only a frozen ISO's menu, retaining every other file and extent.

The replacement must fit the existing menu slot. Strip debug sections before
calling this tool if necessary; no payload is appended or relocated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from freeze_opl_baseline import iso_inventory
from build_opl_boot_probes import sha

SECTOR = 2048


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--menu', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, menu, output = (p.resolve() for p in (args.baseline, args.menu, args.output))
    if output.exists():
        parser.error('output already exists; select a fresh path')
    work = output.parent / (output.stem + '-verification')
    work.mkdir(parents=True, exist_ok=False)
    before = iso_inventory(source, work / 'before-elfs')
    payload = menu.read_bytes()
    old = next(row for row in before if row['path'] == 'HPS2_000.01')
    if len(payload) > old['bytes']:
        parser.error(f'menu is {len(payload)} bytes; original slot is {old["bytes"]}')
    subprocess.run(['cp', '--reflink=auto', '--', str(source), str(output)], check=True)
    output.chmod(0o644)  # the frozen source is read-only; edit only this new copy
    with output.open('r+b') as stream:
        stream.seek(16 * SECTOR)
        pvd = bytearray(stream.read(SECTOR))
        pvd[8:40] = b'PLAYSTATION'.ljust(32, b' ')
        stream.seek(16 * SECTOR)
        stream.write(pvd)
        root_lba = int.from_bytes(pvd[158:162], 'little')
        root_bytes = int.from_bytes(pvd[166:170], 'little')
        stream.seek(root_lba * SECTOR)
        directory = bytearray(stream.read(root_bytes))
        cursor = 0
        found = False
        while cursor + 33 <= len(directory):
            size = directory[cursor]
            if not size:
                cursor = (cursor // SECTOR + 1) * SECTOR
                continue
            name = directory[cursor + 33:cursor + 33 + directory[cursor + 32]]
            if name.split(b';')[0] == b'HPS2_000.01':
                directory[cursor + 10:cursor + 14] = len(payload).to_bytes(4, 'little')
                directory[cursor + 14:cursor + 18] = len(payload).to_bytes(4, 'big')
                found = True
                break
            cursor += size
        if not found:
            raise RuntimeError('menu directory record missing')
        stream.seek(root_lba * SECTOR)
        stream.write(directory)
        stream.seek(old['lba'] * SECTOR)
        stream.write(payload)
        stream.write(bytes(old['bytes'] - len(payload)))
    after = iso_inventory(output, work / 'after-elfs')
    assert len(before) == len(after)
    new_rows = {row['path']: row for row in after}
    for row in before:
        new = new_rows[row['path']]
        if row['path'] == 'HPS2_000.01':
            assert new['lba'] == row['lba'] and new['sha256'] == sha(menu)
        else:
            assert new == row, (row, new)
    result = {'baseline': str(source), 'baseline_sha256': sha(source),
              'menu': str(menu), 'menu_sha256': sha(menu), 'output': str(output),
              'iso_sha256': sha(output), 'bytes': output.stat().st_size,
              'unchanged_other_files_and_extents': len(before) - 1,
              'unchanged_guest_elf_count': sum(r['path'].startswith('E/') and r['extracted_elf'] for r in before),
              'menu_lba_preserved': old['lba'], 'system_identifier': 'PLAYSTATION',
              'release_image': False}
    (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
