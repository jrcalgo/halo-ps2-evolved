"""Cross-compile the bounded EE worker; does not link or run a viewer."""
import hashlib
import subprocess
from build_toolchain import ROOT, environment, save


def main():
    build, prefix, env, _ = environment()
    output = build / 'streaming-ee'
    output.mkdir(parents=True, exist_ok=True)
    compiler = prefix / 'ee/bin/mips64r5900el-ps2-elf-gcc'
    sources = ['src/stream/staging.c', 'src/stream/reader_ee.c']
    for source in sources:
        subprocess.run([str(compiler), '-D_EE', '-std=gnu11', '-Wall',
                        '-Wextra', '-Werror', '-G0', '-Isrc',
                        '-Isubmodules/halo-ps2/engine/src',
                        '-I'+str(prefix/'ps2sdk/ee/include'),
                        '-I'+str(prefix/'ps2sdk/common/include'),
                        '-c', source, '-o', str(output/(source.rsplit('/', 1)[1][:-2]+'.o'))],
                       cwd=ROOT, env=env, check=True)
    inputs = sources + ['src/stream/staging.h', 'src/stream/reader_ee.h',
                        'tools/build_streaming.py']
    save(output/'result.json', {
        'status': 'objects-compiled',
        'compiler': subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0],
        'sources': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
        'limits': 'Object compilation only; no ELF link, EE execution or viewer integration.'})
    print(output/'result.json')


if __name__ == '__main__':
    main()
