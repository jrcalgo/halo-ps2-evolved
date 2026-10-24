from pathlib import Path
import subprocess
import tempfile


def test_snapshot_bank_host_contract():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-snapshot-bank-") as temp:
		executable = Path(temp) / "hcu-snapshot-bank-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-Isrc",
			"-I" + str(root / "submodules/halo-ce-universal/port/ps2/include"),
			"tests/hcu_snapshot_bank_main.c",
			"src/stream/hcu_snapshot_bank.c",
			"-lm", "-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		result = subprocess.run([str(executable)], check=True,
			capture_output=True, text=True)
	for needle in ("version: ok", "sequence: ok", "dedupe: ok", "refusal:",
		"four views: ok", "bounds: ok", "bytes: v2 bank=191808",
		"hcu_snapshot_bank tests passed"):
		assert needle in result.stdout, needle


def test_ce_publisher_is_opt_in_and_uses_v2_hooks():
	root = Path(__file__).resolve().parents[1]
	source = (root / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c").read_text()
	assert "#if defined(HALO_PS2_C3_FRAME_SNAPSHOT)" in source
	body = source[source.index("static void ps2_c3_publish_frame_snapshot("):]
	body = body[:body.index("\n}\n", body.index("halo_ps2_frame_snapshot_commit(snapshot)")) + 3]
	assert "halo_ps2_frame_snapshot_begin()" in body
	assert "halo_ps2_frame_snapshot_commit(snapshot)" in body
	assert "object_set_world_matrix(" not in body
	assert "object_get_world_matrix(iterator.index, &world_matrix);" in body
	assert "first_person_weapon_copy_node_matrices(" in body
	assert "ps2_c3_publish_frame_snapshot(windoze, window_count," in source
	assert "object_set_position(" not in body
