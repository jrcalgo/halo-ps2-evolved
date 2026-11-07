#!/usr/bin/env python3
"""Build three incremental OPL probe ISOs, retaining exact input identities."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
from build_toolchain import ROOT, environment
from build_hcu_opl_iso import publish_dvd_path_table, publish_ps2_logo, _root_entries


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/opl-qualification')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = environment()[2]
    payload = out / 'PROBE.BIN'
    payload.write_bytes(bytes((i * 37 + i // 256) & 255 for i in range(16421)))
    cnf = out / 'SYSTEM.CNF'
    cnf.write_bytes(b'BOOT2 = cdrom0:\\HPS2_000.01;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n')
    pad = out / 'ZZPAD.BIN'
    pad.write_bytes(bytes(512 * 2048))
    manifest = {'hardware_accepted': False, 'payload_sha256': sha(payload),
                'sdk_resolved': str(Path(env['PS2SDK']).resolve()), 'probes': [],
                'source_sha256': {name: sha(ROOT / name) for name in (
                    'src/probe/opl_boot.c', 'src/stream/hcu_boot_diag.c',
                    'src/stream/hcu_boot_diag.h', 'src/stream/hcu_boot_entry.S',
                    'src/stream/hcu_storage_boot.c', 'src/stream/hcu_storage_boot.h',
                    'src/stream/hcu_filexio_irx.S', 'src/stream/sha256.c',
                    'submodules/halo-ps2/engine/src/stream/file.c',
                    'submodules/halo-ps2/engine/src/stream/file.h',
                    'submodules/halo-ps2/engine/src/stream/iso9660_name.h',
                    'tools/ee-opl-probe.mk', 'tools/build_hcu_opl_iso.py',
                    'tools/build_opl_boot_probes.py')},
                'sdk_inputs_sha256': {name: sha(Path(env['PS2SDK']) / name) for name in (
                    'ee/lib/libdebug.a', 'ee/lib/libeedebug.a', 'ee/lib/libfileXio.a',
                    'ee/lib/libkernel.a', 'ee/startup/linkfile',
                    'iop/irx/iomanX.irx', 'iop/irx/fileXio.irx')}}
    for level in (1, 2, 3):
        folder = out / f'probe-{level}'
        folder.mkdir(exist_ok=True)
        command = ['make', '-f', 'tools/ee-opl-probe.mk', f'PROBE_LEVEL={level}',
                   f'PROBE_OUTPUT={folder}', 'all', '-j4']
        result = subprocess.run(command, env=env, cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (folder / 'build.log').write_text(result.stdout)
        result.check_returncode()
        elf = folder / 'HPS2_000.01'
        iso = folder / f'HALO_DIAG_{level}.iso'
        subprocess.run(['xorriso', '-as', 'mkisofs', '-iso-level', '2', '--norock',
                        '-graft-points', '--sort-weight', '500000', 'ZZPAD.BIN',
                        '--sort-weight', '300000', 'HPS2_000.01', '-sysid', 'PLAYSTATION',
                        '-V', 'HALO_PS2',
                        '-o', str(iso), f'SYSTEM.CNF={cnf}', f'ZZPAD.BIN={pad}',
                        f'HPS2_000.01={elf}', f'PROBE.BIN={payload}'], check=True)
        publish_dvd_path_table(iso)
        publish_ps2_logo(iso, ROOT / 'assets/ps2/boot-logo-ntsc.bin')
        # Verify packaged payload bytes independently of the publisher's inputs.
        with iso.open('rb') as handle:
            entries = {name: (lba, size) for name, lba, size in _root_entries(handle)}
            for name, source in [('SYSTEM.CNF', cnf), ('HPS2_000.01', elf), ('PROBE.BIN', payload)]:
                lba, size = entries[name]
                handle.seek(lba * 2048)
                if hashlib.sha256(handle.read(size)).hexdigest() != sha(source):
                    raise RuntimeError(f'{name} differs inside {iso}')
        manifest['probes'].append({'level': level, 'elf': str(elf), 'elf_sha256': sha(elf),
                                  'iso': str(iso), 'iso_sha256': sha(iso), 'map_sha256': sha(folder / 'probe.map'), 'command': command})
    (out / 'probes.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(out / 'probes.json')


if __name__ == '__main__':
    main()
