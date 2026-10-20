"""Exercise the HCU PS2 XInput semantics with host-compiled code."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


class HcuPs2Input(unittest.TestCase):
    def test_ps2_pad_logical_order_for_both_multitap_arrangements(self):
        for port0_tap in (1, 0):
            with self.subTest(port0_tap=port0_tap), tempfile.TemporaryDirectory() as temp:
                exe = Path(temp) / "hcu-pad-poll"
                subprocess.run(
                    ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                     f"-DPAD_TEST_PORT0_TAP={port0_tap}",
                     "-I" + str(ROOT / "tests/hcu_pad_shim"),
                     "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                     str(ROOT / "tests/hcu_pad_poll_main.c"),
                     str(ROOT / "submodules/halo-ps2/engine/src/platform/pad.c"),
                     "-o", str(exe)],
                    check=True, capture_output=True)
                result = subprocess.run([str(exe)], check=True, text=True,
                                        capture_output=True)
                self.assertTrue(result.stdout.strip().endswith(
                    "PS2 pad logical port/slot fixture passed"))

    def test_dualshock_conversion_connection_and_packet_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-ps2-input"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                 "-I" + str(HCU / "port/include"),
                 "-I" + str(HCU / "port/ps2/include"),
                 str(ROOT / "tests/hcu_ps2_input_main.c"),
                 str(HCU / "port/ps2/src/ps2_input.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)

    def test_parent_pad_bridge_publishes_samples_before_ce_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "hcu-input-bridge"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-D__stdcall=", "-D__fastcall=", "-D__int64=long long",
                 "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
                 "-I" + str(HCU / "port/include"),
                 "-I" + str(HCU / "port/ps2/include"),
                 str(ROOT / "tests/hcu_input_bridge_main.c"),
                 str(ROOT / "src/stream/hcu_input_bridge.c"),
                 str(HCU / "port/ps2/src/ps2_input.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)

    def test_ce_frame_begin_polls_parent_before_snapshotting_devices(self):
        source = (HCU / "source/input/input_xbox.c").read_text()
        match = re.search(
            r"void\s+input_frame_begin\s*\(\s*void\s*\)\s*\{(.*?)\n\}",
            source, re.S)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("#ifdef HALO_PS2", body)
        self.assertLess(body.index("ps2_input_poll_devices()"),
                        body.index("input_get_device_states()"))
        self.assertLess(body.index("input_get_device_states()"),
                        body.index("input_globals.frame_active = TRUE"))


if __name__ == "__main__":
    unittest.main()
