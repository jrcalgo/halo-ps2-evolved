/* Host ILP32 fixture: real CE bitmap/rasterizer layouts, bounded capture only. */
#include "cseries.h"
#include "bitmaps/bitmap_group.h"
#include "rasterizer/rasterizer.h"
#include "rasterizer/rasterizer_cinematics.h"
#include "render/render.h"
#include "halo_ps2_bitmap_requests.h"

#include <stdio.h>
#include <string.h>

typedef char fixture_ilp32[sizeof(void *) == 4 && sizeof(long) == 4 ? 1 : -1];

static struct bitmap_group s_group;
static struct bitmap_data s_bitmaps[2];
struct rasterizer_window_begin_parameters global_window_parameters;
struct render_globals render;

/* Same layout as hud_draw.c's struct rasterizer_meter_parameters (0x1C). */
typedef struct fixture_meter_parameters {
	pixel32 gradient_min_color;
	pixel32 gradient_max_color;
	pixel32 background_color;
	pixel32 flash_color;
	boolean flash_color_is_negative;
	boolean tint_mode_2;
	byte pad12[2];
	pixel32 tint_color;
	real gradient;
} fixture_meter_parameters;
typedef char fixture_meter_size[sizeof(fixture_meter_parameters) == 0x1C ? 1 : -1];
typedef char fixture_request_bounded[sizeof(halo_ps2_bitmap_request) <= 256 ? 1 : -1];

typedef struct bitmap_consumer_probe {
	uint32_t calls;
	uint32_t observed_count;
	uint32_t observed_generation;
	int32_t return_status;
} bitmap_consumer_probe;

static int32_t bitmap_consumer(
	halo_ps2_bitmap_request_reader const *reader,
	void *context)
{
	bitmap_consumer_probe *probe=(bitmap_consumer_probe *)context;
	if (!reader || !reader->held || !probe)
		return -1;
	probe->calls++;
	probe->observed_count=reader->count;
	probe->observed_generation=reader->generation;
	return probe->return_status;
}

void *csmemset(void *buffer, long value, unsigned long size)
{
	unsigned long i;
	byte *bytes=(byte *)buffer;
	for(i=0;i<size;i++) bytes[i]=(byte)value;
	return buffer;
}

void *tag_block_get_element_with_size(struct tag_block const *block, long index, long size)
{
	if (!block || index < 0 || index >= block->count || !block->address || size <= 0)
		return NULL;
	return (byte *)block->address + index * size;
}

void *tag_get(long group_tag, long tag_index)
{
	return group_tag == BITMAP_GROUP_TAG && tag_index == 19 ? &s_group : NULL;
}

static int check(int condition, char const *label)
{
	if (!condition)
	{
		fprintf(stderr, "FAIL %s\n", label);
		return 0;
	}
	return 1;
}

