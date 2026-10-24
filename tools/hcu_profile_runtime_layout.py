"""Compile a pinned PS2 target-layout probe for CE runtime identity fields."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from build_toolchain import ROOT, environment
from hcu_ps2_closure import FLAGS, HCU, MANIFEST_PATH


DEFAULT_SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
PROBE_SOURCE = r'''#include "cseries.h"
#include <stddef.h>
#include "sound/sound_definitions.h"
typedef char hcu_target_pointer_is_32[sizeof(void *) == 4 ? 1 : -1];
typedef char hcu_target_long_is_32[sizeof(long) == 4 ? 1 : -1];
typedef char hcu_cache_tag_index_is_52[offsetof(struct sound_permutation, unknown2) == 52 ? 1 : -1];
typedef char hcu_runtime_tag_index_is_60[offsetof(struct sound_permutation, unknown3) == 60 ? 1 : -1];
__attribute__((used, section(".hcu_profile_layout")))
const unsigned long hcu_profile_sound_permutation_layout[3] = {
	(unsigned long)sizeof(struct sound_permutation),
	(unsigned long)offsetof(struct sound_permutation, unknown2),
	(unsigned long)offsetof(struct sound_permutation, unknown3)
};
'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_key(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout


def _verify_owner_semantics() -> dict:
    effects = HCU / "port/linux/game/tag_schema_effects.c"
    sound_header = HCU / "source/sound/sound_definitions.h"
    source_text = effects.read_text()
    required = (
        "/* (cache_tag_index and runtime_tag_index) */",
        "tag_validate_tag_get(validation, (long)permutation->unknown2, SOUND_DEFINITION_TAG) != base",
        "permutation->unknown3 != permutation->unknown2",
        "permutation->unknown2 = (unsigned long)tag_index;",
        "permutation->unknown3 = (unsigned long)tag_index;",
    )
    missing = [text for text in required if text not in source_text]
    if missing:
        raise RuntimeError("sound owner-identity semantics changed; review probe: " + "; ".join(missing))
    return {
        "schema_effects_source": effects.relative_to(ROOT).as_posix(),
        "schema_effects_source_sha256": sha256(effects),
        "sound_definitions_header": sound_header.relative_to(ROOT).as_posix(),
        "sound_definitions_header_sha256": sha256(sound_header),
        "owner_semantics": "sound_check validates unknown2 as this sound tag's cache index and unknown3 as the same runtime index; mismatches set both to the current tag index",
    }


def _dependency_paths(compiler: Path, flags: list[str], source: Path,
                      cwd: Path, env: dict[str, str]) -> list[Path]:
    text = _run([str(compiler), *flags, "-M", "-MT", "hcu_profile_runtime_layout.o",
                 str(source)], cwd, env)
    body = text.replace("\\\n", " ").split(":", 1)[1]
    dependencies = [Path(item).resolve() for item in shlex.split(body)]
    unique = {path for path in dependencies if path.is_file()}
    unique.add(source.resolve())
    return sorted(unique, key=lambda path: str(path))


def run_probe(output_dir: Path, schema_elf: Path, force: bool = False) -> dict:
    output_dir = output_dir.resolve()
    schema_elf = schema_elf.resolve()
    if not schema_elf.is_file():
        raise RuntimeError(f"schema ELF is missing: {schema_elf}")
    build, prefix, env, _jobs = environment()
    manifest = json.loads(MANIFEST_PATH.read_text())
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    objcopy = prefix / "ee/bin/mips64r5900el-ps2-elf-objcopy"
    readelf = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    if not compiler.is_file() or not objcopy.is_file() or not readelf.is_file():
        raise RuntimeError("target compiler, objcopy, or readelf is missing; finish the compiler toolchain first")

    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / "sound_permutation_layout.c"
    source.write_text(PROBE_SOURCE)
    semantics = output_dir / "halo_ps2_msvc_semantics.h"
    _run([sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
          "--output", str(semantics), "--all-inlines",
          "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
          "--inlines", str(HCU / "port/include/xdk")], ROOT, env)
    prefix_header = HCU / manifest["prefix"]
    include_flags = ["-I" + str(HCU / item) for item in manifest["include_dirs"]]
    include_flags.extend(("-I" + str(prefix / "ps2sdk/common/include"),
                          "-I" + str(prefix / "ps2sdk/ee/include")))
    # Generated source/header paths must not make independent clean builds
    # different. Keep actual commands in the report, but normalize their
    # directory in both the object's debug information and its input identity.
    flags = [*FLAGS, *include_flags, "-include", str(prefix_header),
             "-include", str(semantics),
             f"-ffile-prefix-map={output_dir}=/hcu-c1-layout",
             f"-fdebug-prefix-map={output_dir}=/hcu-c1-layout"]
    deps = _dependency_paths(compiler, flags, source, ROOT, env)
    def stable_path(value: str) -> str:
        return value.replace(output_dir.as_posix(), "/hcu-c1-layout")
    dependency_hashes = {stable_path(path.as_posix()): sha256(path) for path in deps}
    owner_pins = _verify_owner_semantics()
    compiler_version = _run([str(compiler), "--version"], ROOT, env).splitlines()[0]
    inputs = {
        "compiler_path": compiler.as_posix(),
        "compiler_sha256": sha256(compiler),
        "compiler_version": compiler_version,
        "objcopy_sha256": sha256(objcopy),
        "readelf_sha256": sha256(readelf),
        "flags": [stable_path(flag) for flag in flags],
        "manifest_sha256": sha256(MANIFEST_PATH),
        "prefix_header": prefix_header.relative_to(ROOT).as_posix(),
        "prefix_sha256": sha256(prefix_header),
        "semantics_sha256": sha256(semantics),
        "schema_elf": schema_elf.as_posix(),
        "schema_elf_sha256": sha256(schema_elf),
        "hcu_commit": subprocess.check_output(
            ["git", "-C", str(HCU), "rev-parse", "HEAD"], text=True).strip(),
        "probe_source_sha256": sha256(source),
        "probe_tool_sha256": sha256(Path(__file__).resolve()),
        "dependency_hashes": dependency_hashes,
        **owner_pins,
    }
    key = canonical_key(inputs)
    result_path = output_dir / "result.json"
    object_path = output_dir / "sound_permutation_layout.o"
    raw_path = output_dir / "layout-section.bin"
    prior = None
    if result_path.is_file():
        try:
            prior = json.loads(result_path.read_text())
        except (ValueError, OSError):
            prior = None
    if (not force and prior and prior.get("cache_key") == key and
            object_path.is_file() and sha256(object_path) == prior.get("object_sha256") and
            raw_path.is_file() and sha256(raw_path) == prior.get("layout_section_sha256")):
        # Cache use is execution metadata, not a mutation of retained evidence.
        return {**prior, "cache_hit": True}

    command = [str(compiler), *flags, "-c", str(source), "-o", str(object_path)]
    compile_log = _run(command, ROOT, env)
    (output_dir / "compile.log").write_text("$ " + " ".join(command) + "\n" + compile_log)
    elf_header = _run([str(readelf), "-h", str(object_path)], ROOT, env)
    if "Class:                             ELF32" not in elf_header or "Type:                              REL (Relocatable file)" not in elf_header:
        raise RuntimeError("layout probe output is not an ELF32 relocatable object")
    _run([str(objcopy), "--dump-section", f".hcu_profile_layout={raw_path}", str(object_path)], ROOT, env)
    raw = raw_path.read_bytes()
    if len(raw) != 12:
        raise RuntimeError(f"layout section has unexpected size: {len(raw)}")
    import struct
    size_bytes, cache_offset, runtime_offset = struct.unpack("<III", raw)
    if (cache_offset, runtime_offset) != (52, 60):
        raise RuntimeError(f"target layout changed: unknown2={cache_offset}, unknown3={runtime_offset}")
    report = {
        "format": "hcu-c1-target-runtime-layout-v1",
        "status": "passed",
        "cache_hit": False,
        "cache_key": key,
        "inputs": inputs,
        "layout": {
            "sound_permutation": {
                "size": size_bytes,
                "cache_tag_index_offset": cache_offset,
                "runtime_tag_index_offset": runtime_offset,
                "source_members": {"cache_tag_index": "sound_permutation.unknown2", "runtime_tag_index": "sound_permutation.unknown3"},
            }
        },
        "target_object": display_path(object_path),
        "object_sha256": sha256(object_path),
        "layout_section_sha256": sha256(raw_path),
        "compiler_command": command,
        "limits": "Target compiler layout probe only; no payload normalization, PS2 memory budget, or profile admission claim.",
    }
    result_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/m2-c1-runtime-layout")
    parser.add_argument("--schema-elf", type=Path, default=DEFAULT_SCHEMA_ELF)
    parser.add_argument("--force", action="store_true", help="recompile even when all pinned inputs match")
    args = parser.parse_args()
    report = run_probe(args.output_dir, args.schema_elf, args.force)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
