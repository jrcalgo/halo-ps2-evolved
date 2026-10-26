#include <stdio.h>
#include "stream/hcu_render_objects.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s line %d\n", #x, __LINE__); return 1; } } while (0)

int main(void)
{
	hcu_object_prepare_key key = { 71u, 9u, 123u, 456u, 5u };
	halo_ps2_snapshot_matrix4x3 src = {0};
	float matrix[16];
	int slot = -1;
	uint32_t hash = 0;
	src.scale = 2.0f;
	src.forward[0] = 1.0f; src.forward[1] = 2.0f; src.forward[2] = 3.0f;
	src.left[0] = 4.0f; src.left[1] = 5.0f; src.left[2] = 6.0f;
	src.up[0] = 7.0f; src.up[1] = 8.0f; src.up[2] = 9.0f;
	src.position[0] = 3.0f; src.position[1] = 4.0f; src.position[2] = 5.0f;
	CHECK(hcu_render_objects_prepare_key_valid(&key, 71u, 9u, 123u, 456u, 5u));
	CHECK(!hcu_render_objects_prepare_key_valid(&key, 72u, 9u, 123u, 456u, 5u));
	CHECK(!hcu_render_objects_prepare_key_valid(&key, 71u, 10u, 123u, 456u, 5u));
	CHECK(!hcu_render_objects_prepare_key_valid(&key, 71u, 9u, 124u, 456u, 5u));
	CHECK(!hcu_render_objects_prepare_key_valid(&key, 71u, 9u, 123u, 457u, 5u));
	CHECK(!hcu_render_objects_prepare_key_valid(&key, 71u, 9u, 123u, 456u, 6u));
	CHECK(hcu_render_objects_prepare_range_valid(1023u, 1u, HALO_PS2_FRAME_MAX_PALETTE));
	CHECK(!hcu_render_objects_prepare_range_valid(1024u, 1u, HALO_PS2_FRAME_MAX_PALETTE));
	CHECK(!hcu_render_objects_prepare_range_valid(0xFFFFFFFEu, 8u, HALO_PS2_FRAME_MAX_PALETTE));
	CHECK(!hcu_render_objects_prepare_range_valid(0u, HALO_PS2_FRAME_MAX_PALETTE + 1u, HALO_PS2_FRAME_MAX_PALETTE));
	CHECK(hcu_render_objects_prepare_range_valid(0u, HALO_PS2_FRAME_MAX_PALETTE, HALO_PS2_FRAME_MAX_PALETTE));
	CHECK(hcu_render_objects_prepare_select(1, &key, 71u, 9u, 123u, 456u, 5u,
		7, 0xCAFEBABEu, 2, 0x12345678u, &slot, &hash));
	CHECK(slot == 7 && hash == 0xCAFEBABEu);
	CHECK(!hcu_render_objects_prepare_select(0, &key, 71u, 9u, 123u, 456u, 5u,
		7, 0xCAFEBABEu, 2, 0x12345678u, &slot, &hash));
	CHECK(slot == 2 && hash == 0x12345678u);
	CHECK(!hcu_render_objects_prepare_select(1, &key, 71u, 9u, 124u, 456u, 5u,
		7, 0xCAFEBABEu, 2, 0x12345678u, &slot, &hash));
	CHECK(slot == 2 && hash == 0x12345678u);
	hcu_render_objects_prepare_matrix(&src, matrix);
	CHECK(matrix[0] == 2.0f && matrix[1] == 4.0f && matrix[2] == 6.0f);
	CHECK(matrix[4] == 8.0f && matrix[5] == 10.0f && matrix[6] == 12.0f);
	CHECK(matrix[8] == 14.0f && matrix[9] == 16.0f && matrix[10] == 18.0f);
	CHECK(matrix[12] == 3.0f && matrix[13] == 4.0f && matrix[14] == 5.0f && matrix[15] == 1.0f);
	CHECK(matrix[3] == 0.0f && matrix[7] == 0.0f && matrix[11] == 0.0f);
	puts("hcu object prepare cache tests passed");
	return 0;
}
