"""Blood Gulch player: pill sweep, jump, crouch, and the scratch budget."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_collide import MAP, collision_fixture

FRAME_SCRATCH = 393216
# current_bsp minus the Blood Gulch render BSP raw size
BSP_SPARE = 6291456 - 611856


def fields(line):
    parts = line.split()
    out = {}
    i = 0
    while i < len(parts):
        key = parts[i]
        if i + 1 < len(parts):
            try:
                out[key] = float(parts[i + 1])
                i += 2
                continue
            except ValueError:
                pass
        i += 1
    return out


class Player(unittest.TestCase):
    def test_walk_jump_crouch_on_blood_gulch(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        with tempfile.TemporaryDirectory() as temp:
            sys.path.insert(0, str(ROOT / "tools"))
            from convert_collision import build_pack
            fixture = Path(temp) / "collision.hp2"
            fixture.write_bytes(build_pack(MAP))
            exe = Path(temp) / "player"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/player_main.c"),
                 str(ROOT / "src/game/move.c"),
                 str(ROOT / "src/game/pill.c"),
                 str(ROOT / "src/game/collide.c"),
                 str(ROOT / "src/game/collpack.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(fixture)], check=True, capture_output=True, text=True)
        lines = {line.split()[0]: line for line in out.stdout.splitlines()}
        scratch = fields(lines["scratch"])["scratch"]
        tables = fields(lines["tables"])["tables"]
        self.assertLess(scratch, FRAME_SCRATCH)
        self.assertLess(tables, BSP_SPARE)
        settle = fields(lines["settle"])
        self.assertEqual(settle["grounded"], 1)
        self.assertEqual(settle["oow"], 0)
        self.assertLess(abs(settle["z"] - settle["spawn"]), 0.01)
        self.assertAlmostEqual(settle["eye"], 0.62, places=3)
        jump = fields(lines["jump"])
        self.assertEqual(jump["grounded"], 0)
        self.assertAlmostEqual(jump["vz"], 0.07 - 0.0035651792, places=5)
        land = fields(lines["land"])
        self.assertEqual(land["grounded"], 1)
        self.assertGreater(land["peak"] - settle["z"], 0.60)
        self.assertLess(land["peak"] - settle["z"], 0.72)
        self.assertLess(abs(land["z"] - settle["z"]), 0.01)
        walk = fields(lines["walk"])
        self.assertEqual(walk["grounded"], 1)
        self.assertLess(abs(walk["z"] - settle["z"]), 0.05)
        distance = (walk["dx"] ** 2 + walk["dy"] ** 2) ** 0.5
        self.assertGreater(distance, 1.0)
        self.assertLess(distance, 2.3)
        crouch = fields(lines["crouch"])
        self.assertAlmostEqual(crouch["crouch"], 1.0, places=3)
        self.assertAlmostEqual(crouch["eye"], 0.35, places=3)
        self.assertAlmostEqual(crouch["height"], 0.5, places=3)
        recover = fields(lines["recover"])
        self.assertEqual(recover["oow"], 1)
        self.assertLess(abs(recover["z"] - settle["z"]), 0.01)
        self.assertEqual(fields(lines["schedule"])["schedule"], 1)
        self.assertGreaterEqual(fields(lines["fast_blocked"])["fast_blocked"], 2)
        bench = fields(lines["bench"])
        self.assertLess(bench["usec"], 500)
        self.assertEqual(bench["depth_limited"], 0)
        self.assertLessEqual(bench["max_features"], 256)
        slope = fields(lines["slope"])
        self.assertGreater(slope["rise"], 0.02)
        self.assertGreaterEqual(slope["grounded_ticks"], 20)
        self.assertEqual(fields(lines["slope_found"])["slope_found"], 1)
        ceiling = fields(lines["ceiling"])
        self.assertLess(ceiling["head"], ceiling["limit"] + 0.05)
        self.assertEqual(fields(lines["ceiling_found"])["ceiling_found"], 1)
        self.assertGreater(fields(lines["corner"])["remain"], 0.15)
        self.assertEqual(fields(lines["corner_found"])["corner_found"], 1)
        sys.path.insert(0, str(ROOT / "tools"))
        from convert_collision import collision_payload
        _payload, tags = collision_payload(MAP)
        expected = {
            "run_forward": 2.25, "run_backward": 2.0, "run_sideways": 2.0,
            "run_acceleration": 0.32, "jump_velocity": 0.07,
            "stand_camera": 0.62, "crouch_camera": 0.35,
            "stand_height": 0.7, "crouch_height": 0.5, "radius": 0.2,
            "minimum_normal_k": 0.70710677, "gravity": 0.0035651792,
        }
        for name, value in expected.items():
            self.assertAlmostEqual(tags[name], value, delta=1.0e-4)
        for name in ("move.c", "pill.c", "collide.c"):
            text = (ROOT / "src/game" / name).read_text()
            self.assertNotIn("malloc", text)
            self.assertNotIn("calloc", text)


if __name__ == "__main__":
    unittest.main()
