#!/usr/bin/env python3
"""Exercise CE's guarded invalid fog references on a retail MP BSP.

This makes a temporary, test-only source copy of the existing all-MP host
fixture. It does not modify the CE or parent production sources.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    source = (ROOT / "tests/test_hcu_mp_capacity.py").read_text()
    root_seam = "ROOT = Path(__file__).resolve().parents[1]"
    if source.count(root_seam) != 1:
        raise SystemExit("capacity fixture ROOT seam changed")
    source = source.replace(root_seam, f"ROOT = Path({str(ROOT)!r})")

    common_seam = 'common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()'
    injected = r'''common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
            invalid_ref_probe = r"""
	{
		short source_reference = cluster->fog_reference;
		short invalid_plane_reference;
		short invalid_region_reference;
		assert(structure->fog_planes.count > 0 &&
			structure->fog_planes.count < SHORT_MAX);
		assert(structure->fog_regions.count > 0 &&
			structure->fog_regions.count < SHORT_MAX);
		invalid_plane_reference = (short)(0x8000u |
			(unsigned)structure->fog_planes.count);
		invalid_region_reference = (short)structure->fog_regions.count;
		cluster->fog_reference = invalid_plane_reference;
		assert(scenario_get_fog_region_index(&location, NULL) == NONE);
		cluster->fog_reference = invalid_region_reference;
		assert(scenario_get_fog_region_index(&location, NULL) == NONE);
		cluster->fog_reference = source_reference;
		assert(scenario_get_fog_region_index(&location, NULL) ==
			golden->region_index);
		assert(global_structure_bsp == structure &&
			global_structure_bsp_index == published_index);
		assert(global_current_collision_user_depth == collision_depth);
		assert(cluster->fog_reference == source_reference);
		printf("mp-fog-invalid-reference map=%d invalid_plane=%d "
			"invalid_region=%d restored=%d status=passed\n", map_id,
			invalid_plane_reference, invalid_region_reference,
			cluster->fog_reference);
	}
"""
            fog_seam = '\tassert(global_structure_bsp == structure &&\n\t\tglobal_structure_bsp_index == published_index);\n\tassert(global_current_collision_user_depth == collision_depth);\n\tprintf("fog-plane map='
            if common.count(fog_seam) != 1:
                raise SystemExit("fog-plane assertion seam changed")
            common = common.replace(fog_seam, invalid_ref_probe + "\n" + fog_seam)
'''
    # Replace only the first part of the existing setup; its next line is the
    # scratch-buffer assertion, which the inserted test leaves intact.
    if source.count(common_seam + "\n            old =") != 1:
        raise SystemExit("fixture-generated CE common source seam changed")
    source = source.replace(common_seam + "\n            old =",
                          injected + "\n            old =", 1)
    write_seam = '            (temp / "hcu_scenario_bsp_switch_main.c").write_text(common)'
    if source.count(write_seam) != 1:
        raise SystemExit("generated CE source retention seam changed")
    source = source.replace(
        write_seam,
        write_seam + '\n            shutil.copy2(temp / "hcu_scenario_bsp_switch_main.c", '
        'Path(__file__).resolve().with_name("generated_hcu_scenario_bsp_switch_main.c"))',
        1)

    out = ROOT / "build" / f"m2-mp-invalid-fog-{time.time_ns()}"
    out.mkdir(parents=True)
    generated = out / "test_hcu_mp_capacity_fog_invalid.py"
    generated.write_text(source)
    module = generated.stem
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((
        str(out), str(ROOT), str(ROOT / "tests"), str(ROOT / "tools"),
        str(ROOT / "submodules/halo-ps2/tools"),
    ))
    cmd = [sys.executable, "-m", "unittest", "-v",
           f"{module}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision"]
    result = subprocess.run(cmd, cwd=out, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = out / "runner.log"
    log.write_text(result.stdout)
    print(result.stdout, end="")
    print(f"generated_test={generated.relative_to(ROOT)} sha256={sha(generated)}")
    print(f"runner_log={log.relative_to(ROOT)} sha256={sha(log)}")
    print(f"exit={result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
