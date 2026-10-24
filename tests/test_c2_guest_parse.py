"""Host tests for the C2 guest runner's parsers (no emulator needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import c2_guest_run as run  # noqa: E402

READELF = """\
Elf file type is EXEC (Executable file)

Program Headers:
  Type           Offset   VirtAddr   PhysAddr   FileSiz  MemSiz   Flg Align
  LOAD           0x001000 0x00100000 0x00100000 0x0a0000 0x0a0000 R E 0x1000
  LOAD           0x0a1000 0x001a0000 0x001a0000 0x001000 0x2d0000 RW  0x1000
"""


class ParseLoadSegments(unittest.TestCase):
    def test_segments_and_highest_byte(self):
        segments = run.parse_load_segments(READELF)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["vaddr"], 0x100000)
        self.assertEqual(segments[1]["memsz"], 0x2D0000)
        self.assertEqual(run.highest_guest_byte(segments), 0x1A0000 + 0x2D0000)

    def test_reserve_comparison_uses_guest_value(self):
        highest = 0x1A0000 + 0x2D0000
        self.assertLess(highest, run.GUEST_RESERVE_START)


class HaloLines(unittest.TestCase):
    def test_strips_timestamp_and_keeps_order(self):
        log = ("[    1.0543] HALO_PS2_LOCAL machine entry\n"
               "[    1.0] unrelated line\n"
               "[    2.5] HALO_PS2_LOCAL arena name=current_bsp cap=6291456 used=2097152 high=2097152\n")
        lines = run.halo_lines(log)
        self.assertEqual(lines, ["HALO_PS2_LOCAL machine entry",
                                 "HALO_PS2_LOCAL arena name=current_bsp cap=6291456 used=2097152 high=2097152"])


class Markers(unittest.TestCase):
    def test_missing_marker_is_reported(self):
        lines = ["HALO_PS2_LOCAL partition-selected name=x version=1 tag=1 bsp=1 texture=1 qualified=1",
                 "HALO_PS2_LOCAL arena name=a cap=1 used=0 high=0"]
        found = run.check_markers(lines, lifecycle=False)
        self.assertTrue(found["partition-selected"])
        self.assertTrue(found["arena"])
        self.assertFalse(found["owner-telemetry"])
        self.assertFalse(run.check_markers(lines, lifecycle=False)["map-lifecycle"])
        self.assertIn("lifecycle-unload-reload-complete", run.check_markers(lines, lifecycle=True))

    def test_lifecycle_requires_unload_or_reload(self):
        lines = ["HALO_PS2_LOCAL m2-ui-lifecycle-owner-released cycle=1 cache=0"]
        self.assertTrue(run.check_markers(lines, lifecycle=True)["lifecycle-unload-reload-complete"])
        self.assertFalse(run.check_markers(["HALO_PS2_LOCAL map-mount result=0 active=1"],
                                           lifecycle=True)["lifecycle-unload-reload-complete"])


class Summary(unittest.TestCase):
    def test_counters_per_owner(self):
        lines = [
            "HALO_PS2_LOCAL arena name=frame_scratch base=0x1 cap=393216 used=0 high=12",
            "HALO_PS2_LOCAL cache-owner phase=end name=tags current=7 peak=9 failures=0",
            "HALO_PS2_LOCAL cache-owner phase=end name=bsp current=1 peak=2",
            "HALO_PS2_LOCAL map-mount result=0 active=1",
            "[err] asset root host:/ failed",
        ]
        summary = run.summarize(lines)
        self.assertEqual(summary["arenas"]["frame_scratch"], {"cap": 393216, "used": 0, "high": 12})
        self.assertEqual(summary["cache_owners"]["tags"][0]["peak"], 9)
        self.assertEqual(summary["cache_owners"]["bsp"][0]["current"], 1)
        self.assertEqual(len(summary["map_lifecycle"]), 1)
        self.assertEqual(len(summary["errors"]), 1)


class RegionPeaks(unittest.TestCase):
    """The region peak parser (tools/c2_region_peaks.py) on synthetic guest lines."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import c2_region_peaks as peaks  # noqa: E402
        cls.peaks = peaks

    def test_arena_and_owner_lines(self):
        lines = [
            "HALO_PS2_LOCAL arena name=resident_gameplay cap=5043316 used=4214784 high=4214784 "
            "alloc_failures=0 resets=0 releases=0 invalid_releases=0",
            "HALO_PS2_LOCAL owner-telemetry phase=before-shell partition=bootstrap backing_cap=12582912 "
            "backing_used=274704 backing_high=274704 backing_failures=0 backing_resets=0 "
            "nested_within_parent=1 renderer_drained=1",
            "HALO_PS2_LOCAL owner-telemetry phase=before-shell name=dma kind=backing parent=- bound=1 "
            "cap=1179648 used=0 high=0 failures=0 resets=0",
        ]
        records, failures = self.peaks.parse_run("lifecycle", lines)
        self.assertEqual(failures, [])
        sources = {(record["source"], record["name"]): record for record in records}
        self.assertEqual(sources[("arena", "resident_gameplay")]["high"], 4214784)
        self.assertEqual(sources[("partition", "partition_backing")]["cap"], 12582912)
        self.assertEqual(sources[("owner", "dma")]["cap"], 1179648)
        self.assertEqual(sources[("owner", "dma")]["kind"], "backing")

    def test_context_follows_map_and_lifecycle_boundaries(self):
        lines = [
            "HALO_PS2_LOCAL arena name=frame_scratch cap=393216 used=0 high=0 alloc_failures=0 resets=0",
            "HALO_PS2_LOCAL step8-mp-capacity-query map=bloodgulch clusters=3 pvs_rows=3 collision_called=1",
            "HALO_PS2_LOCAL arena name=frame_scratch cap=393216 used=5 high=77 alloc_failures=0 resets=0",
            "HALO_PS2_LOCAL m2-cycle-boundary phase=map-loaded cycle=1",
            "HALO_PS2_LOCAL cache-owner phase=map-loaded name=bsp current=9 peak=40 publications=1 "
            "failures=0 unmounts=0 resets=0 lease_failures=0 readers_drained=1 mount_rejections=0",
        ]
        records, _ = self.peaks.parse_run("capacity", lines)
        self.assertEqual([record["context"] for record in records],
                         ["boot", "map bloodgulch", "lifecycle map-loaded cycle 1"])
        self.assertEqual(records[-1]["name"], "cache_bsp")
        self.assertEqual(records[-1]["high"], 40)

    def test_workload_line_gives_game_state_peak(self):
        line = ("HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players=4 units=4 "
                "unit_indices=0,1,2,3 ticks=3 objects=94 active_objects=88 game_state_used=3107656 "
                "game_state_peak=3107656 game_state_fail=0 object_pool_used=92768 object_pool_peak=92768 "
                "object_pool_fail=0 dynamic_simulation=separate workload=local-splitscreen-only bots=not-exercised")
        records, _ = self.peaks.parse_run("workload4p", [line])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "game_state")
        self.assertEqual(records[0]["high"], 3107656)
        self.assertEqual(records[0]["context"], "map sidewinder (workload)")

    def test_failure_lines_are_kept_separately(self):
        lines = ["HALO_PS2_FAIL step8-mp-capacity pvs map=ui",
                 "HALO_PS2_LOCAL arena name=tags cap=1 used=0 high=0 alloc_failures=0 resets=0"]
        records, failures = self.peaks.parse_run("capacity", lines)
        self.assertEqual(failures, ["step8-mp-capacity pvs map=ui"])
        self.assertEqual(len(records), 1)

    def test_slack_is_capacity_minus_max_high_and_unmeasured_is_reported(self):
        regions = {"dma_commands": {"name": "dma_commands", "bytes": 1179648},
                   "streaming": {"name": "streaming", "bytes": 1572864}}
        records = [
            {"run": "a", "context": "boot", "source": "arena", "name": "dma_commands", "cap": 1179648,
             "used": 0, "high": 0, "failures": 0, "resets": 0, "phase": None},
            {"run": "b", "context": "map sidewinder", "source": "owner", "name": "dma", "cap": 1179648,
             "used": 0, "high": 294912, "failures": 0, "resets": 0, "phase": "x"},
        ]
        rows = {row["name"]: row for row in self.peaks.build_rows(records, regions, {})}
        dma = rows["dma_commands"]
        self.assertEqual(dma["max_high"], 294912)
        self.assertEqual(dma["slack"], 1179648 - 294912)
        self.assertEqual(dma["max_high_run"], "b")
        self.assertTrue(dma["workload_measured"])
        self.assertFalse(rows["streaming"]["measured"])
        self.assertIsNone(rows["streaming"]["slack"])

    def test_elf_static_uses_the_load_extent(self):
        regions = {"elf_static": {"name": "elf_static", "bytes": 2097152}}
        row = self.peaks.static_row("elf_static", regions["elf_static"], {"lifecycle": 0x1A0000 + 0x2D0000})
        self.assertEqual(row["max_high"], 0x1A0000 + 0x2D0000 - 0x100000)
        self.assertEqual(row["slack"], 2097152 - row["max_high"])
        self.assertTrue(row["measured"])


if __name__ == "__main__":
    unittest.main()
