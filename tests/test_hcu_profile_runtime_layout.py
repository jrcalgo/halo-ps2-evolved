"""The two sound self-owner indices use the actual PS2 target ABI layout."""
from __future__ import annotations

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import hcu_profile_runtime_layout as layout  # noqa: E402


def test_target_compiler_sound_layout_and_dependency_sensitive_cache(tmp_path):
    compiler = (ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc")
    if not compiler.is_file() or shutil.which("python3") is None:
        import pytest
        pytest.skip("PS2 target compiler is unavailable")
    schema_elf = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
    report = layout.run_probe(tmp_path / "probe", schema_elf)

    sound = report["layout"]["sound_permutation"]
    assert sound["cache_tag_index_offset"] == 52
    assert sound["runtime_tag_index_offset"] == 60
    assert sound["size"] == 124
    assert sound["source_members"] == {
        "cache_tag_index": "sound_permutation.unknown2",
        "runtime_tag_index": "sound_permutation.unknown3",
    }
    assert report["inputs"]["schema_elf_sha256"] == layout.sha256(schema_elf)
    assert report["inputs"]["sound_definitions_header_sha256"]
    assert report["inputs"]["schema_effects_source_sha256"]
    assert report["object_sha256"] == layout.sha256(
        tmp_path / "probe/sound_permutation_layout.o")

    cached = layout.run_probe(tmp_path / "probe", schema_elf)
    assert cached["cache_hit"] is True
    assert cached["cache_key"] == report["cache_key"]
    assert cached["object_sha256"] == report["object_sha256"]

    rebuilt = layout.run_probe(tmp_path / "independent-clean-probe", schema_elf)
    assert rebuilt["cache_hit"] is False
    assert rebuilt["cache_key"] == report["cache_key"]
    assert rebuilt["inputs"] == report["inputs"]
    assert rebuilt["object_sha256"] == report["object_sha256"]

    changed_inputs = dict(report["inputs"])
    changed_dependencies = dict(changed_inputs["dependency_hashes"])
    header = next(path for path in changed_dependencies
                  if path.endswith("/source/sound/sound_definitions.h"))
    changed_dependencies[header] = "0" * 64
    changed_inputs["dependency_hashes"] = changed_dependencies
    assert layout.canonical_key(changed_inputs) != report["cache_key"]
