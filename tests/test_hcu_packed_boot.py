"""Decode actual boot inputs with the C runtime used on the console."""
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2.hp2 import lz4_compress
import build_hcu_runtime_metadata as metadata
import hcu_mp_map_table as maps


@pytest.fixture(scope="module")
def decoder(tmp_path_factory):
    out = tmp_path_factory.mktemp("boot-packing")
    source = out / "decode.c"
    source.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stream/hcu_irx_unpack.h"
#include "stream/hp2.h"
static unsigned char *read_file(char *path, size_t *n) {
 FILE *f=fopen(path,"rb"); unsigned char *p;
 if(!f)exit(2);fseek(f,0,SEEK_END);*n=ftell(f);rewind(f);
 p=malloc(*n);if(fread(p,1,*n,f)!=*n)exit(3);fclose(f);return p;
}
int main(int argc,char **argv) {
 size_t rn,pn;unsigned char *raw,*packed,*dst;const void *got;
 if(argc!=4)return 4;raw=read_file(argv[1],&rn);packed=read_file(argv[2],&pn);
 if(argv[3][0]=='i') {
  got=hcu_irx_unpack(packed,pn,rn);if(!got||memcmp(got,raw,rn))return 5;
  if(hcu_irx_unpack(packed,1,rn)||hcu_irx_unpack(packed,pn,16385)||hcu_irx_unpack(NULL,pn,rn))return 6;
 } else {
  dst=malloc(rn);if(lz4_decode(packed,pn,dst,rn)!=(long)rn||memcmp(dst,raw,rn))return 7;free(dst);
 }
 free(raw);free(packed);return 0;
}
''')
    engine = ROOT / "submodules/halo-ps2/engine"
    binary = out / "decode"
    subprocess.run(["cc", "-std=c99", "-ffunction-sections", "-fdata-sections",
                    "-Wl,--gc-sections", "-I" + str(ROOT / "src"),
                    "-I" + str(engine / "src"), str(source),
                    str(ROOT / "src/stream/hcu_irx_unpack.c"),
                    str(engine / "src/stream/hp2.c"), "-o", str(binary)], check=True)
    return binary


def check_decode(decoder, tmp_path, raw, kind):
    original = tmp_path / "raw"
    packed = tmp_path / "packed"
    original.write_bytes(raw)
    packed.write_bytes(lz4_compress(raw))
    subprocess.run([str(decoder), str(original), str(packed), kind], check=True)


@pytest.mark.parametrize("name", ["iomanX", "fileXio", "libsd", "sdrdrv"])
def test_sdk_irx_round_trip_and_rejection(decoder, tmp_path, name):
    path = ROOT / f"build/toolchain/install/ps2sdk/iop/irx/{name}.irx"
    if not path.exists():
        pytest.skip("PS2SDK build required")
    check_decode(decoder, tmp_path, path.read_bytes(), "irx")


@pytest.mark.parametrize("name", [row[2] for row in maps.ROWS])
def test_map_metadata_round_trip(decoder, tmp_path, name):
    row = f"{name}_mounted_gunner_4p4bot"
    folder = ROOT / "build/c3" / name / "pkg" / row
    if not (folder / f"{row}.hcp").exists():
        pytest.skip("prepared map package required")
    raw = metadata.build(folder / f"{row}.json", folder / f"{row}.hcp")
    check_decode(decoder, tmp_path, raw, "metadata")
