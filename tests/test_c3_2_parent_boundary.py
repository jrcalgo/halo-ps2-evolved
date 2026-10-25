"""C3.2 parent boundary: the parent consumes CE-published snapshot data and never advances CE simulation.

Static audit of the parent consumer sources and the halo-ps2 renderer paths, plus unit checks of the
counters-based C3.2 guest checker in tools/c2_profile_boot_matrix.py (no guest run is implied).
"""
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PARENT_CONSUMER_FILES = [
    "src/stream/hcu_render_objects.c",
    "src/stream/hcu_render_objects.h",
    "src/stream/hcu_fx_bitmap.c",
    "src/stream/hcu_fx_bitmap.h",
    "src/stream/hcu_render_views.c",
    "src/stream/hcu_render_views.h",
    "src/stream/hcu_render_snapshot.c",
    "src/stream/hcu_render_snapshot.h",
    "src/stream/hcu_render_world.c",
    "src/stream/hcu_render_frame.c",
    "src/stream/hcu_render_content.c",
    "src/stream/hcu_bitmap_dispatch.c",
    "src/stream/hcu_bitmap_frame.c",
    "src/stream/hcu_bitmap_quad.c",
    "src/stream/hcu_bitmap_attach.c",
    "src/stream/hcu_bitmap_renderer.c",
    "src/stream/hcu_pose_asset.c",
    "src/stream/hcu_sound_requests.c",
    "src/stream/hcu_main.c",
]
HALO_PS2_RENDER_GLOB = "submodules/halo-ps2/engine/src/render/*.[ch]"

# CE simulation, animation and node-matrix builders. The parent must never call these.
FORBIDDEN_CE_CALLS = re.compile(
    r"\b(objects_update|objects_tick|game_tick|game_time_update|main_game_render|render_frame|"
    r"object_update\w*|object_compute_node_matrices\w*|object_get_node_matrix|object_new|object_delete|"
    r"object_place\w*|unit_update\w*|biped_update\w*|vehicle_update\w*|weapon_update\w*|"
    r"player_update\w*|first_person_\w+|animation_\w+|model_animation\w*)\s*\(")

# Writers of the snapshot bank. Only the bank itself, the CE-facing hooks, the test-only synthetic
# producer (HCU_C3_OBJECTS_SYNTHETIC, off by default) and the map-load generation setter may appear.
BANK_WRITER_CALLS = re.compile(
    r"\bhcu_snapshot_bank_(begin_write|intern_object|commit|abandon|set_map_generation)\s*\(")
BANK_WRITER_ALLOWED = {
    "src/stream/hcu_snapshot_bank.c": None,      # the bank implementation
    "src/stream/hcu_render_objects.c": {"publish_synthetic"},   # gated test-only producer
    "src/stream/hcu_main.c": {"hcu_c3_snapshot_map_loaded"},     # map-load generation metadata
}

# A mutable frame-snapshot pointer or a store through one, in consumer code.
SNAPSHOT_STORE = re.compile(
    r"\b(snap|snapshot|s_snapshot|s_pose_snapshot|s_pin\.snapshot|pin->snapshot)\w*(\.|->)[\w.\[\]>-]*\s*"
    r"(=(?!=)|\+=|-=|\|=|&=|\+\+|--)")
SNAPSHOT_MEM_WRITE = re.compile(
    r"\bmem(set|cpy|move)\s*\(\s*&?\s*(snap|snapshot|s_snapshot|s_pose_snapshot|s_pin\.snapshot|pin->snapshot)\b")


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _functions(text):
    """(name, body) for column-0 function definitions; a coarse split that the repo's style supports."""
    starts = [(m.start(), m.group(1)) for m in re.finditer(r"^[A-Za-z_][\w \t\*]*?\b(\w+)\s*\([^;]*$", text, re.M)]
    out = []
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        out.append((name, text[pos:end]))
    return out


def test_parent_consumer_sources_call_no_ce_simulation_animation_or_node_builders():
    offenders = []
    for rel in PARENT_CONSUMER_FILES:
        for lineno, line in enumerate(_strip_comments(_read(rel)).splitlines(), 1):
            if FORBIDDEN_CE_CALLS.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    for path in sorted(ROOT.glob(HALO_PS2_RENDER_GLOB)):
        for lineno, line in enumerate(_strip_comments(path.read_text(errors="replace")).splitlines(), 1):
            if FORBIDDEN_CE_CALLS.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "parent calls CE simulation/animation/node builders:\n" + "\n".join(offenders)


