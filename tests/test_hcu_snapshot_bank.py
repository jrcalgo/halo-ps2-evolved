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
		"four views: ok", "bounds: ok", "reader overwrite: ok", "bytes: v10 bank=",
		"hcu_snapshot_bank tests passed"):
		assert needle in result.stdout, needle


def test_snapshot_bank_lag_trace_captures_real_fx_rejection():
	root = Path(__file__).resolve().parents[1]
	with tempfile.TemporaryDirectory(prefix="hcu-snapshot-bank-trace-") as temp:
		executable = Path(temp) / "hcu-snapshot-bank-trace-test"
		source = Path(temp) / "trace_check.c"
		source.write_text(r'''#include "stream/hcu_snapshot_bank.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
static uint8_t storage[2 * 1024 * 1024] __attribute__((aligned(16)));
int main(void) {
  halo_ps2_frame_snapshot *s;
  hcu_snapshot_bank_rejection r;
  assert(hcu_snapshot_bank_bind(storage, hcu_snapshot_bank_storage_required()) == 0);
  s = hcu_snapshot_bank_begin_write();
  s->fx_request_count = s->effect_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_PARTICLE;
  s->fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
  s->fx_requests[0].bitmap_width = s->fx_requests[0].bitmap_height = 1;
  s->fx_requests[0].sequence_index = s->fx_requests[0].frame_index = 0;
  s->fx_requests[0].age_sec = 0.25f;
  s->fx_requests[0].lifespan_sec = 0.125f;
  s->fx_requests[0].sprite_orientation = 3;
  s->fx_requests[0].sprite_uv[2] = 0.75f;
  assert(hcu_snapshot_bank_commit(s) == -1);
  hcu_snapshot_bank_get_last_rejection(&r);
  assert(r.reason != 0 && r.index == 0 && r.kind == HALO_PS2_FRAME_FX_PARTICLE);
  assert(r.value0_bits == 0x3e800000u && r.value1_bits == 0x3e000000u);
  assert(r.has_fx_request && r.fx_request.sprite_orientation == 3);
  assert(r.fx_request.sprite_uv[2] == 0.75f && r.map_generation == 0);
  s = hcu_snapshot_bank_begin_write();
  s->fx_request_count = s->effect_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_PARTICLE;
  s->fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
  s->fx_requests[0].bitmap_width = s->fx_requests[0].bitmap_height = 1;
  s->fx_requests[0].sequence_index = s->fx_requests[0].frame_index = 0;
  s->fx_requests[0].age_sec = 0.25f;
  s->fx_requests[0].lifespan_sec = 0.125f;
  assert(hcu_snapshot_bank_commit(s) == -1);
  hcu_snapshot_bank_get_last_rejection(&r);
  assert(r.has_fx_request && r.fx_request.lifespan_sec == 0.125f);
  /* Particle flags and shader flags occupy the same union bytes as decal
   * vertex count/surface id. They must not trigger decal validation. */
  s = hcu_snapshot_bank_begin_write();
  memset(&s->fx_requests[0], 0, sizeof s->fx_requests[0]);
  s->fx_request_count = s->effect_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_PARTICLE;
  s->fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
  s->fx_requests[0].bitmap_width = s->fx_requests[0].bitmap_height = 1;
  s->fx_requests[0].sequence_index = s->fx_requests[0].frame_index = 0;
  s->fx_requests[0].lifespan_sec = 0.125f;
  s->fx_requests[0].particle_flags = 0x18;
  s->fx_requests[0].particle_shader_flags = 3;
  assert(hcu_snapshot_bank_commit(s) == 0);
  s = hcu_snapshot_bank_begin_write();
  memset(&s->fx_requests[0], 0, sizeof s->fx_requests[0]);
  s->fx_request_count = s->effect_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_CONTRAIL;
  s->fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
  s->fx_requests[0].bitmap_width = s->fx_requests[0].bitmap_height = 1;
  s->fx_requests[0].particle_flags = 4; /* alias of decal vertex count */
  assert(hcu_snapshot_bank_commit(s) == 0);
  s = hcu_snapshot_bank_begin_write();
  memset(&s->fx_requests[0], 0, sizeof s->fx_requests[0]);
  s->fx_request_count = s->decal_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_DECAL;
  s->fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
  s->fx_requests[0].decal_geometry_vertex_count = 3;
  assert(hcu_snapshot_bank_commit(s) == -1); /* count still requires native geometry */
  s = hcu_snapshot_bank_begin_write();
  memset(&s->fx_requests[0], 0, sizeof s->fx_requests[0]);
  s->fx_request_count = s->effect_count = 1;
  s->fx_requests[0].kind = HALO_PS2_FRAME_FX_PARTICLE;
  s->fx_requests[0].flags = HALO_PS2_FRAME_FX_NATIVE_GEOMETRY;
  assert(hcu_snapshot_bank_commit(s) == -1); /* native geometry remains decal-only */
  return 0;
}''')
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-DHALO_PS2_C3_LAG_TRACE=1", "-Isrc",
			"-I" + str(root / "submodules/halo-ce-universal/port/ps2/include"),
			str(source), "src/stream/hcu_snapshot_bank.c", "-lm", "-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		subprocess.run([str(executable)], cwd=root, check=True, capture_output=True, text=True)


def test_ce_publisher_is_opt_in_and_uses_v3_hooks():
	root = Path(__file__).resolve().parents[1]
	source = (root / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c").read_text()
	assert "#if defined(HALO_PS2_C3_FRAME_SNAPSHOT)" in source
	body = source[source.index("static void ps2_c3_publish_frame_snapshot("):]
	body = body[:body.index("\n}\n", body.index("halo_ps2_frame_snapshot_commit(snapshot)")) + 3]
	assert "halo_ps2_frame_snapshot_begin()" in body
	assert "halo_ps2_frame_snapshot_commit(snapshot)" in body
	assert "object_set_world_matrix(" not in body
	assert "object_get_world_matrix(iterator.index, &world_matrix);" in body
	assert "first_person_weapon_copy_render_models(" in body
	assert "first_person_weapon_resource_slot" in body
	assert "first_person_hands_resource_slot" in body
	assert "first_person_weapon_palette_count" in body
	assert "first_person_hands_palette_count" in body
	assert "ps2_c3_publish_frame_snapshot(windoze, window_count," in source
	assert "object_set_position(" not in body
