"""C3.5 per-view camera/HUD/first-person selection: host C tests plus wiring checks on the C3:views glue."""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"


def test_views_pure_module_host_checks():
	with tempfile.TemporaryDirectory(prefix="hcu-render-views-") as temp:
		executable = Path(temp) / "hcu-render-views-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc", "-I" + str(ENGINE),
			"tests/hcu_render_views_main.c",
			"src/stream/hcu_render_views.c",
			str(ENGINE / "render/camera.c"),
			"-lm", "-o", str(executable),
		], cwd=ROOT, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
		assert "all checks passed" in result.stdout


def test_views_block_is_wired_into_c3_render_and_build():
	main = (ROOT / "src/stream/hcu_main.c").read_text()
	mk = (ROOT / "tools/ee-world.mk").read_text()
	assert main.count("/* C3:views begin */") == main.count("/* C3:views end */") >= 2
	block = main[main.index("/* C3:views begin */"):main.index("/* C3:views end */")]
	assert "hcu_render_views.h" in main
	assert "hcu_c3_views_begin" in main and "hcu_c3_views_end" in main
	assert "hcu_c3_views_camera(v, &cam, &vp)" in main
	assert "camera=%s" in main
	assert "HALO_PS2_LOCAL c3-views" in main
	assert "hcu_render_views.o" in mk
	assert "src/stream/hcu_render_views.c" in mk
	# the per-view call sits in the C3:render loop, after the fixed camera it replaces, before the present
	render = main[main.index("void hcu_c3_render_tick(int tick)"):main.index("/* Order: drain GS/DMA")]
	assert render.index("hcu_c3_views_begin();") < render.index("overlay = hcu_c3_views_camera(v, &cam, &vp);")
	# an active view with no usable snapshot camera is skipped (counted), never drawn from a fixed camera
	assert render.index("overlay = hcu_c3_views_camera(v, &cam, &vp);") < render.index("if (!overlay) continue;")
	assert render.index("if (!overlay) continue;") < render.index("bsp_render_view(&cam, overlay, &vp)")
	assert "hcu_views_must_skip(s_c3v.ever_active[v])" in main
	assert "HCU_VIEW_CAMERA_SKIPPED" in main and "skipped=%u" in main and "camera=%s" in main
	assert render.index("hcu_c3_views_end(") < render.index("bsp_render_wait_gpu();")
	assert "bsp_render_view(&cam, NULL, &vp)" not in render
	assert "hcu_views_camera_from_snapshot" in block and "hcu_snapshot_bank_begin_read" in block
	assert "hcu_snapshot_bank_end_read" in block and "fp-drawn=" in block


def test_render_ready_reports_real_camera_source_not_fixed_spawn():
	main = (ROOT / "src/stream/hcu_main.c").read_text()
	assert "camera-source=fixed-spawn" not in main
	assert "camera-source=%s" in main
	assert '#define HCU_C3_CAMERA_SOURCE_NAME "snapshot"' in main
	assert '#define HCU_C3_CAMERA_SOURCE_NAME "fixed"' in main
