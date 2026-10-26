/* C3 HUD reserve, real chain and real bitmap quad emitter: the general limit is reached (world, objects,
 * fx) and a HUD quad still emits from the reserve; a general quad at the limit is deferred, not overflowed. */
#include "stream/hcu_bitmap_quad.h"
#include "render/chain.h"
#include "render/storage.h"
#include "render/gs.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static uint8_t section[1184];
static void w16(unsigned o,uint16_t v){section[o]=(uint8_t)v;section[o+1]=(uint8_t)(v>>8);}
static void w32(unsigned o,uint32_t v){w16(o,(uint16_t)v);w16(o+2,(uint16_t)(v>>16));}

static void make_tex(void)
{
	memset(section,0,sizeof section); memcpy(section,"TEXS",4); w16(4,1);
	w32(8,1); w32(12,0); w32(16,64); w32(20,96); w32(24,96); w32(28,sizeof section);
	w32(64,77); w16(68,8); w16(70,8); section[72]=GS_PSMT8; section[73]=1;
	w32(76,96); w32(80,1120); w32(84,64); w16(88,256); w32(92,0x80808080);
}

static uint8_t geometry[BSP_RENDER_GEOMETRY_CHAIN_QW * 16u] __attribute__((aligned(64)));

int main(void)
{
	/* the renderer's real limits: general = cap - tail - reserve, HUD = cap - tail */
	const uint32_t limit = BSP_RENDER_GEOMETRY_CHAIN_QW - BSP_RENDER_GEOMETRY_TAIL_QW - BSP_RENDER_GEOMETRY_HUD_RESERVE_QW;
	const uint32_t hud_limit = BSP_RENDER_GEOMETRY_CHAIN_QW - BSP_RENDER_GEOMETRY_TAIL_QW;
	chain_t c; tex_section textures; hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t v[4] = {{10,10,0,0,0x80FF8040},{50,8,1,0,0x80FF8040},
	                            {48,48,1,1,0x80FF8040},{8,50,0,1,0x80FF8040}};
	uint32_t *fill;

	make_tex();
	CHECK(tex_open(&textures, section, sizeof section) == TEX_OK);
	memset(&state, 0, sizeof state);
	state.tex0 = GS_TEX0(10,1,GS_PSMT8,3,3,1,0,30,GS_PSMCT32,0,0,1);
	state.screen_w = 640; state.screen_h = 448; state.clip_w = 640; state.clip_h = 448;
	state.z = 0x1234; state.blend = HCU_BITMAP_BLEND_ALPHA; state.texture_layers = 1;

	/* world, objects and fx fill the chain to the general limit */
	chain_init(&c, geometry, BSP_RENDER_GEOMETRY_CHAIN_QW);
	chain_set_limits(&c, limit, hud_limit);
	fill = chain_cnt(&c, limit - 1u, 0);
	CHECK(fill != NULL && chain_qwords(&c) == limit);
	CHECK(!chain_has_space(&c, 1));

	/* a general quad at the limit is deferred: refused, counted, no overflow */
	CHECK(hcu_bitmap_quad_emit(&c, &textures, 0, &state, v) == HCU_BITMAP_QUAD_CAPACITY);
	CHECK(!c.overflow && c.deferred >= 1 && chain_qwords(&c) == limit);

	/* the HUD scope emits the quad from the reserve */
	CHECK(chain_set_scope(&c, CHAIN_SCOPE_HUD) == CHAIN_SCOPE_GENERAL);
	CHECK(hcu_bitmap_quad_emit(&c, &textures, 0, &state, v) == HCU_BITMAP_QUAD_OK);
	CHECK(!c.overflow && chain_qwords(&c) > limit && chain_qwords(&c) <= hud_limit);
	chain_set_scope(&c, CHAIN_SCOPE_CLOSE);
	CHECK(chain_cnt(&c, 1 + 2, 0) != NULL && !c.overflow);   /* FINISH-sized write in the tail */
	chain_end(&c, 0);
	CHECK(chain_qwords(&c) <= BSP_RENDER_GEOMETRY_CHAIN_QW && !c.overflow);

	if (failures) { printf("%d failure(s)\n", failures); return 1; }
	printf("ok\n");
	return 0;
}