def test_parent_consumer_sources_do_not_include_ce_game_headers():
    # Parent code may include halo-ps2 engine headers and the CE port's published-snapshot header only.
    banned = re.compile(r'#include\s+"(game|objects|units|items|animation|scenario|model_animations)/')
    offenders = [rel for rel in PARENT_CONSUMER_FILES if banned.search(_read(rel))]
    assert not offenders, offenders


def test_only_the_bank_and_the_gated_producer_write_snapshot_bank():
    offenders = []
    for rel in PARENT_CONSUMER_FILES + ["src/stream/hcu_snapshot_bank.c", "src/stream/hcu_render_snapshot.c"]:
        text = _strip_comments(_read(rel))
        for name, body in _functions(text):
            if not BANK_WRITER_CALLS.search(body):
                continue
            allowed = BANK_WRITER_ALLOWED.get(rel, "missing")
            if allowed is None or (allowed != "missing" and name in allowed):
                continue
            offenders.append(f"{rel}: {name}")
    assert not offenders, "snapshot bank written outside the allowed producers: " + ", ".join(offenders)


def test_consumer_paths_never_store_through_or_memset_the_published_snapshot():
    offenders = []
    for rel in ["src/stream/hcu_render_objects.c", "src/stream/hcu_fx_bitmap.c", "src/stream/hcu_render_views.c",
                "src/stream/hcu_main.c"]:
        text = _strip_comments(_read(rel))
        for name, body in _functions(text):
            if name in BANK_WRITER_ALLOWED.get(rel, set()) or name in ("hcu_render_synthetic_begin",
                                                                      "hcu_render_synthetic_view",
                                                                      "hcu_render_synthetic_object_add"):
                continue
            for m in SNAPSHOT_STORE.finditer(body):
                offenders.append(f"{rel}:{name}: {m.group(0)}")
            for m in SNAPSHOT_MEM_WRITE.finditer(body):
                offenders.append(f"{rel}:{name}: {m.group(0)}")
    assert not offenders, "consumer code writes the published snapshot:\n" + "\n".join(offenders)


def test_consumer_selectors_take_const_snapshot_pointers():
    text = _strip_comments(_read("src/stream/hcu_render_objects.c"))
    selectors = ["hcu_render_objects_select", "hcu_render_objects_select_first_person",
                 "hcu_render_effects_select", "hcu_render_objects_track_poses", "hcu_render_objects_pin",
                 "hcu_render_objects_parity", "hcu_render_objects_frame_begin"]
    defs = dict(_functions(text))
    for name in selectors:
        body = defs.get(name)
        assert body is not None, f"{name} not found"
        signature = body.split("{", 1)[0]
        if name in ("hcu_render_objects_pin", "hcu_render_objects_parity", "hcu_render_objects_frame_begin"):
            # Returns or stores the pointer; frame_begin's result is const.
            assert "const halo_ps2_frame_snapshot" in signature or name == "hcu_render_objects_parity", name
            continue
        assert "const halo_ps2_frame_snapshot *" in signature, f"{name} must take a const snapshot"


def test_consumer_translation_unit_compiles_with_no_cast_away_of_snapshot_const():
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    result = subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wcast-qual",
        "-Wdiscarded-qualifiers", "-fsyntax-only", "-Isrc",
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "src/stream/hcu_render_objects.c",
    ], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_synthetic_test_producer_is_off_in_every_build_path():
    mk = _read("tools/ee-world.mk")
    assert re.search(r"^HCU_C3_OBJECTS_SYNTHETIC \?= 0$", mk, re.M), "synthetic producer must default to 0"
    for rel in ["tools/c2_profile_boot_matrix.py", "tools/c3_integration.py", "tools/c3_render_run.py",
                "tools/c2_guest_run.py"]:
        assert "HCU_C3_OBJECTS_SYNTHETIC" not in _read(rel), f"{rel} enables the synthetic producer"


