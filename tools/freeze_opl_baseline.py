#!/usr/bin/env python3
"""Freeze caller-selected ISO candidates; never infer historical test identity.

Retains a copy, directory/file hashes, extracted menu/guest ELFs, tracked source
archives and binary diffs, and the currently resolved toolchain identities.
The current SDK is NOT asserted to be the SDK used for an older ISO.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from build_toolchain import ROOT, environment
from build_opl_boot_probes import sha

SECTOR = 2048


def iso_inventory(iso, destination):
    rows = []
    with iso.open('rb') as stream:
        stream.seek(16 * SECTOR)
        pvd = stream.read(SECTOR)
        if pvd[:7] != b'\x01CD001\x01':
            raise ValueError('not an ISO9660 primary volume')
        visited = set()

        def walk(lba, size, prefix):
            if (lba, size) in visited:
                raise ValueError('cyclic or aliased directory')
            visited.add((lba, size))
            if size > 16 * 1024 * 1024 or lba * SECTOR + size > iso.stat().st_size:
                raise ValueError('directory out of bounds')
            stream.seek(lba * SECTOR)
            directory = stream.read(size)
            offset = 0
            while offset + 33 <= len(directory):
                length = directory[offset]
                if not length:
                    offset = (offset // SECTOR + 1) * SECTOR
                    continue
                record = directory[offset:offset + length]
                if length < 34 or offset % SECTOR + length > SECTOR:
                    raise ValueError('invalid directory record')
                raw = record[33:33 + record[32]]
                offset += length
                if raw in (b'\x00', b'\x01'):
                    continue
                name = raw.decode('ascii').split(';')[0]
                if name in ('.', '..') or '/' in name or '\\' in name:
                    raise ValueError('unsafe file name')
                path = prefix + name
                extent = int.from_bytes(record[2:6], 'little')
                count = int.from_bytes(record[10:14], 'little')
                if record[25] & 2:
                    walk(extent, count, path + '/')
                    continue
                if extent * SECTOR + count > iso.stat().st_size:
                    raise ValueError('file out of bounds')
                stream.seek(extent * SECTOR)
                digest = hashlib.sha256()
                left = count
                extract = path == 'HPS2_000.01' or path.startswith('E/') and path.endswith('.ELF')
                output = None
                if extract:
                    target = destination / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    output = target.open('xb')
                try:
                    while left:
                        block = stream.read(min(left, 1024 * 1024))
                        if not block:
                            raise ValueError('short file read')
                        digest.update(block)
                        if output:
                            output.write(block)
                        left -= len(block)
                finally:
                    if output:
                        output.close()
                rows.append({'path': path, 'lba': extent, 'bytes': count,
                             'sha256': digest.hexdigest(), 'extracted_elf': extract})
        walk(int.from_bytes(pvd[158:162], 'little'), int.from_bytes(pvd[166:170], 'little'), '')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'qualification': 'not tested', 'historical_identity': 'unknown',
              'build_flags_for_existing_isos': 'unknown; no matching build record supplied',
              'isos': [], 'sources': [], 'current_toolchain': []}
    for index, iso in enumerate(args.iso):
        iso = iso.resolve()
        dest = out / f'candidate-{index + 1}'
        dest.mkdir()
        copy = dest / iso.name
        subprocess.run(['cp', '--reflink=auto', '--', str(iso), str(copy)], check=True)
        rows = iso_inventory(copy, dest / 'elfs')
        report['isos'].append({'original': str(iso), 'copy': str(copy),
                               'sha256': sha(copy), 'files': rows})
        copy.chmod(0o444)
    for name in ('.', 'submodules/halo-ps2', 'submodules/halo-ce-universal',
                 'submodules/ps2sdk', 'submodules/opl', 'submodules/ps2link'):
        source = ROOT / name
        label = 'parent' if name == '.' else source.name
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        subprocess.run(['git', '-C', str(source), 'archive', '--format=tar',
                        '-o', str(out / f'{label}.tar'), 'HEAD'], check=True)
        diff = subprocess.check_output(['git', '-C', str(source), 'diff', '--binary', 'HEAD'])
        (out / f'{label}.diff').write_bytes(diff)
        status = subprocess.check_output(['git', '-C', str(source), 'status', '--short'], text=True)
        report['sources'].append({'source': name, 'revision': revision, 'status': status,
                                  'archive_sha256': sha(out / f'{label}.tar'),
                                  'diff_sha256': sha(out / f'{label}.diff')})
    # Preserve parent untracked implementation sources too, without sweeping
    # unrelated untracked data or credentials into the snapshot.
    for name in ('src', 'tools', 'config', 'tests'):
        shutil.copytree(ROOT / name, out / 'working-parent' / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    env = environment()[2]
    sdk = Path(env['PS2SDK'])
    report['current_sdk_resolved'] = str(sdk.resolve())
    paths = [sdk / 'ee/startup/linkfile', *sorted((sdk / 'ee/lib').glob('*.a')),
             *sorted((sdk / 'iop/irx').glob('*.irx'))]
    compiler = shutil.which('mips64r5900el-ps2-elf-gcc', path=env['PATH'])
    if compiler:
        report['compiler_version'] = subprocess.check_output([compiler, '--version'], env=env, text=True)
        paths.append(Path(compiler))
        crt = subprocess.check_output([compiler, '-print-file-name=crt0.o'], env=env, text=True).strip()
        if Path(crt).is_file():
            paths.append(Path(crt))
    for path in paths:
        report['current_toolchain'].append({'path': str(path), 'resolved': str(path.resolve()), 'sha256': sha(path)})
    (out / 'baseline.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'baseline.json')


if __name__ == '__main__':
    main()
