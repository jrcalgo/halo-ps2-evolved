from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "submodules/halo-ce-universal/source/scenario/scenario.c"
FIXTURE = ROOT / "tests/hcu_ce_map_lifecycle_main.c"
RUNNER = ROOT / "tests/test_hcu_ce_map_lifecycle.py"


def test_failed_first_bsp_unloads_unpublished_scenario():
	text = SCENARIO.read_text()
	load = text[text.index("boolean scenario_load("):]
	branch = load.index("if (scenario_switch_structure_bsp(0))")
	cleanup = load.index("scenario_unload();", branch)
	return_statement = load.index("return result;", cleanup)
	assert "else" in load[branch:cleanup]
	assert "scenario_unload();" in load[branch:return_statement]
	assert "result = TRUE;" in load[branch:cleanup]


def test_scenario_without_a_bsp_also_unloads_partial_tag_state():
	text = SCENARIO.read_text()
	load = text[text.index("boolean scenario_load("):]
	refs = load.index("if (global_scenario->structure_bsp_references.count > 0)")
	no_bsp = load.index("scenario doesn't have a structure bsp", refs)
	cleanup = load.index("scenario_unload();", no_bsp)
	assert cleanup > no_bsp


def test_scenario_tag_load_failure_releases_ps2_parent_owner():
	text = SCENARIO.read_text()
	load = text[text.index("boolean scenario_load("):]
	failed_tags = load.index("if (global_scenario_index != NONE)")
	else_branch = load.index("\n\telse\n\t{", failed_tags)
	cleanup = load.index("scenario_unload();", else_branch)
	guard = load.rfind("#ifdef HALO_PS2", else_branch, cleanup)
	assert guard >= else_branch
	assert cleanup < load.index("missing_tag = \"\";", cleanup)


def test_lifecycle_fixture_injects_failure_after_a_real_sink_write():
	text = FIXTURE.read_text()
	assert "lifecycle_bsp_fail_after_first_write" in text
	assert "if (failure->calls++ == 0)" in text
	assert "lifecycle_bsp_failure_injected = 1;" in text
	assert "lifecycle_bsp_sink_writes > 0" in text
	assert "size > 36u" in text
	assert "lifecycle_bsp_destination_witness" in text
	assert "lifecycle_owner_release_count == 6" in text
	assert "late streamed CTAG visitor failure stayed unpublished; fresh remount retry passed" in text
	assert "post-copy tag validation failure released owner; full retry passed" in text
	assert "initial B000 late-write failure rolled back; retry passed" in text
	fixture = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
	assert "tag_validate_tags_actual" in fixture
	assert "hcu_bsp_fixture_reject_tag_validation_once" in fixture


def test_lifecycle_fixture_wraps_production_hp2_visitor():
	text = RUNNER.read_text()
	assert '"-Wl,--wrap=world_visit_section_with_scratch"' in text
	assert "initial_ce_scenario_load_late_b000_write_failure_rolled_back" in text
