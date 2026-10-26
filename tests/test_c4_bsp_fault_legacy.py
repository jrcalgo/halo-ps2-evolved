"""C4 owner-exhaustion injection through the legacy HP2 preflight in hcu_map_service.c.

The production translation unit is compiled unmodified. Two owner-allocation sites are
reachable only when HCU_C4_FAULT_SEAM is defined (default off, constant 0):
  site 1: CTAG relocation vector allocation in feed_ctag_first_pass()
  site 2: source-hash scratch allocation in verify_source_hash()

The legacy path is production-reachable: tools/ee-world.mk:56 leaves
WORLD_HCU_PARTITION_PROFILE empty, so no profile runtime is registered, and
hcu_map_service_preflight() then takes the legacy branch (hcu_map_service.c:1459-1461).

Fixture-only overrides, both recorded as such:
  * HCU_M2_MP_HOST_ORACLE admits bloodgulch through the capacity gate (hcu_map_service.c:1373).
  * The host tag cache is 16 MiB. At the production 2 MiB (tools/ee-world.mk:62) bloodgulch
    is rejected by the CTAG capacity check (status 8), which the clean run here shows
    is a real production-capacity finding, not a seam result.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

HCU = ROOT / "submodules/halo-ce-universal"
ENG = ROOT / "submodules/halo-ps2/engine"
MAP = "bloodgulch"
PACKAGE = ROOT / "build/retail-maps/bloodgulch-with-bsps.hp2"
SOURCE = ROOT / f"build/retail-maps/decompressed/{MAP}.map"

SOURCES = [
    "tests/c4_bsp_fault_legacy_main.c", "tests/hcu_objects_host32.c",
    "tests/hcu_game_sound_host32.c", "tests/hcu_player_pvs_host32.c",
    "tests/hcu_real_math_host32.c", "tests/hcu_bsp3d_host32.c",
    "submodules/halo-ce-universal/source/scenario/scenario.c",
    "submodules/halo-ce-universal/source/sound/sound_environment_definitions.c",
    "submodules/halo-ce-universal/source/tag_files/tag_files.c",
    "submodules/halo-ce-universal/source/memory/data.c",
    "submodules/halo-ce-universal/source/math/integer_math.c",
    "submodules/halo-ce-universal/source/physics/collisions.c",
    "submodules/halo-ce-universal/source/physics/collision_bsp.c",
    "submodules/halo-ce-universal/source/physics/bsp2d.c",
    "submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c",
    "submodules/halo-ce-universal/port/ps2/src/ps2_cache.c",
    "submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c",
    "submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_groups.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_models.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_objects.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_render.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_effects.c",
    "submodules/halo-ce-universal/port/linux/game/tag_schema_scenario.c",
    "src/stream/hcu_map_service.c", "src/stream/hcu_map_catalog.c",
    "src/stream/ctag_mount.c", "src/stream/ctag_ps2_backend.c",
    "src/stream/cbsp_catalog.c", "src/stream/ctag_resource_index.c",
    "src/stream/ctag_map_source.c", "src/stream/sha256.c", "src/stream/hmap.c",
    "src/stream/hcu_asset_profile.c", "src/stream/hcu_profile_mount.c",
    "src/stream/hcu_profile_metadata.c",
    "submodules/halo-ps2/engine/src/world/section.c",
    "submodules/halo-ps2/engine/src/stream/hp2.c",
    "submodules/halo-ps2/engine/src/stream/file.c",
    "submodules/halo-ps2/engine/src/core/mem.c",
]
INCLUDES = [
    ".", "tests", "tests/hcu_scenario_host_shim",
    "submodules/halo-ce-universal/port/ps2/include",
    "submodules/halo-ce-universal/port/linux/game",
    "submodules/halo-ce-universal/port/include",
    "submodules/halo-ce-universal/source",
    *[f"submodules/halo-ce-universal/source/{d}" for d in (
        "cseries", "scenario", "structures", "cache", "tag_files", "objects", "physics",
        "game", "interface", "math", "sound", "memory", "input")],
    "src", "submodules/halo-ps2/engine/src", "submodules/halo-ps2/engine/tests/hp2_world_shim",
]


def _host_flags():
    import host_abi32
    return host_abi32.flags()


def _build(exe: Path, seam: bool, semantics: Path):
    compiler = shutil.which("gcc")
    if not compiler:
        raise unittest.SkipTest("gcc unavailable for the ILP32 map-service fixture")
    if not Path(os.environ.get("HALO_HOST_ABI32_ROOT", ROOT / "build/host-abi32/root")).exists():
        raise unittest.SkipTest("host ILP32 sysroot missing; run tools/host_abi32.py prepare")
    includes = [str(ROOT / p) for p in INCLUDES] + ["/usr/include"]
    cmd = [compiler, *_host_flags(), "-fshort-wchar", "-std=gnu99", "-fms-extensions",
           "-fcommon", "-fwrapv", "-ffunction-sections", "-fdata-sections",
           "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
           "-DHCU_BSP_RETAIL_INTEGRATION=1", "-DHALO_PS2=1",
           "-DHALO_PS2_M2_ANIMATION_TRACE=1", "-DHCU_M2_MP_HOST_ORACLE=1"]
    if seam:
        cmd.append("-DHCU_C4_FAULT_SEAM=1")
    cmd += ["-include", str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
            "-include", str(semantics), "-w"]
    cmd += ["-I" + p for p in includes]
    cmd += ["-Wl,--gc-sections", "-Wl,--wrap=read"]
    cmd += [str(ROOT / s) for s in SOURCES]
    cmd += ["-lm", "-o", str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if built.returncode:
        raise AssertionError(built.stdout + built.stderr)


def _semantics(tmp: Path) -> Path:
    out = tmp / "halo_ps2_msvc_semantics.h"
    subprocess.run([sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
                    "--output", str(out), "--all-inlines", "--tags", str(HCU / "source"),
                    "--inlines", str(HCU / "source"), "--inlines", str(HCU / "port/include/xdk")],
                   check=True, capture_output=True, text=True)
    return out


def _run(exe: Path, asset_root: Path, site: int):
    return subprocess.run([str(exe), str(asset_root) + "/", MAP, str(site)],
                          capture_output=True, text=True, timeout=600)


def _state(line: str):
    fields = dict(part.split("=", 1) for part in line.split()[1:] if "=" in part)
    return fields


class LegacyOwnerExhaustionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PACKAGE.is_file() or not SOURCE.is_file():
            raise unittest.SkipTest("retail bloodgulch package/source not present")
        cls.tmp = Path(tempfile.mkdtemp(prefix="c4-legacy-"))
        maps = cls.tmp / "assets/maps"
        maps.mkdir(parents=True)
        (maps / f"{MAP}.hp2").symlink_to(PACKAGE)
        (maps / f"{MAP}.map").symlink_to(SOURCE)
        semantics = _semantics(cls.tmp)
        cls.seam_exe = cls.tmp / "legacy-seam"
        cls.plain_exe = cls.tmp / "legacy-plain"
        _build(cls.seam_exe, True, semantics)
        _build(cls.plain_exe, False, semantics)
        cls.asset_root = cls.tmp / "assets"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _lines(self, run):
        self.assertIn(run.returncode, (0,), run.stdout + run.stderr)
        return run.stdout.splitlines()

    def _find(self, lines, prefix):
        matches = [l for l in lines if l.startswith(prefix)]
        self.assertEqual(len(matches), 1, lines)
        return matches[0]

    def test_clean_preflight_accepts_and_stages(self):
        lines = self._lines(_run(self.seam_exe, self.asset_root, 0))
        clean = _state(self._find(lines, "CLEAN "))
        self.assertEqual(clean["rc"], "1")
        self.assertEqual(clean["preflight_ready"], "1")
        self.assertEqual(clean["staged_map"], MAP)
        self.assertEqual(clean["canaries"], "ok")

    def test_seam_off_build_matches_seam_build_clean_run(self):
        seam = _state(self._find(self._lines(_run(self.seam_exe, self.asset_root, 0)), "CLEAN "))
        plain = _state(self._find(self._lines(_run(self.plain_exe, self.asset_root, 0)), "CLEAN "))
        self.assertEqual(seam, plain)

    def test_owner_exhaustion_rolls_back_then_retry_matches_clean(self):
        clean = _state(self._find(self._lines(_run(self.seam_exe, self.asset_root, 0)), "CLEAN "))
        cases = {1: "ctag-relocation-allocation-failed",
                 2: "sha256-scratch-failed"}
        for site, message in cases.items():
            with self.subTest(site=site):
                lines = self._lines(_run(self.seam_exe, self.asset_root, site))
                self.assertIn(f"FAULT site={site} fired={site}", lines)
                self.assertTrue(any(message in l for l in lines),
                                f"owner-allocation failure not reported: {message}")
                faulted = _state(self._find(lines, "FAULTED "))
                # Rollback: rejected, nothing staged, both arenas back to their marks,
                # no source or mount left open, and the guard past the region intact.
                self.assertEqual(faulted["rc"], "0")
                self.assertEqual(faulted["preflight_ready"], "0")
                self.assertEqual(faulted["staged_map"], "-")
                self.assertEqual(faulted["staged_entry"], "0")
                self.assertEqual(faulted["map_used"], "0")
                self.assertEqual(faulted["scratch_used"], "0")
                self.assertEqual(faulted["source_active"], "0")
                self.assertEqual(faulted["mount_active"], "0")
                self.assertEqual(faulted["descriptor"], "-1")
                self.assertEqual(faulted["canaries"], "ok")
                # Clean retry in the same process reproduces the clean load state.
                retry = _state(self._find(lines, "RETRY "))
                self.assertEqual(retry["rc"], "1")
                for key in ("preflight_ready", "staged_map", "staged_entry", "map_used",
                            "scratch_used", "source_active", "mount_active",
                            "descriptor", "canaries"):
                    self.assertEqual(retry[key], clean[key], key)


if __name__ == "__main__":
    unittest.main()
