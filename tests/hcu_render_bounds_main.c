#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "stream/hcu_render_bounds.h"

#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

int main(void)
{
	static const uint8_t hash[32] = { 0x86, 0xbf, 0x78, 0xd6, 0xc1, 0x66, 0x84, 0x72,
		0x58, 0xe9, 0xc6, 0xd1, 0x5b, 0x68, 0xf0, 0xef, 0x1c, 0x59, 0xfa, 0x52,
		0xb1, 0xb2, 0xbe, 0x8d, 0xac, 0xe7, 0x5f, 0x36, 0x9d, 0xb5, 0xb3, 0x41 };
	hcu_render_model_bound b;
	float center[3], radius, expanded, rotated[3];
	uint8_t wrong_hash[32];
	memset(&b, 0, sizeof b);
	b.profile_id = 16; b.model_chunk = 650; b.source_datum = 1124;
	b.tag_datum = 3784507423u; memcpy(b.model_sha256, hash, sizeof hash);
	/* Exact packed boulder_doublewide RMD 1124 MODL LOD0 sphere. */
	b.center[0] = 0.0013619661331176758f;
	b.center[1] = 0.00026091933250427246f;
	b.center[2] = -0.1942111849784851f;
	b.radius = 1.5343986749649048f; b.valid = 1;
	CHECK(hcu_render_model_bound_resolve(&b, 16, 1124, 650, hash, 3784507423u,
		9, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 17, 1124, 650, hash, 3784507423u, 9, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1125, 650, hash, 3784507423u, 9, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 651, hash, 3784507423u, 9, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 650, hash, 0, 9, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 650, hash, 3784507423u, 8, 9, 9, center, &radius));
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 650, hash, 3784507423u, 9, 9, 8, center, &radius));
	memcpy(wrong_hash, hash, sizeof hash); wrong_hash[7] ^= 1u;
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 650, wrong_hash, 3784507423u, 9, 9, 9, center, &radius));
	b.valid = 0;
	CHECK(!hcu_render_model_bound_resolve(&b, 16, 1124, 650, hash, 3784507423u, 9, 9, 9, center, &radius));
	b.valid = 1;
	expanded = hcu_render_bounds_root_radius(1.4762f, 1.0f, b.center, b.radius);
	CHECK(expanded > 1.70f); /* actual visible VIF vertex is 1.70049 from object root */
	CHECK(expanded > 1.4762f);
	CHECK(hcu_render_bounds_root_radius(1.4762f, 2.0f, b.center, b.radius) > expanded);
	CHECK(hcu_render_bounds_root_radius(1.4762f, -1.0f, b.center, b.radius) == expanded);
	rotated[0] = b.center[1]; rotated[1] = -b.center[0]; rotated[2] = b.center[2];
	CHECK(hcu_render_bounds_root_radius(1.4762f, 1.0f, rotated, b.radius) == expanded);
	CHECK(hcu_render_bounds_root_radius(1.4762f, 0.0f, b.center, b.radius) == 1.4762f);
	/* A root 1.60 units outside a plane was culled with CE's 1.4762 radius;
	 * the packed MODL sphere reaches beyond that plane and therefore retains it. */
	CHECK(-1.60f < -1.4762f);
	CHECK(-1.60f >= -expanded);
	/* Static object well outside the bound still culls. */
	CHECK(-2.0f < -expanded);
	/* Unknown/invalid metadata leaves CE's bound untouched. */
	CHECK(hcu_render_bounds_root_radius(1.4762f, NAN, b.center, b.radius) == 1.4762f);
	CHECK(hcu_render_bounds_root_radius(1.4762f, 1.0f, NULL, b.radius) == 1.4762f);
	puts("hcu_render_bounds tests passed");
	return 0;
}