def _load_matrix():
    spec = importlib.util.spec_from_file_location("c2_profile_boot_matrix_c32",
                                                  ROOT / "tools/c2_profile_boot_matrix.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guest_lines(camera="snapshot", seqs=(10, 40, 70), active=4, source="bank", views=4):
    lines = []
    for frame, seq in zip((0, 30, 60), seqs):
        for v in range(views):
            lines.append(f"HALO_PS2_LOCAL c3-views frame={frame} view={v} camera={camera} pos_x100=0,0,0 active=1")
        lines.append(f"HALO_PS2_LOCAL c3-snapshot frame={frame} map-gen=1 seq={seq} views={views} "
                     f"active-views={active} biped=4 weapon=8 vehicle=2")
        lines.append(f"HALO_PS2_LOCAL c3-objects frame={frame} view=0 source={source} drawn=10")
    return lines


def test_c3_2_checker_qualifies_only_bank_sourced_views_and_advancing_sequence():
    matrix = _load_matrix()
    result = matrix.c3_2_contract_checks(_guest_lines(), 4)
    assert result["c3_2_qualified"], result["reasons"]


def test_c3_2_checker_rejects_parent_authored_fixed_cameras():
    matrix = _load_matrix()
    result = matrix.c3_2_contract_checks(_guest_lines(camera="fixed"), 4)
    assert not result["c3_2_qualified"]
    assert not result["checks"]["camera_from_snapshot_all_views"]


def test_c3_2_checker_rejects_synthetic_object_source_and_stalled_sequence():
    matrix = _load_matrix()
    assert not matrix.c3_2_contract_checks(_guest_lines(source="synthetic"), 4)["checks"]["object_source_bank_only"]
    assert not matrix.c3_2_contract_checks(_guest_lines(seqs=(10, 10, 10)), 4)["checks"]["snapshot_sequence_advances"]


def test_c3_2_checker_fails_closed_without_telemetry():
    matrix = _load_matrix()
    result = matrix.c3_2_contract_checks([], 4)
    assert not result["c3_2_qualified"]
    assert not any(result["checks"].values())


def _spawn_lines(prespawn_camera="fixed", active_camera="snapshot", skip_view=None, never_active=None):
    lines = []
    for v in range(4):
        lines.append(f"HALO_PS2_LOCAL c3-views frame=0 view={v} camera={prespawn_camera} active=0")
    for frame, seq in zip((30, 60), (10, 40)):
        for v in range(4):
            if v == never_active:
                lines.append(f"HALO_PS2_LOCAL c3-views frame={frame} view={v} camera=fixed active=0")
                continue
            camera = "skipped" if v == skip_view else active_camera
            lines.append(f"HALO_PS2_LOCAL c3-views frame={frame} view={v} camera={camera} active=1")
        lines.append(f"HALO_PS2_LOCAL c3-snapshot frame={frame} map-gen=1 seq={seq} views=4 active-views=4")
        lines.append(f"HALO_PS2_LOCAL c3-objects frame={frame} view=0 source=bank drawn=10")
    return lines


def test_c3_2_checker_exempts_only_prespawn_inactive_fixed_rows():
    matrix = _load_matrix()
    result = matrix.c3_2_contract_checks(_spawn_lines(), 4)
    assert result["checks"]["camera_from_snapshot_all_views"], result["reasons"]
    assert result["camera_rows"]["pre_spawn_inactive"] == 4
    assert result["camera_rows"]["fixed"] == 4  # the frame-0 rows are counted but exempt
    assert result["c3_2_qualified"], result["reasons"]


def test_c3_2_checker_rejects_skipped_active_view_and_post_spawn_fixed_rows():
    matrix = _load_matrix()
    skipped = matrix.c3_2_contract_checks(_spawn_lines(skip_view=2), 4)
    assert not skipped["checks"]["camera_from_snapshot_all_views"]
    assert skipped["camera_rows"]["skipped"] == 2
    assert not skipped["c3_2_qualified"]
    # a view that goes inactive after spawn is drawn with the fixed camera today; it must fail as well
    lines = _spawn_lines(never_active=1)
    assert not matrix.c3_2_contract_checks(lines, 4)["checks"]["views_active_per_view"]


def test_c3_2_checker_rejects_fixed_camera_on_active_row():
    matrix = _load_matrix()
    assert not matrix.c3_2_contract_checks(_spawn_lines(active_camera="fixed"), 4)["checks"][
        "camera_from_snapshot_all_views"]
