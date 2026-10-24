"""M3 collision-oracle baseline plus an honest CE-parity readiness gate.

The parent movement implementation remains a reference while M2 still lacks a
resident retail BSP in the combined CE runtime.  This test freezes a stable
parent trace from the retail Blood Gulch map, and asserts that the requested CE
comparison cases stay explicitly blocked rather than being counted as parity.
"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"
REPORT = ROOT / "docs/investigations/m3-collision-parity-scaffold.json"
FRAME_SCRATCH_BYTES = 393216


def _parent_trace():
    sys.path.insert(0, str(ROOT / "tools"))
    from convert_collision import build_pack

    with tempfile.TemporaryDirectory() as temp:
        pack_path = Path(temp) / "bloodgulch-collision.hp2"
        pack = build_pack(MAP)
        pack_path.write_bytes(pack)
        executable = Path(temp) / "m3-parent-player-oracle"
        subprocess.run(
            [
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(ROOT / "src"),
                str(ROOT / "tests/player_main.c"),
                str(ROOT / "src/game/move.c"),
                str(ROOT / "src/game/pill.c"),
                str(ROOT / "src/game/collide.c"),
                str(ROOT / "src/game/collpack.c"),
                "-lm", "-o", str(executable),
            ],
            check=True,
            capture_output=True,
        )
        output = subprocess.run(
            [str(executable), str(pack_path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    # Wall-clock benchmark is intentionally not part of simulation parity.
    canonical = "\n".join(
        line for line in output.splitlines() if not line.startswith("bench ")
    ) + "\n"
    return pack, output, canonical


class M3CollisionOracleScaffold(unittest.TestCase):
    def test_parent_bloodgulch_trace_is_repeatable_and_budgeted(self):
        if not MAP.is_file():
            self.skipTest("decompressed retail Blood Gulch map is unavailable")
        report = json.loads(REPORT.read_text())
        self.assertEqual(sha256(MAP.read_bytes()).hexdigest(), report["fixture"]["map_sha256"])

        pack_a, output_a, canonical_a = _parent_trace()
        pack_b, output_b, canonical_b = _parent_trace()
        self.assertEqual(sha256(pack_a).hexdigest(), report["fixture"]["parent_hp2_sha256"])
        self.assertEqual(sha256(pack_b).hexdigest(), report["fixture"]["parent_hp2_sha256"])
        self.assertEqual(canonical_a, canonical_b, "parent simulation trace must be deterministic")
        self.assertEqual(
            sha256(canonical_a.encode()).hexdigest(),
            report["fixture"]["parent_trace_sha256_excluding_bench_line"],
        )

        rows = {line.split()[0]: line for line in output_a.splitlines() if line.strip()}
        self.assertEqual(int(rows["scratch"].split()[1]), 47644)
        self.assertLess(int(rows["scratch"].split()[1]), FRAME_SCRATCH_BYTES)
        for required in (
            "settle", "jump", "land", "walk", "crouch", "recover",
            "schedule", "fast_blocked", "slope_found", "ceiling_found", "corner_found",
        ):
            self.assertIn(required, rows)
        self.assertEqual(rows["settle"].split()[2], "1", "parent reference must settle grounded")
        self.assertEqual(rows["schedule"].split()[1], "1", "parent reference is render-schedule invariant")

    def test_hcu_rows_are_not_misreported_as_parity_without_runtime_bsp(self):
        report = json.loads(REPORT.read_text())
        required_rows = {
            "player_pill_sweep", "static_bsp_hit", "dynamic_object_hit",
            "actor_hit", "projectile_hit",
        }
        rows = {row["case"]: row for row in report["comparisons"]}
        self.assertEqual(set(rows), required_rows)
        for row in rows.values():
            self.assertEqual(row["status"], "blocked-awaiting-m2-resident-gameplay-bsp")
            self.assertFalse(row["hcu_trace_available"])
            self.assertTrue(row["blockers"])

        # Assert the CE authority remains present and is wired through the
        # collision layer, while deliberately not fabricating an invocation.
        ce_bsp = ROOT / "submodules/halo-ce-universal/source/physics/collision_bsp.c"
        ce_collision = ROOT / "submodules/halo-ce-universal/source/physics/collisions.c"
        self.assertIn("boolean collision_bsp_test_pill_new(", ce_bsp.read_text())
        self.assertIn("collision_bsp_test_pill_new(", ce_collision.read_text())
        self.assertIn("collision_move_pill(", ce_collision.read_text())
        self.assertIn("m2-ui-map-loaded", report["hcu_authority"]["blocking_boundary"])


if __name__ == "__main__":
    unittest.main()
