"""Compile and run CE's real, narrowly scoped sound-scenery callbacks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))


class HcuSoundSceneryLifecycleTest(unittest.TestCase):
    def test_real_ce_callback_only_sets_shadowless_object_flag(self):
        from host_abi32 import flags

        with tempfile.TemporaryDirectory(prefix="hcu-sound-scenery-") as temp_name:
            temp = Path(temp_name)
            semantics = temp / "halo_ps2_msvc_semantics.h"
            subprocess.run([
                "python3", str(HCU / "tools/linux_msvc_semantics.py"),
                "--output", str(semantics), "--all-inlines",
                "--tags", str(HCU / "source"),
                "--inlines", str(HCU / "source"),
                "--inlines", str(HCU / "port/include/xdk"),
            ], check=True, capture_output=True, text=True)
            include_dirs = [
                ROOT / "tests", HCU / "port/ps2/include", HCU / "port/include",
                HCU / "port/include/xdk", HCU / "port/linux/game", HCU / "source",
                *[HCU / "source" / name for name in (
                    "cseries", "objects", "math", "memory", "structures",
                    "tag_files", "sound")],
                Path("/usr/include"),
            ]
            executable = temp / "sound-scenery-test"
            command = [
                "gcc", *flags(), "-fshort-wchar", "-std=gnu99", "-fms-extensions",
                "-fcommon", "-fwrapv", "-ffunction-sections", "-fdata-sections",
                "-fno-strict-aliasing", "-include",
                str(ROOT / "tests/hcu_scenario_host32_prefix.h"),
                "-include", str(semantics), "-w",
                *["-I" + str(path) for path in include_dirs],
                str(ROOT / "tests/hcu_sound_scenery_host32.c"),
                str(HCU / "source/sound/sound_scenery.c"),
                "-Wl,--gc-sections", "-o", str(executable),
            ]
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(
                "ce-sound-scenery lifecycle=passed callback_effect=shadowless audio_request=none",
                run.stdout,
            )


if __name__ == "__main__":
    unittest.main()
