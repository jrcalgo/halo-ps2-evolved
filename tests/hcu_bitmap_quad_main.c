#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

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

int main(int argc,char **argv)
{
	uint64_t memory[64*2]; chain_t chain; tex_section textures; hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t v[4]={{10,10,0,0,0x80FF8040},{50,8,1,0,0x80FF8040},
	                          {48,48,1,1,0x80FF8040},{8,50,0,1,0x80FF8040}};
	hcu_bitmap_quad_status status; uint32_t *words; uint64_t *q;
	make_tex(); if(tex_open(&textures,section,sizeof section)!=TEX_OK) return 2;
	memset(memory,0xA5,sizeof memory); chain_init(&chain,memory,64);
	memset(&state,0,sizeof state); state.tex0=GS_TEX0(10,1,GS_PSMT8,3,3,1,0,30,GS_PSMCT32,0,0,1);
	state.screen_w=640; state.screen_h=448; state.clip_w=640; state.clip_h=448;
	state.z=0x1234; state.blend=HCU_BITMAP_BLEND_ALPHA; state.texture_layers=1;
	if(argc>1 && strcmp(argv[1],"add")==0) state.blend=HCU_BITMAP_BLEND_ADD;
	if(argc>1 && strcmp(argv[1],"opaque")==0) state.blend=HCU_BITMAP_BLEND_OPAQUE;
	if(argc>1 && strcmp(argv[1],"premultiplied")==0) state.blend=HCU_BITMAP_BLEND_PREMULTIPLIED;
	if(argc>1 && strcmp(argv[1],"raw_add")==0) state.blend=HCU_BITMAP_BLEND_RAW_ADD;
	if(argc>1 && strcmp(argv[1],"premultiplied_overflow")==0){
		state.blend=HCU_BITMAP_BLEND_PREMULTIPLIED; chain.cap_qw=47;
		status=hcu_bitmap_quad_emit(&chain,&textures,0,&state,v);
		if(status!=HCU_BITMAP_QUAD_CAPACITY||chain.qw||chain.overflow||((uint8_t*)memory)[0]!=0xA5)return 16;
		return 0;
	}
	if(argc>1 && strcmp(argv[1],"multitexture")==0) state.texture_layers=2;
	if(argc>1 && strcmp(argv[1],"overflow")==0){chain.cap_qw=26; status=hcu_bitmap_quad_emit(&chain,&textures,0,&state,v);
		if(status!=HCU_BITMAP_QUAD_CAPACITY||chain.qw!=0||chain.overflow||((uint8_t*)memory)[0]!=0xA5) return 3;
		return 0;}
	if(argc>1 && strcmp(argv[1],"bad_uv")==0){v[2].u=1.1f; status=hcu_bitmap_quad_emit(&chain,&textures,0,&state,v);
		if(status!=HCU_BITMAP_QUAD_INVALID||chain.qw!=0||((uint8_t*)memory)[0]!=0xA5) return 4;
		return 0;}
	status=hcu_bitmap_quad_emit(&chain,&textures,0,&state,v);
	if(argc>1 && strcmp(argv[1],"multitexture")==0){
		if(status!=HCU_BITMAP_QUAD_INVALID||chain.qw!=0) return 12;
		return 0;
	}
	if(status!=HCU_BITMAP_QUAD_OK||chain.qw!=(state.blend==HCU_BITMAP_BLEND_PREMULTIPLIED?48u:27u)) return 5;
	if(((memory[0]>>28)&7u)!=DMA_ID_CNT||(memory[0]&0xFFFFu)!=chain.qw-1u) return 6;
	words=(uint32_t*)((uint8_t*)memory+16); if((words[3]&0xFFFFu)!=chain.qw-2u) return 7;
	q=(uint64_t*)((uint8_t*)memory+32);
	if(q[0]!=GIF_TAG(5,1,0,0,GIFX_FLG_PACKED,1)||q[1]!=GIF_REGS_AD||q[3]!=GS_A_TEX0_1) return 8;
	if(q[12]!=GIF_TAG(6,1,1,GS_PRIM(GSX_PRIM_TRIANGLE,1,1,0,state.blend==HCU_BITMAP_BLEND_OPAQUE?0:1,0,1,0,0),GIFX_FLG_PACKED,3)||q[13]!=0x531) return 9;
	/* Walk GIF NLOOP/NREG fields independently; DIRECT consumes initialized data exactly. */
	{
		unsigned consumed=0, direct=words[3]&0xFFFFu;
		while(consumed<direct){
			uint64_t tag=q[consumed*2u];
			unsigned loops=(unsigned)(tag&0x7FFFu), registers=(unsigned)((tag>>60)&15u);
			unsigned packet=1u+loops*(registers?registers:16u);
			if(packet>direct-consumed)return 14;
			consumed+=packet;
		}
		if(consumed+2u!=chain.qw)return 14;
		if(((uint8_t*)memory)[chain.qw*16u]!=0xA5)return 15;
	}
	{
		uint64_t expected=GS_ALPHA(0,1,0,1,0);
		if(state.blend==HCU_BITMAP_BLEND_ADD)expected=GS_ALPHA(0,2,0,1,0);
		if(state.blend==HCU_BITMAP_BLEND_RAW_ADD)expected=GS_ALPHA(0,2,2,1,128);
		if(state.blend==HCU_BITMAP_BLEND_PREMULTIPLIED)expected=GS_ALPHA(2,1,0,1,0);
		if(q[6]!=expected)return 13;
		if(state.blend==HCU_BITMAP_BLEND_PREMULTIPLIED){
			if(q[52]!=GS_ALPHA(0,2,2,1,128))return 17;
			if(memcmp(q+14,q+56,36u*sizeof(uint64_t)))return 18;
		}
	}
	/* Modulation unity is 128: CE white must not double the texture brightness. */
	if((uint32_t)q[14]!=128u||(uint32_t)(q[14]>>32)!=64u||(uint32_t)q[15]!=32u)return 19;

	/* First vertex gets half-texel UVs, 0x80 -> GS alpha 64, and preserved depth. */
	if((uint32_t)q[16]!=8u||(uint32_t)(q[16]>>32)!=8u||(uint32_t)(q[15]>>32)!=64u||q[19]!=0x1234u) return 10;
	/* Rotated second screen vertex is emitted next and has U=7.5 texels (120 in 10.4). */
	if((uint32_t)q[22]!=120u) return 11;
	return 0;
}
