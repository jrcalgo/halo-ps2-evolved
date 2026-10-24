import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runtime_metadata", ROOT / "tools/build_hcu_runtime_metadata.py")
meta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(meta)

CORPUS_DIRS = (
    ROOT / os.environ.get("HCU_C1_PROFILES", "build/m2-c1-corpus-primary-v3"),   # preferred; may be corrupted
    ROOT / os.environ.get("HCU_C1_REBUILD", "build/m2-c1-corpus-rebuild-v3"),    # intact pinned fallback
)
# Frozen metadata pins, keyed by corpus directory name. A corpus without a recorded
# pin still gets every manifest-derived check; only the frozen blob pin is skipped.
FROZEN_PINS = {
    "m2-c1-corpus-primary-v1": (21616, "0c978cf937c42ee773da717e203bdae9953810ebad5b0e36aa75eb7a4b98a7e1"),
    "m2-c1-corpus-rebuild-v1": (21616, "0c978cf937c42ee773da717e203bdae9953810ebad5b0e36aa75eb7a4b98a7e1"),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _select_corpus() -> tuple[Path, Path, Path]:
    for corpus in CORPUS_DIRS:
        manifest = corpus / "ui.json"
        package = corpus / "ui.hcp"
        if manifest.is_file() and package.is_file() and \
                _sha(package) == json.loads(manifest.read_text())["package_sha256"]:
            return manifest, package, corpus
    pytest.fail("no UI HCP in the corpus directories matches its manifest package_sha256")


def _expected_bitmap_count(manifest_path: Path) -> int:
    """Historical UI count (368) holds only without pinned media consumer exclusions;
    otherwise the count is the manifest's BITM chunk-binding count."""
    m = json.loads(manifest_path.read_text())
    if "consumer_exclusions" not in m.get("media", {}):
        return 368
    return sum(1 for x in m.get("chunk_bindings", []) if x.get("kind") == "BITM")


def test_real_ui_metadata_is_deterministic_and_has_frozen_counts():
    manifest, package, corpus = _select_corpus()
    a = meta.build(manifest, package)
    b = meta.build(manifest, package)
    assert a == b
    bitmap_count = _expected_bitmap_count(manifest)
    assert struct.unpack_from("<4sHHIIIIII", a) == (b"HCM1", 1, 32, len(a), 1, bitmap_count, 1, 75, 0)
    pin = FROZEN_PINS.get(corpus.name)
    if pin is not None:
        assert len(a) == pin[0]
        assert hashlib.sha256(a).hexdigest() == pin[1]


def test_decoder_validates_and_decodes_real_ui(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("cc unavailable for HCM1 decoder harness")
    manifest, package, _corpus = _select_corpus()
    blob = meta.build(manifest, package)
    bitmap_count = _expected_bitmap_count(manifest)
    data = tmp_path / "ui.hcm"
    data.write_bytes(blob)
    harness = tmp_path / "decode.c"
    harness.write_text(r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "stream/hcu_profile_metadata.h"
int main(int argc,char **argv) {
 FILE *f=fopen(argv[1],"rb"); long n; uint8_t *p; uint8_t expected[32];
 hcu_profile_metadata_view v; void *storage; unsigned bitmap_expected;
 if(!f)return 10; fseek(f,0,SEEK_END); n=ftell(f); rewind(f); p=(uint8_t*)malloc(n); fread(p,1,n,f); fclose(f);
 if(argc<4)return 11; bitmap_expected=(unsigned)atoi(argv[3]); { FILE *h=fopen(argv[2],"rb"); if(!h)return 12; fread(expected,1,32,h); fclose(h); }
 storage=malloc(30000); if(hcu_profile_metadata_decode(p,n,expected,1,storage,30000,&v))return 13;
 if(v.bitmap_count!=bitmap_expected || v.cbsp_count!=1 || v.resource_range_count!=75)return 14;
 if(hcu_profile_metadata_decode(p,n,expected,2,storage,30000,&v)!=HCU_PROFILE_METADATA_E_PROFILE)return 15;
 if(hcu_profile_metadata_decode(p,n-1,expected,1,storage,30000,&v)!=HCU_PROFILE_METADATA_E_FORMAT)return 17;
 { uint8_t saved[4]; memcpy(saved,p+16,4); p[16]=255; p[17]=p[18]=p[19]=255;
   if(hcu_profile_metadata_decode(p,n,expected,1,storage,30000,&v)!=HCU_PROFILE_METADATA_E_FORMAT)return 18;
   memcpy(p+16,saved,4); }
 p[n-1]^=1; if(hcu_profile_metadata_decode(p,n,expected,1,storage,30000,&v)!=HCU_PROFILE_METADATA_E_HASH)return 16;
 p[n-1]^=1; expected[0]^=1;
 if(hcu_profile_metadata_decode(p,n,expected,1,storage,30000,&v)!=HCU_PROFILE_METADATA_E_HASH)return 19;
 return 0;
}''')
    digest = tmp_path / "digest"
    digest.write_bytes(hashlib.sha256(blob).digest())
    exe = tmp_path / "decode"
    subprocess.run([cc, "-std=c99", "-I", str(ROOT / "src"),
                    "-I", str(ROOT / "submodules/halo-ps2/engine/src"),
                    "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
                    str(harness), str(ROOT / "src/stream/hcu_profile_metadata.c"),
                    str(ROOT / "src/stream/sha256.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe), str(data), str(digest), str(bitmap_count)], check=True)


def test_decoded_view_feeds_mount_prepare_signature(tmp_path):
    """Compile-time check: the decoded view's arrays are the exact types that
    hcu_profile_mount_prepare takes, so no copy or cast is needed."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("cc unavailable for view/prepare signature check")
    source = tmp_path / "feed.c"
    source.write_text(r'''#include "stream/hcu_profile_metadata.h"
int feed(const hcu_profile_metadata_view *v, const hcu_asset_profile_view *profile,
	const hcu_map_catalog_entry *catalog, const ctag_mount_backend *backend,
	hcu_profile_mount *mount, void *reloc, size_t reloc_bytes,
	void *scratch, size_t scratch_bytes, hcu_profile_source_read_fn read, void *ctx)
{
	if (v->cbsp_count > 0xffffu || v->resource_range_count > 0xffffffffu) return -1;
	return hcu_profile_mount_prepare(mount, profile, v->profile_id, catalog,
		v->cbsp_bindings, (uint16_t)v->cbsp_count, v->resource_ranges,
		v->resource_range_count, read, ctx, backend, 2u * 1024u * 1024u,
		reloc, reloc_bytes, scratch, scratch_bytes);
}
''')
    subprocess.run([cc, "-std=c99", "-Wall", "-Werror", "-fsyntax-only", "-I", str(ROOT / "src"),
                    "-I", str(ROOT / "submodules/halo-ps2/engine/src"),
                    "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
                    str(source)], check=True)
