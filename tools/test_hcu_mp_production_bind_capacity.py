#!/usr/bin/env python3
"""Exercise the real HCU binder with the default and Step 8 candidate layouts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    compiler = shutil.which("cc")
    if not compiler:
        raise SystemExit("C compiler not found")
    out = ROOT / "build" / f"mp-production-binder-capacity-{time.time_ns()}"
    out.mkdir(parents=True)
    binary = out / "production-binder-capacity"
    linkmap = out / "production-binder-capacity.map"
    source = ROOT / "tests/hcu_mp_production_bind_capacity_main.c"
    memory_source = HCU / "port/ps2/src/ps2_memory.c"
    parent_binder = ROOT / "src/stream/hcu_memory_bind.c"
    memory_profile = ROOT / "src/stream/hcu_memory_profile.c"
    arena_source = ENGINE / "core/mem.c"
    command = [compiler, *host_abi32_flags(), "-isystem", "/usr/include",
               "-std=gnu99", "-O2", "-g", "-Wall", "-Wextra",
               "-DHALO_PS2_NO_BOOTSTRAP_MEMORY",
               "-I" + str(ROOT / "tests/hcu_ps2_memory_shim"),
               "-I" + str(ENGINE), "-I" + str(HCU / "port/ps2/include"),
               "-I" + str(ROOT / "src"), str(memory_source),
               str(parent_binder), str(memory_profile), str(source), str(arena_source),
               "-Wl,-Map," + str(linkmap), "-o", str(binary)]
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if built.returncode:
        (out / "compile.log").write_text(built.stdout + built.stderr)
        raise SystemExit(f"compile failed; see {out / 'compile.log'}")
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    log = out / "run.log"
    log.write_text(run.stdout + run.stderr)
    if run.returncode:
        raise SystemExit(f"production binder capacity test failed; see {log}\n"
                         f"{run.stdout}{run.stderr}")

    required = (
        "production-binder-default tag=4477120 bsp=1814336 "
        "required_bsp=1993712 bsp_shortfall=179376 texture=4194304 "
        "gap=16 ready=1 candidate_fit=0",
        "production-binder-recarved tag=4477120 bsp=1993712 "
        "map=6470832 texture=4014928 total=10485760 "
        "contiguous_views=1 parent_bytes_unchanged=1 guards=1 ready=1",
        "profile-v1 tag=4685920 bsp=1993744 map_parent=6679680 internal_guard=16 texture=3806080 render_parent=3806080 claims=834960 bsp_alignment=0 texture_alignment=0",
        "profile-v1-invalid version=1 alignment=1 bounds=1 used=1 adjacency=1 plan_atomic=1",
        "profile-v1-provider-failure rollback=1 cursors=1 provider-spans=1 canary=1",
        "provider-locked-rebind rejected=1 ready0=unchanged ready1=unchanged spans=unchanged cursors=unchanged contents=unchanged",
    )
    for marker in required:
        if marker not in run.stdout:
            raise SystemExit(f"missing diagnostic marker {marker!r}; see {log}")

    binder_text = parent_binder.read_text()
    main_text = (ROOT / "src/stream/hcu_main.c").read_text()
    build_text = (ROOT / "tools/ee-world.mk").read_text()
    map_text = (ROOT / "src/stream/hcu_map_service.c").read_text()
    ps2_cache_text = (HCU / "port/ps2/src/ps2_cache.c").read_text()
    ps2_texture_text = (HCU / "port/ps2/src/ps2_sound_cache.c").read_text()
    port_manifest = json.loads((HCU / "port/ps2/port.json").read_text())
    for marker in (
        "arena_alloc(bsp, tag_cache_bytes, 16)",
        "(unsigned long)(bsp->cap - bsp->used)",
        "physical_memory_bind_texture_cache(texture->base",
    ):
        if marker not in binder_text:
            raise SystemExit(f"production binder source contract changed: {marker}")
    for marker in (
        "static int hcu_step8_mp_candidate_recarve",
        "const size_t map_bytes = 6470832u",
        "const size_t texture_bytes = 4014928u",
        "bsp->cap = map_bytes",
        "texture->base = bsp->base + map_bytes",
        "texture->cap = texture_bytes",
        "hcu_step8_mp_candidate_recarve(&layout)",
    ):
        if marker not in main_text:
            raise SystemExit(f"candidate recarve source contract changed: {marker}")
    if "WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC ?= 0" not in build_text:
        raise SystemExit("candidate recarve must remain disabled in default profile")
    if "WORLD_HCU_TAG_CACHE_BYTES ?= 2097152" not in build_text:
        raise SystemExit("default production tag-cache size changed; reassess this report")
    if "physical_memory_get_tag_cache_size()" not in map_text or \
       "physical_memory_get_structure_bsp_cache_size()" not in ps2_cache_text or \
       "texture_cache_steal_memory" in ps2_texture_text:
        raise SystemExit("CE map/BSP/texture provider ownership changed; reassess the test")
    if "source/cache/xbox_texture_cache.c" not in port_manifest["exclude_sources"] or \
       "port/ps2/src/ps2_sound_cache.c" not in port_manifest["port_sources"]:
        raise SystemExit("PS2 texture-cache source selection changed; reassess this test")
    if "return bitmap;" not in ps2_texture_text or \
       "void texture_cache_open(\n\tvoid)\n{\n}" not in ps2_texture_text:
        raise SystemExit("PS2 CE texture-cache adapter behavior changed; reassess this test")

    manifest = {
        "schema": "hcu-mp-production-binder-capacity-v1",
        "status": "passed-host-runtime-and-source-audit",
        "profile": {
            "default_current_bsp_bytes": 6291456,
            "default_texture_bytes": 4194304,
            "candidate_tag_bytes": 4477120,
            "candidate_bsp_bytes": 1993712,
            "candidate_map_bytes": 6470832,
            "candidate_texture_bytes": 4014928,
            "candidate_total_bytes": 10485760,
        },
        "host_ilp32_runtime": True,
        "ee_or_pcsx2_qualification": False,
        "production_budget_or_admission_changed": False,
        "scope": "real parent binder + real HCU PS2 memory provider, exercised with default guarded layout and the existing opt-in candidate recarve geometry; no map admission or renderer claims",
        "source_evidence": {
            "binder": "src/stream/hcu_memory_bind.c:19-78",
            "candidate_recarve_and_macro_gate": "src/stream/hcu_main.c:196-229, 326-334",
            "diagnostic_disabled_by_default": "tools/ee-world.mk:47-54",
            "tag_capacity_preflight": "src/stream/hcu_map_service.c:224-260 (preflight_ctag_stream), 668-828 (hcu_map_service_preflight; tag_cache_size at 791-803)",
            "CE BSP and texture adapter consumers": "submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:320-336, 580-590, 770-835; submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c:51-57, 222-235; submodules/halo-ce-universal/port/ps2/port.json:20-40, 62-67",
        },
        "output": run.stdout,
        "interpretation": [
            "With the ordinary guarded v2 layout, the production binder accepts and marks the provider ready at candidate tag size, but BSP capacity is only the current_bsp remainder (1,814,336 bytes), 179,376 bytes below the corpus candidate requirement. The separate texture view also begins 16 bytes after current_bsp, so this default layout is not one contiguous map+texture span.",
            "The opt-in recarve already present in hcu_main.c changes only the map/texture view boundaries: the same actual parent binder then exposes exact candidate tag, BSP, and texture capacities as adjacent views, while the total underlying BSP+texture bytes stay 10 MiB and canaries remain valid.",
            "Do not apply the Xbox texture-cache page-count constant as the PS2 capacity: port/ps2/port.json excludes source/cache/xbox_texture_cache.c and selects port/ps2/src/ps2_sound_cache.c, whose texture hardware-format adapter returns the tag bitmap and whose texture-cache lifecycle functions are empty. Actual texture upload/eviction ownership is in halo-ps2's GS renderer and its pack/cache path; it still requires target/PCSX2 evidence for this recarve.",
            "This proves a diagnostic capacity layout is representable through the existing provider APIs. It does not qualify every MP map load, renderer texture residency, GS transfer, EE/PCSX2 behavior, or production map admission. Keep the recarve opt-in pending those independent acceptance gates.",
        ],
        "artifacts": {
            "binary": str(binary.relative_to(ROOT)), "binary_sha256": sha(binary),
            "link_map": str(linkmap.relative_to(ROOT)), "link_map_sha256": sha(linkmap),
            "log": str(log.relative_to(ROOT)), "log_sha256": sha(log),
            "test_source": str(source.relative_to(ROOT)), "test_source_sha256": sha(source),
            "runner": str(Path(__file__).relative_to(ROOT)), "runner_sha256": sha(Path(__file__).resolve()),
            "memory_provider": str(memory_source.relative_to(ROOT)), "memory_provider_sha256": sha(memory_source),
            "parent_binder": str(parent_binder.relative_to(ROOT)), "parent_binder_sha256": sha(parent_binder),
            "candidate_recarve_source": "src/stream/hcu_main.c",
            "candidate_recarve_sha256": sha(ROOT / "src/stream/hcu_main.c"),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(run.stdout, end="")
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {sha(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
