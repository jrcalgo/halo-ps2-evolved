"""Asset-free regression for the production C3 first-person pose freshness helper."""
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ps2_c3_pose_freshness_paths(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        return
    executable = tmp_path / "ps2_fp_pose_update_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        str(ROOT / "tests/ps2_fp_pose_update_main.c"), "-o", str(executable),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(executable)], cwd=ROOT, check=True,
        capture_output=True, text=True, timeout=30)
    assert "PS2 first-person pose freshness helper fixture passed" in result.stdout


def test_ps2_snapshot_updates_after_selecting_each_ce_camera():
    source = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c").read_text()
    bitmap_start = source.index("static int32_t ps2_bitmap_frame_run(\n\tstruct render_window")
    bitmap = source[bitmap_start:
                    source.index("/* C3:snapshot begin */", bitmap_start)]
    assert bitmap.index("render.local_player_index = window->local_player_index;") < \
        bitmap.index("render.camera = window->render_camera;") < \
        bitmap.index("ps2_c3_ensure_first_person_pose_current();") < \
        bitmap.index("s_bitmap_frame_consumer.set_view(")

    snapshot = source[source.index("static void ps2_c3_publish_frame_snapshot("):]
    assert snapshot.index("render.local_player_index = window->local_player_index;") < \
        snapshot.index("render.camera = window->render_camera;") < \
        snapshot.index("ps2_c3_ensure_first_person_pose_current();") < \
        snapshot.index("first_person_weapon_copy_render_models(")

    frame = source[source.index("void render_frame("):]
    assert frame.index("halo_ps2_fp_pose_tracker_reset(&s_c3_fp_pose_tracker);") < \
        frame.index("if (s_bitmap_frame_consumer_registered &&")
    assert "#if !defined(HALO_PS2_C3_FRAME_SNAPSHOT)\n\tif (!s_bitmap_frame_consumer_registered &&" in frame