int main(void)
{
	halo_ps2_bitmap_request_queue queue;
	halo_ps2_bitmap_request_reader reader = { 0 };
	halo_ps2_bitmap_request_reader reader2 = { 0 };
	struct rasterizer_dynamic_screen_geometry_parameters params;
	struct rasterizer_cinematic_screen_effect_parameters screen_effect;
	struct dynamic_screen_vertex vertices[4];
	real_point2d multiply_offset;
	real_rgb_color multiply_tint;
	real multiply_fade;
	bitmap_consumer_probe probe={0, 0, 0, 0};
	bitmap_consumer_probe rejected_probe={0, 0, 0, 0};
	fixture_meter_parameters meter_fixture;
	int i;
	memset(&queue, 0xA5, sizeof(queue));
	memset(&s_group, 0, sizeof(s_group));
	memset(s_bitmaps, 0, sizeof(s_bitmaps));
	s_group.bitmaps.count = 2;
	s_group.bitmaps.address = s_bitmaps;
	s_bitmaps[1].tag_index = 19;
	s_bitmaps[0].tag_index = 19;
	memset(&params, 0, sizeof(params));
	memset(vertices, 0, sizeof(vertices));
	params.map[0] = &s_bitmaps[1];
	params.map_scale[0].i = params.map_scale[0].j = 1.0f;
	params.map_texture_scale[0].i = params.map_texture_scale[0].j = 1.0f;
	params.map_wrapped[0] = TRUE;
	params.framebuffer_blend_function = 7;
	params.point_sampled = TRUE;
	params.alpha_weighted = TRUE;
	for (i = 0; i < 4; i++)
	{
		vertices[i].position.x = (real)(10 + i);
		vertices[i].position.y = (real)(20 + i);
		vertices[i].texture_coordinates.x = (real)i / 4.0f;
		vertices[i].texture_coordinates.y = (real)i / 8.0f;
		vertices[i].color = (pixel32)(0xFF102030u + (unsigned)i);
	}
	halo_ps2_bitmap_requests_init(&queue);
	if (!check(halo_ps2_bitmap_requests_register_consumer(&queue, bitmap_consumer, &probe) == HALO_PS2_BITMAP_REQUEST_OK, "register queue-end consumer")) return 1;
	rasterizer_psuedo_dynamic_screen_quad_draw(&params, vertices);
	if (!check(halo_ps2_bitmap_requests_begin(&queue, 77, 9001, 2, 1) == HALO_PS2_BITMAP_REQUEST_OK, "begin")) return 1;
	if (!check(halo_ps2_bitmap_requests_register_consumer(&queue, bitmap_consumer, &rejected_probe) == HALO_PS2_BITMAP_REQUEST_BUSY, "registration while frame open rejected")) return 1;
	if (!check(halo_ps2_bitmap_requests_clear_consumer(&queue) == HALO_PS2_BITMAP_REQUEST_BUSY, "clear while frame open rejected")) return 1;
	if (!check(halo_ps2_bitmap_requests_set_view(&queue, 3, 2) == HALO_PS2_BITMAP_REQUEST_OK, "set per-window request attribution")) return 1;
	rasterizer_psuedo_dynamic_screen_quad_draw(&params, vertices);
	if (!check(queue.count == 1, "exact-signature bridge capture")) return 1;
	vertices[0].position.x = 999.0f;
	if (!check(queue.count == 1 && queue.requests[0].bitmap_tag_index == 19 && queue.requests[0].bitmap_index == 1, "stable bitmap identity")) return 1;
	if (!check(queue.requests[0].frame_index == 77 && queue.requests[0].generation == 9001 && queue.requests[0].view_index == 3 && queue.requests[0].player_index == 2, "updated per-window frame context")) return 1;
	if (!check(queue.requests[0].vertices[0].x == 10.0f && queue.requests[0].vertices[0].u == 0.0f && queue.requests[0].vertices[3].color == 0xFF102033u, "copied vertices")) return 1;
	if (!check(queue.requests[0].framebuffer_blend_function == 7 && queue.requests[0].point_sampled && queue.requests[0].alpha_weighted && queue.requests[0].bitmap_wrap, "draw state and primary wrap")) return 1;
	params.map[1] = &s_bitmaps[0];
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_UNSUPPORTED, "multitexture rejection")) return 1;
	params.map0_to_1_blend_function = 1; /* CE shader multiply */
	params.map_scale[1].i = 1.0f; params.map_scale[1].j = 2.0f;
	params.map_texture_scale[1].i = params.map_texture_scale[1].j = 1.0f;
	multiply_offset.x = 0.0f; multiply_offset.y = -0.232f;
	multiply_tint.red = 0.5f; multiply_tint.green = 1.0f; multiply_tint.blue = 0.25f;
	multiply_fade = 0.75f;
	params.map_offset[1] = &multiply_offset;
	params.map_tint[1] = &multiply_tint;
	params.map_fade[1] = &multiply_fade;
	params.map_wrapped[1] = TRUE;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK &&
		queue.count == 2 && queue.multiply_count_by_view[3] == 1,
		"two-map CE multiply with animated offset is captured")) return 1;
	{
		halo_ps2_bitmap_request const *request = &queue.requests[1];
		if (!check(request->has_multiply_map && request->multiply_bitmap_tag_index == 19 &&
			request->multiply_bitmap_index == 0 && request->multiply_slot == 6 && request->multiply_wrap &&
			request->multiply_scale_u == 1.0f && request->multiply_scale_v == 2.0f &&
			request->multiply_offset_v < -0.231f && request->multiply_offset_v > -0.233f &&
			request->multiply_tint[0] == 128 && request->multiply_tint[1] == 255 &&
			request->multiply_tint[2] == 64 && request->multiply_tint[3] == 191,
			"secondary map identity, transform, tint, fade, and scratch slot copied")) return 1;
	}
	params.map_offset[1] = NULL; params.map_tint[1] = NULL; params.map_fade[1] = NULL;
	params.map_wrapped[1] = FALSE; params.map0_to_1_blend_function = 0;
	params.map[1] = NULL;
	/* Non-null map-0 parameters are common in CE's overlay path. Accept exact
	 * identity values, while rejecting unsupported or non-finite transforms. */
	multiply_offset.x = 0.0f; multiply_offset.y = 0.0f;
	params.map_offset[0] = &multiply_offset;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK,
		"identity map-0 offset pointer accepted")) return 1;
	multiply_offset.x = 0.25f;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_UNSUPPORTED,
		"nonidentity map-0 offset remains unsupported")) return 1;
	{
		union { uint32_t u; real f; } not_finite;
		not_finite.u = 0x7FC00000u;
		multiply_offset.x = not_finite.f; multiply_offset.y = 0.0f;
		if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_UNSUPPORTED,
			"nonfinite map-0 offset remains unsupported")) return 1;
	}
	params.map_offset[0] = NULL;
	/* Meter capture: CE's struct copied by value; threshold = gradient_min alpha; flash when its alpha is higher. */
	meter_fixture.gradient_min_color = 0x40112233u;
	meter_fixture.gradient_max_color = 0x00FF8800u;
	meter_fixture.background_color = 0x20000000u;
	meter_fixture.flash_color = 0xC0AABBCCu;
	params.meter_parameters = &meter_fixture;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK, "meter capture accepted")) return 1;
	{
		halo_ps2_bitmap_request const *mr = &queue.requests[queue.count - 1];
		if (!check(mr->has_meter == (HALO_PS2_BITMAP_METER_PRESENT | HALO_PS2_BITMAP_METER_FLASHING) &&
			mr->meter_value == 0x40 && mr->meter_gradient_min_color == 0x40112233u &&
			mr->meter_gradient_max_color == 0x00FF8800u && mr->meter_flash_color == 0xC0AABBCCu &&
			mr->meter_background_color == 0x20000000u && mr->bitmap_index == 1, "meter fields copied")) return 1;
		/* A non-flashing meter (flash alpha not above the threshold) keeps only the present bit. */
		meter_fixture.flash_color = 0x40AABBCCu;
		if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK &&
			queue.requests[queue.count - 1].has_meter == HALO_PS2_BITMAP_METER_PRESENT, "non-flashing meter")) return 1;
	}
	params.meter_parameters = NULL;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK &&
		queue.requests[queue.count - 1].has_meter == 0, "plain capture clears meter fields")) return 1;
	params.map[0] = NULL;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_MISSING_TEXTURE, "missing texture")) return 1;
	params.map[0] = &s_bitmaps[1];
	s_bitmaps[1].tag_index = 20;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_INVALID_IDENTITY, "invalid identity")) return 1;
	s_bitmaps[1].tag_index = 19;
	for (i = (int)queue.count; i < (int)HALO_PS2_BITMAP_REQUEST_CAPACITY; i++)
		if (halo_ps2_bitmap_request_capture(&queue, &params, vertices) != HALO_PS2_BITMAP_REQUEST_OK) return 1;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_FULL, "capacity bound")) return 1;
	if (!check(queue.unsupported_count == 3 && queue.missing_texture_count == 1 && queue.invalid_identity_count == 1 && queue.full_count == 1, "failure counters include rejected nonidentity map-0 transforms")) return 1;
	if (!check(halo_ps2_bitmap_requests_end(&queue) == HALO_PS2_BITMAP_REQUEST_OK, "queue end invokes consumer")) return 1;
	if (!check(probe.calls == 1 && probe.observed_count == HALO_PS2_BITMAP_REQUEST_CAPACITY && probe.observed_generation == 9001 && queue.readers == 0, "consumer receives sealed pinned reader and releases it")) return 1;
	if (!check(halo_ps2_bitmap_requests_set_view(&queue, 0, 0) == HALO_PS2_BITMAP_REQUEST_INVALID_ARGUMENT, "closed queue rejects view update")) return 1;
	if (!check(halo_ps2_bitmap_requests_acquire(&queue, 9000, &reader) == HALO_PS2_BITMAP_REQUEST_STALE_GENERATION, "stale generation")) return 1;
	if (!check(halo_ps2_bitmap_requests_acquire(&queue, 9001, &reader) == HALO_PS2_BITMAP_REQUEST_OK && reader.count == HALO_PS2_BITMAP_REQUEST_CAPACITY, "acquire sealed frame")) return 1;
	if (!check(halo_ps2_bitmap_requests_register_consumer(&queue, bitmap_consumer, &rejected_probe) == HALO_PS2_BITMAP_REQUEST_BUSY, "registration while reader active rejected")) return 1;
	if (!check(halo_ps2_bitmap_requests_clear_consumer(&queue) == HALO_PS2_BITMAP_REQUEST_BUSY, "clear while reader active rejected")) return 1;
	if (!check(halo_ps2_bitmap_requests_set_view(&queue, 0, 0) == HALO_PS2_BITMAP_REQUEST_INVALID_ARGUMENT, "reader-held queue rejects view update")) return 1;
	if (!check(halo_ps2_bitmap_requests_acquire(&queue, 9001, &reader) == HALO_PS2_BITMAP_REQUEST_BUSY && queue.readers == 1, "double acquire rejected")) return 1;
	queue.readers = UINT16_MAX;
	if (!check(halo_ps2_bitmap_requests_acquire(&queue, 9001, &reader2) == HALO_PS2_BITMAP_REQUEST_BUSY, "reader count saturation rejected")) return 1;
	queue.readers = 1;
	if (!check(halo_ps2_bitmap_requests_begin(&queue, 78, 9002, 2, 1) == HALO_PS2_BITMAP_REQUEST_BUSY, "reader pins queue")) return 1;
	halo_ps2_bitmap_requests_release(&reader);
	if (!check(halo_ps2_bitmap_requests_clear_consumer(&queue) == HALO_PS2_BITMAP_REQUEST_OK, "clear consumer when quiescent")) return 1;
	if (!check(halo_ps2_bitmap_requests_register_consumer(&queue, bitmap_consumer, &rejected_probe) == HALO_PS2_BITMAP_REQUEST_OK, "register replacement consumer when quiescent")) return 1;
	rejected_probe.return_status = -37;
	if (!check(halo_ps2_bitmap_requests_begin(&queue, 78, 9002, 2, 1) == HALO_PS2_BITMAP_REQUEST_OK, "next generation after release")) return 1;
	if (!check(halo_ps2_bitmap_requests_end(&queue) == HALO_PS2_BITMAP_REQUEST_CONSUMER_FAILED, "consumer failure is returned")) return 1;
	if (!check(rejected_probe.calls == 1 && queue.last_consumer_status == -37 && queue.consumer_failure_count == 1 && queue.readers == 0, "consumer failure status and reader release are explicit")) return 1;
	if (!check(halo_ps2_bitmap_requests_clear_consumer(&queue) == HALO_PS2_BITMAP_REQUEST_OK, "clear consumer after callback completion")) return 1;
	if (!check(halo_ps2_bitmap_requests_end(&queue) == HALO_PS2_BITMAP_REQUEST_NO_ACTIVE_FRAME, "duplicate end rejected")) return 1;
	if (!check(halo_ps2_bitmap_requests_begin(&queue, 79, 9003, 0, 0) == HALO_PS2_BITMAP_REQUEST_OK,
		"begin font pixel-UV capture")) return 1;
	memset(&params, 0, sizeof(params));
	params.map[0] = &s_bitmaps[1];
	params.map_scale[0].i = params.map_scale[0].j = 1.0f;
	params.map_texture_scale[0].i = 0.01f;
	params.map_texture_scale[0].j = 0.02f;
	params.framebuffer_blend_function = 0;
	for (i = 0; i < 4; i++) {
		vertices[i].texture_coordinates.x = (real)(i * 25);
		vertices[i].texture_coordinates.y = (real)(i * 10);
	}
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_OK &&
		queue.requests[0].vertices[2].u == 0.5f && queue.requests[0].vertices[2].v > 0.399f &&
		queue.requests[0].vertices[2].v < 0.401f,
		"font atlas pixel UVs use CE inverse-scale normalization")) return 1;
	vertices[3].texture_coordinates.x = 101.0f;
	if (!check(halo_ps2_bitmap_request_capture(&queue, &params, vertices) == HALO_PS2_BITMAP_REQUEST_UNSUPPORTED &&
		queue.unsupported_reason_mask == HALO_PS2_BITMAP_UNSUPPORTED_UV_RANGE &&
		queue.unsupported_reason_counts[6] == 1 && queue.first_unsupported_reason == HALO_PS2_BITMAP_UNSUPPORTED_UV_RANGE,
		"out-of-range normalized UV stays fail-closed with bounded cause")) return 1;
	memset(&screen_effect, 0, sizeof(screen_effect));
	screen_effect.convolution_mask = &s_bitmaps[0];
	screen_effect.convolution_type = 2;
	screen_effect.convolution_radius = 0.25f;
	screen_effect.filter_light_enhancement_intensity = 1.0f;
	screen_effect.filter_desaturation_intensity = 0.5f;
	screen_effect.filter_desaturation_tint.red = 0.2f;
	screen_effect.filter_desaturation_tint.green = 0.4f;
	screen_effect.filter_desaturation_tint.blue = 0.8f;
	screen_effect.filter_desaturation_is_additive = TRUE;
	screen_effect.filter_light_enhancement_uses_convolution_mask = TRUE;
	screen_effect.filter_desaturation_uses_convolution_mask = TRUE;
	/* The C3 producer installs the active view here; Xbox global window state
	 * may still be stale or zero when the PS2 producer calls interface_draw_screen. */
	render.camera.viewport_bounds.x0 = 12;
	render.camera.viewport_bounds.x1 = 628;
	render.camera.viewport_bounds.y0 = 24;
	render.camera.viewport_bounds.y1 = 456;
	rasterizer_screen_effect(&screen_effect);
	if (!check(queue.count == 2 && queue.screen_effect_mask_requests == 1 &&
		queue.screen_effect_warp_omitted == 1 && queue.screen_effect_filter_omitted == 1,
		"screen effect mask is queued and unsupported warp/filter are counted")) return 1;
	if (!check(queue.requests[1].bitmap_tag_index == 19 && queue.requests[1].bitmap_index == 0 &&
		queue.requests[1].screen_effect_mask == 1u &&
		queue.requests[1].framebuffer_blend_function == 0 && !queue.requests[1].point_sampled &&
		queue.requests[1].vertices[0].x == 12.0f && queue.requests[1].vertices[0].y == 24.0f &&
		queue.requests[1].vertices[2].x == 628.0f && queue.requests[1].vertices[2].y == 456.0f &&
		queue.requests[1].vertices[2].u == 1.0f && queue.requests[1].vertices[2].v == 1.0f,
		"screen effect captures mask identity, view bounds, and linear sampling")) return 1;
	if (!check(queue.screen_effects[0].valid &&
		queue.screen_effects[0].convolution_type == 2 &&
		queue.screen_effects[0].convolution_radius == 0.25f &&
		queue.screen_effects[0].light_enhancement_intensity == 1.0f &&
		queue.screen_effects[0].desaturation_intensity == 0.5f &&
		queue.screen_effects[0].desaturation_tint[0] > 0.19f &&
		queue.screen_effects[0].desaturation_tint[2] > 0.79f &&
		queue.screen_effects[0].desaturation_is_additive &&
		queue.screen_effects[0].light_uses_mask && queue.screen_effects[0].desaturation_uses_mask &&
		queue.screen_effects[0].mask_request_index == 1u,
		"screen effect values and mask request linkage are copied into the active view snapshot")) return 1;
	puts("bitmap-requests-ok records=128 captured=128 queue_end_consumer=1 bounded=1 pointers_retained=0");
	return 0;
}
