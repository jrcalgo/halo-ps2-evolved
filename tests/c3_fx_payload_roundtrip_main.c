#include <assert.h>
#include <string.h>
#include "halo_ps2_fx_iter.h"

int main(void)
{
	halo_ps2_fx_record r;
	halo_ps2_frame_fx_request q;
	unsigned i;
	memset(&r, 0, sizeof r);
	memset(&q, 0, sizeof q);
	r.pass_index = 1; r.particle_final_sequence = 1;
	r.particle_flags = 0x1357; r.particle_shader_flags = 0x2468;
	r.bitmap_width = 320; r.bitmap_height = 192;
	r.framebuffer_blend_function = 2; r.framebuffer_fade_mode = 3;
	r.local_player_index = 1; r.sprite_orientation = 7;
	r.sequence_index = 4; r.frame_index = 9; r.rotation = 1.25f;
	r.lifespan_sec = 8.5f; r.fade_in_sec = 0.75f; r.fade_out_sec = 1.5f;
	r.minimum_pixels = 2.25f; r.lod_cutoff = 0.125f; r.runtime_oo_width = 3.5f;
	r.segment_end_width = 6.25f;
	for (i = 0; i < 4; i++) {
		r.color_argb[i] = 0.1f * (float)(i + 1);
		r.segment_end_color_argb[i] = 0.15f * (float)(i + 1);
		r.sprite_uv[i] = 0.2f * (float)(i + 1);
	}
	r.registration[0] = 0.375f; r.registration[1] = 0.625f;
	halo_ps2_fx_copy_particle_payload(&q, &r);
	assert(q.flags & HALO_PS2_FRAME_FX_PASS_TRANSITION);
	assert(q.flags & HALO_PS2_FRAME_FX_PARTICLE_FINAL_SEQUENCE);
	assert(q.particle_flags == r.particle_flags && q.particle_shader_flags == r.particle_shader_flags);
	assert(q.bitmap_width == r.bitmap_width && q.bitmap_height == r.bitmap_height);
	assert(q.framebuffer_blend_function == 2 && q.framebuffer_fade_mode == 3);
	assert(q.local_player_index == 1 && q.sprite_orientation == 7);
	assert(q.sequence_index == 4 && q.frame_index == 9 && q.rotation == r.rotation);
	assert(q.lifespan_sec == r.lifespan_sec && q.fade_in_sec == r.fade_in_sec && q.fade_out_sec == r.fade_out_sec);
	assert(q.minimum_pixels == r.minimum_pixels && q.lod_cutoff == r.lod_cutoff && q.runtime_oo_width == r.runtime_oo_width);
	assert(q.segment_end_width == r.segment_end_width);
	assert(memcmp(q.color_argb, r.color_argb, sizeof q.color_argb) == 0);
	assert(memcmp(q.segment_end_color_argb, r.segment_end_color_argb, sizeof q.segment_end_color_argb) == 0);
	assert(memcmp(q.sprite_uv, r.sprite_uv, sizeof q.sprite_uv) == 0);
	assert(memcmp(q.registration, r.registration, sizeof q.registration) == 0);

	/* Contrails share the sprite payload writer and preserve atlas/orientation state. */
	memset(&q, 0, sizeof q);
	r.particle_final_sequence = 0;
	r.sprite_orientation = 5; r.framebuffer_blend_function = 6;
	halo_ps2_fx_copy_particle_payload(&q, &r);
	assert(q.sprite_orientation == 5 && q.framebuffer_blend_function == 6);
	assert(memcmp(q.color_argb, r.color_argb, sizeof q.color_argb) == 0);
	assert(memcmp(q.sprite_uv, r.sprite_uv, sizeof q.sprite_uv) == 0);

	/* Decals carry their own color and geometry without aliasing particle fields. */
	memset(&q, 0, sizeof q);
	r.geometry_vertex_count = 4; r.geometry_surface_id = 0x1234;
	r.framebuffer_blend_function = 2; r.framebuffer_fade_mode = 1; r.decal_intensity = 0.625f;
	for (i = 0; i < 4; i++) {
		unsigned j;
		for (j = 0; j < 3; j++) r.geometry_position[i][j] = (float)(i * 3 + j) + 0.25f;
		for (j = 0; j < 2; j++) r.geometry_uv[i][j] = (float)(i * 2 + j) + 0.5f;
	}
	halo_ps2_fx_copy_decal_payload(&q, &r);
	assert(q.decal_geometry_vertex_count == 4 && q.decal_surface_id == 0x1234);
	assert(q.decal_intensity == r.decal_intensity);
	assert(HALO_PS2_FRAME_FX_DECAL_BLEND(q.flags) == 2 && HALO_PS2_FRAME_FX_DECAL_FADE(q.flags) == 1);
	assert(q.flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY);
	assert(memcmp(q.decal_color_argb, r.color_argb, sizeof q.decal_color_argb) == 0);
	for (i = 0; i < 4; i++) {
		assert(memcmp(q.decal_geometry[i].position, r.geometry_position[i], sizeof q.decal_geometry[i].position) == 0);
		assert(memcmp(q.decal_geometry[i].uv, r.geometry_uv[i], sizeof q.decal_geometry[i].uv) == 0);
	}
	return 0;
}
