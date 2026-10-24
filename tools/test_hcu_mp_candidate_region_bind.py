#!/usr/bin/env python3
"""Exercise v2 region adjacency and CE provider binding for MP's 10 MiB candidate."""
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
    out = ROOT / "build" / f"mp-candidate-region-bind-{time.time_ns()}"
    out.mkdir(parents=True)
    binary = out / "candidate-region-bind"
    linkmap = out / "candidate-region-bind.map"
    source = ROOT / "tests/hcu_mp_candidate_region_bind_main.c"
    command = [compiler, *host_abi32_flags(), "-isystem", "/usr/include", "-std=gnu99", "-O2", "-g", "-Wall", "-Wextra",
               "-DHALO_PS2_NO_BOOTSTRAP_MEMORY", "-I" + str(ROOT / "tests/hcu_ps2_memory_shim"),
               "-I" + str(ENGINE), "-I" + str(HCU / "port/ps2/include"),
               "-I" + str(ROOT / "src"), str(HCU / "port/ps2/src/ps2_memory.c"),
               str(ENGINE / "core/mem.c"), str(source),
               "-Wl,-Map," + str(linkmap), "-o", str(binary)]
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if built.returncode:
        (out / "compile.log").write_text(built.stdout + built.stderr)
        raise SystemExit(f"compile failed; see {out / 'compile.log'}")
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    log = out / "run.log"
    log.write_text(run.stdout + run.stderr)
    if run.returncode:
        raise SystemExit(f"candidate region/binder fixture failed; see {log}\n{run.stdout}{run.stderr}")
    required = ("candidate-v2-regions ",
                "combined_bytes=10485760 tag=4477120 "
                "bsp=1993712 texture=4014928 guards=9 marks=zero aligned=16 status=passed",
                "candidate-combined-cursor map=6470832 texture=4014928 "
                "used=10485760 cap=10485760 overflow=bounded rollback=zero "
                "high=10485760 guard=1 status=passed",
                "candidate-provider-bind tag=4477120 bsp=1993712 "
                "map=6470832 texture=4014928 total=10485760 claims=808856 "
                "align=16 disjoint=1 ready=1 canaries=1 status=passed")
    for marker in required:
        if marker not in run.stdout:
            raise SystemExit(f"missing diagnostic marker {marker!r}; see {log}")
    manifest = {
        "schema": "hcu-mp-candidate-region-provider-bind-v1",
        "status": "passed-diagnostic-only",
        "candidate_profile": {
            "tag_bytes": 4_477_120,
            "bsp_bytes_aligned_pad8": 1_993_712,
            "combined_map_bytes": 6_470_832,
            "texture_bytes": 4_014_928,
            "map_plus_texture_bytes": 10_485_760,
            "claims_bytes": 808_856,
        },
        "scope": "native host ILP32 test-only guarded layout variant and CE physical-memory provider bind; multiplayer candidate spans",
        "native_ilp32_host": True,
        "production_budget_or_admission_changed": False,
        "target_ee_execution": False,
        "artifacts": {
            "binary": str(binary.relative_to(ROOT)), "binary_sha256": sha(binary),
            "link_map": str(linkmap.relative_to(ROOT)), "link_map_sha256": sha(linkmap),
            "log": str(log.relative_to(ROOT)), "log_sha256": sha(log),
            "test_source": str(source.relative_to(ROOT)), "test_source_sha256": sha(source),
            "runner": str(Path(__file__).relative_to(ROOT)), "runner_sha256": sha(Path(__file__).resolve()),
            "mem_layout_source": str((ENGINE / "core/mem.c").relative_to(ROOT)),
            "mem_layout_source_sha256": sha(ENGINE / "core/mem.c"),
            "provider_source": str((HCU / "port/ps2/src/ps2_memory.c").relative_to(ROOT)),
            "provider_source_sha256": sha(HCU / "port/ps2/src/ps2_memory.c"),
            "provider_interface": "src/stream/hcu_memory_bind.c was not linked: this test binds the candidate spans directly to the same CE provider API, without changing the production v2 binder.",
        },
        "output": run.stdout,
        "interpretation": [
            "The aligned pad variant keeps the candidate 10 MiB sum unchanged while satisfying the provider's 16-byte base alignment: BSP is 8 bytes larger and texture span 8 bytes smaller than the prior candidate.",
            "The test-only guarded layout carves the candidate map+BSP and texture slices from one combined 10 MiB owner, with one 16-byte guard at its combined boundary; it separately carves the other v2 regions and the existing layout's fixed sizes.",
            "A single diagnostic owner cursor now allocates the exact map and texture views sequentially, reaches exactly 10 MiB, rejects one extra 16-byte request without moving the cursor, and rolls back to its entry mark while preserving the measured high-water and guard.",
            "The candidate layout's tag/BSP/texture views are bound to HCU's real PS2 provider API; game state and validator claims are allocated in its resident region, and audio/dynamic spans come from their candidate arenas. Marks are checked/reset and canaries are verified.",
            "The real guarded v2 layout has a 16-byte canary between current_bsp and texture_cache. A merged candidate map span starting at current_bsp.base crosses that canary and borrows 179,360 bytes of texture_cache; its adjacent candidate texture span ends 16 bytes before the stock texture region end.",
            "Therefore the candidate cannot simply be rebound across the existing guarded region boundary while retaining its current per-region guard invariant. A production use would require an explicit recarve/unified map-texture ownership design, not this diagnostic or a budget/admission edit.",
        ],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(run.stdout, end="")
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {sha(manifest_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
