#!/usr/bin/env python3
"""C4 item 6: regression pin for the HCU/CE scenario_fog_at_point() behaviour.

The pinned behaviour is the recorded CE function body: an unconditional
`return 0.0f;` that ignores viewer_location, viewer_point and point, and the
recorded source identities of the function and of its two AI callers.  This
is NOT parity evidence for the Xbox attenuation formula, which is unresolved
(see docs/reports/m2-step7-mp-bot-fog-attenuation-blocker-2026-10-22.md) and is
explicitly excluded from this gate.

Any change to the pinned source files, the function body, the caller threshold
blocks, or the Halo-64 reference stub fails this test.  Pins are never edited
here; a failure is a finding to report.
"""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal"
H64 = ROOT / "submodules/halo-64"

# Recorded pins (docs/reports/m2-step7-mp-bot-fog-attenuation-blocker-2026-10-22.md,
# "Source identities"; scenario.c hash re-confirmed in
# docs/reports/m2-step7-fog-plane-consumer-qualification-2026-10-21.md).
PIN_SHA256 = {
    "ce_scenario": ("submodules/halo-ce-universal/source/scenario/scenario.c",
                    "22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0"),
    "ce_actor_perception": ("submodules/halo-ce-universal/source/ai/actor_perception.c",
                            "09987c7b42e98f137d317fad9d9e8660708b9f3e06d5ce8da41cfb2ed28c70e3"),
    "halo64_scenario": ("submodules/halo-64/source/scenario/scenario.c",
                        "0368b3bb31f8008f1ff2120f58c3d0c91e4c003a1009974d3f1cbd67810e1684"),
}

# ai.c changed after the pin (bc169da3, 2026-10-24, PS2 profiler offset asserts),
# so the file-level hash is not pinned; the fog call block is pinned instead.
AI_FOG_CALL_BLOCK = (
    "\t{\n"
    "\t\treal fog = scenario_fog_at_point(\n"
    "\t\t\t&collision.start_location,\n"
    "\t\t\tp0,\n"
    "\t\t\t&collision.point);\n"
    "\n"
    "\t\tif (fog > 0.8f)\n"
    "\t\t\tgoto classify_collision_distance;\n"
    "\n"
    "\t\tif (fog > 0.6f)\n"
    "\t\t\tgoto occluded;\n"
    "\t}\n"
)
AP_FOG_CALL_BLOCK = (
    "\t\t\t\t{\n"
    "\t\t\t\t\treal fog =\n"
    "\t\t\t\t\t\tscenario_fog_at_point(\n"
    "\t\t\t\t\t\t\t&position->body_location,\n"
    "\t\t\t\t\t\t\t&position->head_position,\n"
    "\t\t\t\t\t\t\ttarget_position);\n"
    "\n"
    "\t\t\t\t\tif (fog > 0.8f)\n"
    "\t\t\t\t\t{\n"
    "\t\t\t\t\t\tperception_factor = 0.15f;\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t\telse\n"
    "\t\t\t\t\t{\n"
    "\t\t\t\t\t\tif (fog > 0.2f)\n"
    "\t\t\t\t\t\t{\n"
    "\t\t\t\t\t\t\tperception_factor =\n"
    "\t\t\t\t\t\t\t\t(0.8f - fog) *\n"
    "\t\t\t\t\t\t\t\tperception_factor *\n"
    "\t\t\t\t\t\t\t\t1.6666666f;\n"
    "\t\t\t\t\t\t}\n"
)

FUNC_HEAD = (
    "real scenario_fog_at_point(\n"
    "\tconst struct location *viewer_location,\n"
    "\tconst real_point3d *viewer_point,\n"
    "\tconst real_point3d *point)\n"
    "{\n"
    "\treturn 0.0f;\n"
    "}\n"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class C4FogPinTest(unittest.TestCase):
    def test_pinned_source_identities(self):
        for key, (rel, expected) in PIN_SHA256.items():
            with self.subTest(source=key):
                actual = sha256(ROOT / rel)
                self.assertEqual(
                    actual, expected,
                    f"{rel} changed: pinned fog source identity {expected}, got {actual}")

    def test_ce_function_body_is_pinned_zero_return(self):
        text = (CE / "source/scenario/scenario.c").read_text()
        self.assertEqual(text.count("scenario_fog_at_point("), 1,
                         "expected exactly one definition of scenario_fog_at_point in scenario.c")
        self.assertIn(FUNC_HEAD, text,
                      "scenario_fog_at_point() definition changed from the pinned "
                      "constant-zero body")

    def test_ce_header_prototype_pinned(self):
        text = (CE / "source/scenario/scenario.h").read_text()
        self.assertIn(
            "real scenario_fog_at_point(const struct location *viewer_location, "
            "const real_point3d *viewer_point, const real_point3d *point);",
            text)

    def test_halo64_reference_stub_pinned(self):
        text = (H64 / "source/scenario/scenario.c").read_text()
        self.assertRegex(
            text,
            r"real scenario_fog_at_point\(\s*const struct location \*viewer_location,"
            r"\s*const real_point3d \*viewer_point,\s*const real_point3d \*point\)\s*"
            r"\{\s*return 0\.0f;\s*\}")

    def test_ai_callers_threshold_blocks_pinned(self):
        ai = (CE / "source/ai/ai.c").read_text()
        ap = (CE / "source/ai/actor_perception.c").read_text()
        self.assertIn(AI_FOG_CALL_BLOCK, ai,
                      "ai.c line-of-sight fog call block changed (0.8 / 0.6 thresholds)")
        self.assertIn(AP_FOG_CALL_BLOCK, ap,
                      "actor_perception.c fog call block changed (0.8 / 0.2 thresholds)")

    def test_exclusion_marker_recorded(self):
        blocker = ROOT / "docs/reports/m2-step7-mp-bot-fog-attenuation-blocker-2026-10-22.md"
        self.assertIn("remains blocked", blocker.read_text())
        self.assertIn("Do not", ROOT.joinpath(
            "docs/reports/m2-step7-mp-field-inventory-remainder-2026-10-21.md").read_text())
        plan = (ROOT / "plans/7.hcu-remake-m2-m4.md").read_text()
        self.assertIn("Preserve the pinned HCU `scenario_fog_at_point()` behavior. "
                      "Record exact retail Xbox attenuation as unresolved", plan)
        closure = (ROOT / "tools/generate_hcu_step7_step8_closure.py").read_text()
        self.assertIn("scenario_fog_at_point attenuation is intentionally unresolved "
                      "and not a closure gate.", closure)

    def test_no_fog_arguments_are_consulted(self):
        # The pinned body must not read its inputs; any real computation is a change.
        text = (CE / "source/scenario/scenario.c").read_text()
        m = re.search(r"real scenario_fog_at_point\((.*?)\n\}\n", text, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn("viewer_location->", body)
        self.assertNotIn("viewer_point->", body)
        self.assertNotIn("point->", body)


if __name__ == "__main__":
    unittest.main()
