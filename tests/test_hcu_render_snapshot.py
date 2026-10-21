from pathlib import Path
import subprocess
import tempfile


def test_ce_ps2_renderer_publishes_frame_after_camera_and_first_person_update():
	root = Path(__file__).resolve().parents[1]
	source = (root / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c").read_text()
	start = source.index("void render_frame(\n")
	body = source[start:source.index("\nvoid render_frame_pregame", start)]
	assert "first_person_weapon_render_update();" in body
	assert "first_person_weapon_copy_node_matrices(" in body
	assert "object_get_world_matrix(iterator.index, &world_matrix);" in body
	assert "halo_ps2_render_snapshot_commit(snapshot)" in body
	assert "hcu_render_snapshot_publish_dma();" in body
	assert body.index("first_person_weapon_render_update();") < body.index(
		"halo_ps2_render_snapshot_commit(snapshot)")
	assert body.index("halo_ps2_render_snapshot_commit(snapshot)") < body.index(
		"hcu_render_snapshot_publish_dma();")


def test_ce_matrix_snapshot_reaches_parent_vu1_palette():
	root = Path(__file__).resolve().parents[1]
	engine = root / "submodules/halo-ps2/engine/src"
	with tempfile.TemporaryDirectory(prefix="hcu-render-snapshot-") as temp:
		executable = Path(temp) / "hcu-render-snapshot-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc", "-I" + str(engine),
			"-I" + str(root / "submodules/halo-ce-universal/source"),
			"-I" + str(root / "submodules/halo-ce-universal/port/ps2/include"),
			"tests/hcu_render_snapshot_main.c",
			"src/stream/hcu_render_snapshot.c",
			str(engine / "render/chain.c"),
			str(engine / "sim/skeleton.c"),
			str(engine / "core/mat.c"), "-lm", "-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		subprocess.run([str(executable)], check=True, capture_output=True,
			text=True)
