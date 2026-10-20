"""Host coverage for the bounded placed-actor combat target registry."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"


class CombatTargets(unittest.TestCase):
    def test_two_actor_order_occlusion_and_target_specific_vitality(self):
        sources = [
            ROOT / "tests/combat_targets_main.c",
            ROOT / "src/game/combat_targets.c",
            ROOT / "src/game/collpack.c",
            ROOT / "src/game/vital.c",
            ENGINE / "sim/objects.c",
            ENGINE / "sim/skeleton.c",
            ENGINE / "world/model.c",
            ENGINE / "world/anim.c",
            ENGINE / "world/scen.c",
            ENGINE / "core/mat.c",
        ]
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "combat_targets"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"), "-I" + str(ENGINE),
                 *map(str, sources), "-lm", "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            result = subprocess.run([str(executable)], check=True,
                                    capture_output=True, text=True)
        self.assertIn("object_table pose/update, vitality persistence, occlusion and hit attribution ok",
                      result.stdout)


if __name__ == "__main__":
    unittest.main()
