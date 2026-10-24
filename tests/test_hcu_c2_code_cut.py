#!/usr/bin/env python3
"""C2.3 code-cut guards: PS2 production keeps the AI profiler history short.

These are source checks. The link-level effect (elf_static bytes) is measured by
tools/audit_hcu_c2_budget_elf_owners.py against the probe ELF, not here.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal/source/ai"


def read(name):
    return (CE / name).read_text(encoding="utf-8", errors="replace")


class AiProfileHistoryStubTests(unittest.TestCase):
    def test_header_defines_stub_under_ps2_guard(self):
        text = read("ai_profile.h")
        self.assertRegex(
            text,
            r"#if defined\(HALO_PS2\) && !defined\(HCU_AI_DEBUG_DIAGNOSTICS\)\s*\n#define AI_PROFILE_HISTORY_STUB",
        )

    def test_history_ticks_are_eight_on_stub_and_sixty_otherwise(self):
        text = read("ai_profile.h")
        self.assertRegex(text, r"#ifdef AI_PROFILE_HISTORY_STUB\s*\n\s*AI_METER_HISTORY_TICKS = 8,")
        self.assertRegex(text, r"#else\s*\n\s*AI_METER_HISTORY_TICKS = 60,")

    def test_ai_profile_size_asserts_are_skipped_on_stub(self):
        for name in ("ai_profile.c", "ai.c"):
            text = read(name)
            guarded = re.findall(r"#ifndef AI_PROFILE_HISTORY_STUB(.*?)#endif", text, re.S)
            self.assertTrue(guarded, f"{name}: no AI_PROFILE_HISTORY_STUB guard")
        ai_c = read("ai.c")
        for offset in ("0xB34", "0xBBC", "0xC44"):
            self.assertIn(offset, ai_c)
        block = re.search(r"#ifndef AI_PROFILE_HISTORY_STUB(.*?)#endif", ai_c, re.S).group(1)
        for offset in ("0xB34", "0xBBC", "0xC44"):
            self.assertIn(offset, block)

    def test_profile_size_asserts_are_skipped_on_stub(self):
        block = re.search(r"#ifndef AI_PROFILE_HISTORY_STUB(.*?)#endif", read("ai_profile.c"), re.S).group(1)
        self.assertIn("0xEEC", block)
        self.assertIn("0x88", block)

    def test_history_is_not_read_by_ai_logic(self):
        # The stub is only safe while no code outside ai_profile.c reads the averages.
        for path in (CE.parent).rglob("*.c"):
            if path.name == "ai_profile.c":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotRegex(text, r"meters\[[^\]]*\]\.average", str(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
