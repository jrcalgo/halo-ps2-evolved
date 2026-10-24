#!/usr/bin/env python3
"""C2.5 lane alloc-b: verdict merge in the post-load allocation audit, and the console scratch path."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
HS_COMPILE = HCU / "source/hs/hs_compile.c"
TOOL = ROOT / "tools/audit_hcu_postload_allocations.py"
INVENTORY = ROOT / "docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json"


def load_tool():
	spec = importlib.util.spec_from_file_location("audit_hcu_postload_allocations", TOOL)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class VerdictMergeTest(unittest.TestCase):
	def setUp(self):
		self.tool = load_tool()
		self.temp = tempfile.TemporaryDirectory(prefix="hcu-c2-alloc-b-")
		self.addCleanup(self.temp.cleanup)

	def write_alloc_a(self, rows):
		path = Path(self.temp.name) / "verdicts.json"
		path.write_text(json.dumps({"lane": "alloc-a", "verdicts": rows}))
		return path

	def test_absent_file_keeps_built_in_verdicts(self):
		missing = Path(self.temp.name) / "absent.json"
		verdicts, stats = self.tool.merge_verdicts(missing)
		self.assertFalse(stats["alloc_a_present"])
		self.assertEqual(stats["alloc_a_entries"], 0)
		expected = {k: (v, b, "built-in") for k, (v, b) in self.tool.VERDICTS.items()}
		for key, (verdict, basis) in self.tool.FINAL_VERDICTS.items():
			for other in [k for k in expected if k[:2] == key[:2]]:
				del expected[other]
			expected[key] = (verdict, basis, "alloc-final")
		self.assertEqual(verdicts, expected)
		self.assertEqual(stats["final_entries"], len(self.tool.FINAL_VERDICTS))

	def test_file_row_replaces_built_in_rows_of_its_function(self):
		path = self.write_alloc_a([
			{"file": "source/hs/hs_compile.c", "function": "hs_compile_add_source",
				"verdict": "load-only", "evidence": "test row"},
		])
		verdicts, stats = self.tool.merge_verdicts(path)
		key = ("submodules/halo-ce-universal/source/hs/hs_compile.c", "hs_compile_add_source", None)
		self.assertEqual(verdicts[key], ("load-only", "test row", "alloc-a"))
		self.assertFalse(any(k[:2] == key[:2] and k[2] is not None for k in verdicts))
		self.assertEqual(stats["alloc_a_entries"], 1)
		self.assertGreaterEqual(stats["alloc_a_overrides"], 1)

	def test_unknown_verdict_counts_as_open(self):
		path = self.write_alloc_a([
			{"path": "src/stream/x.c", "function": "f", "api": "malloc",
				"verdict": "bounded-in-pool", "basis": "test"},
		])
		verdicts, _ = self.tool.merge_verdicts(path)
		record = {"path": "src/stream/x.c", "enclosing_function": "f", "api": "malloc", "verdict": None}
		found = self.tool.lookup_verdict(verdicts, record["path"], record["enclosing_function"], record["api"])
		self.assertEqual(found[0], "bounded-in-pool")
		summary = self.tool.verdict_summary([{"verdict": "bounded-in-pool"}, {"verdict": "load-only"}], {})
		self.assertEqual(summary["open_total"], 1)
		self.assertEqual(summary["open_counts"]["bounded-in-pool"], 1)

	def test_malformed_file_is_refused(self):
		path = Path(self.temp.name) / "bad.json"
		path.write_text(json.dumps({"verdicts": [{"file": "a.c"}]}))
		with self.assertRaises(SystemExit):
			self.tool.merge_verdicts(path)

	def test_api_less_built_in_lookup_falls_back(self):
		verdicts, _ = self.tool.merge_verdicts(Path(self.temp.name) / "absent.json")
		found = self.tool.lookup_verdict(
			verdicts,
			"submodules/halo-ce-universal/source/tag_files/files.c",
			"file_read_into_memory",
			"match_malloc")
		# Stale expectation fixed in C2.5 alloc-final: the PS2 refusal makes this file's reads unreachable.
		self.assertEqual(found[0], "unreachable-selected-build")


class FinalVerdictLayerTest(unittest.TestCase):
	def setUp(self):
		self.tool = load_tool()
		self.temp = tempfile.TemporaryDirectory(prefix="hcu-c2-alloc-final-")
		self.addCleanup(self.temp.cleanup)

	def test_final_row_overrides_the_other_lanes_row_of_its_function(self):
		path = Path(self.temp.name) / "alloc_a.json"
		path.write_text(json.dumps({"verdicts": [{
			"file": "source/objects/objects.c", "function": "object_name_list_allocate",
			"api": "game_state_malloc", "verdict": "unverified-open", "evidence": "other lane"}]}))
		verdicts, stats = self.tool.merge_verdicts(path)
		found = self.tool.lookup_verdict(
			verdicts, self.tool.OBJ_PATH, "object_name_list_allocate", "game_state_malloc")
		self.assertEqual(found[0], "load-only")
		self.assertEqual(found[2], "alloc-final")
		self.assertGreaterEqual(stats["final_entries"], 1)

	def test_bounded_final_rows_cite_a_counter(self):
		for key, (verdict, basis) in self.tool.FINAL_VERDICTS.items():
			if verdict in self.tool.BOUNDED_VERDICTS:
				self.assertIsNotNone(self.tool.COUNTER_BASIS.search(basis), key)

	def test_every_bounded_verdict_in_the_table_cites_a_counter(self):
		for key, (verdict, basis) in self.tool.VERDICTS.items():
			if verdict in self.tool.BOUNDED_VERDICTS:
				self.assertIsNotNone(self.tool.COUNTER_BASIS.search(basis), key)

	def test_cseries_allocator_wrappers_stay_in_the_ps2_source_set(self):
		# port.json does not exclude cseries_windows.c, and its GlobalAlloc is the PS2 one, so the rows
		# are closed on the compat arena's counters rather than dropped from the inventory.
		relative = {p.relative_to(ROOT).as_posix() for p in self.tool.source_set()}
		self.assertIn("submodules/halo-ce-universal/source/cseries/cseries_windows.c", relative)
		ps2_memory = (HCU / "port/ps2/src/ps2_memory.c").read_text(encoding="latin-1")
		body = ps2_memory[ps2_memory.index("void *__stdcall GlobalAlloc(unsigned int flags, unsigned long size)\n{"):]
		self.assertIn("__wrap_malloc(size);", body[:200])
		for counter in ("malloc_refused_unbound", "malloc_high_water", "sdk_malloc_preactivation_calls"):
			self.assertIn(counter, ps2_memory)


class PortCodeChangeTest(unittest.TestCase):
	def test_hs_refusal_counters_are_exported_through_hs_h(self):
		header = (HCU / "source/hs/hs.h").read_text(encoding="latin-1")
		source = (HCU / "source/hs/hs.c").read_text(encoding="latin-1")
		for name in ("hs_port_recompile_refusal_count", "hs_port_core_load_refusal_count"):
			self.assertIn(f"unsigned long {name}(", header)
			self.assertIn(f"unsigned long {name}(", source)

	def test_checkpoint_revert_is_refused_before_the_whole_image_malloc(self):
		text = (HCU / "source/saved games/game_state_xbox.c").read_text(encoding="latin-1")
		start = text.index("boolean game_state_read_from_file(")
		body = text[start:text.index("boolean game_state_write_core(", start)]
		refusal = body.index("if (game_engine_running())")
		self.assertLess(refusal, body.index("image = malloc(xbox_game_state_globals.buffer_size);"))
		self.assertIn("game_state_port_revert_refusals++;", body)
		self.assertIn("unsigned long game_state_port_revert_refusal_count(", text)

	def test_owner_counter_prototype_is_declared_once_in_the_ps2_header(self):
		header = (HCU / "port/ps2/include/halo_ps2_owner_counters.h").read_text(encoding="latin-1")
		objects = (HCU / "source/objects/objects.c").read_text(encoding="latin-1")
		self.assertIn("int halo_ps2_owner_counters_note_pool(int owner", header)
		self.assertNotIn("int halo_ps2_owner_counters_note_pool(", objects)


class InventoryOpenSitesTest(unittest.TestCase):
	def test_regenerated_inventory_has_no_open_sites(self):
		document = json.loads(INVENTORY.read_text())
		self.assertEqual(document["scope"]["open_total"], 0)
		self.assertEqual(document["scope"]["open_sites"], [])


class ConsoleScratchPathTest(unittest.TestCase):
	def setUp(self):
		self.text = HS_COMPILE.read_text(encoding="latin-1")

	def add_source_body(self):
		start = self.text.index("static char *hs_compile_add_source(\n\tlong source_size,\n\tchar const *source)\n{")
		end = self.text.index("\nvoid hs_compile(", start)
		return self.text[start:end]

	def test_short_command_uses_the_scratch_buffer_without_the_heap(self):
		body = self.add_source_body()
		self.assertIn("!hs_compile_globals.compiling_scenario", body)
		self.assertIn("compiled_size <= sizeof(hs_compile_expression_scratch)", body)
		self.assertIn("compiled_source = hs_compile_expression_scratch;", body)

	def test_heap_block_is_marked_for_dispose_to_free(self):
		body = self.add_source_body()
		self.assertIn("hs_compile_globals.malloced = !hs_compile_globals.compiling_scenario;", body)
		dispose = self.text[self.text.index("void hs_compile_dispose("):]
		dispose = dispose[: dispose.index("\nlong hs_compile_expression(")]
		self.assertIn("if (hs_compile_globals.malloced)", dispose)

	def test_expression_scratch_buffer_is_still_bounded(self):
		self.assertIn("HS_MAXIMUM_DYNAMIC_SOURCE_DATA_BYTES = 0x400", self.text)
		self.assertIn("static char hs_compile_expression_scratch[HS_MAXIMUM_DYNAMIC_SOURCE_DATA_BYTES];", self.text)


class InventoryTest(unittest.TestCase):
	def test_regenerated_inventory_has_no_unverified_lane_b_sites(self):
		document = json.loads(INVENTORY.read_text())
		lane_files = ("hs_compile.c", "game_state_xbox.c", "files.c", "hs.c")
		rows = [c for c in document["callsites"]
			if c.get("phase_classification") != "load-or-init" and c["path"].endswith(lane_files)]
		self.assertTrue(rows)
		self.assertNotIn("unverified", [c.get("verdict") for c in rows])
		self.assertIn("open_total", document["scope"])


if __name__ == "__main__":
	unittest.main()
