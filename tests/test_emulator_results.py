"""A completed process is insufficient evidence for the M06 runtime gate."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_emulator import validate_platform


TRACE = """HALO_PS2_PLATFORM pad_ready=1
HALO_PS2_FRAME frame=1 elapsed_ms=7 heap=1261568 chain_high=20 guards=ok
HALO_PS2_PAD frame=126 edges=8
HALO_PS2_PAD frame=246 edges=16384
HALO_PS2_FRAME frame=35940 elapsed_ms=599605 heap=1261568 chain_high=20 guards=ok
HALO_PS2_DONE duration=600 frames=35964 pad_events=2 heap=1261568 guards=ok
"""


class EmulatorResults(unittest.TestCase):
    def test_complete_trace_has_resource_and_input_evidence(self):
        observed = validate_platform(TRACE, 600)
        self.assertEqual(observed["pad_edges"], [8, 16384])
        self.assertEqual(observed["heap"], 1261568)

    def test_missing_progress_input_or_duration_never_passes(self):
        for bad in (TRACE.replace("HALO_PS2_PAD frame=126 edges=8", ""),
                    TRACE.replace("elapsed_ms=599605", "elapsed_ms=1000"),
                    TRACE.replace("duration=600", "duration=15"),
                    TRACE.replace("pad_ready=1", "pad_ready=0")):
            with self.assertRaises(RuntimeError):
                validate_platform(bad, 600)

    def test_guest_failures_heap_growth_and_overflows_never_pass(self):
        for bad in (TRACE + "HALO_PS2_FAIL reason=dma-buffer-canary\n",
                    TRACE.replace("frame=35940 elapsed_ms=599605 heap=1261568", "frame=35940 elapsed_ms=599605 heap=1261600"),
                    TRACE.replace("chain_high=20", "chain_high=65")):
            with self.assertRaises(RuntimeError):
                validate_platform(bad, 600)


if __name__ == "__main__":
    unittest.main()
