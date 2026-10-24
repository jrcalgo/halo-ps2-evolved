#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <math.h>
#include <stdint.h>

#define GS_A_SCISSOR_1 0x40u
/* One VIF qword, six GIF state qwords, one draw tag, 6 * 3 vertex qwords. */
#define HCU_QUAD_DATA_QW (1u + 6u + 1u + 6u * 3u)

static int finitef(float x) { return isfinite(x); }
static int log2_exact(uint32_t x) { int n=0; if (!x || (x & (x-1u))) return -1; while (x>1u) {x>>=1;n++;} return n; }
static uint32_t fixed_uv(float x) { return (uint32_t)floorf(x*16.0f+0.5f); }
static uint32_t gs_coord(float x,uint16_t extent) { return (uint32_t)floorf((2048.0f-(float)extent*0.5f+x)*16.0f+0.5f); }
/* GS MODULATE uses 0x80 as unity for both colour and alpha. */
static uint32_t gs_channel(uint32_t value) { return (value*128u+127u)/255u; }

static uint64_t scissor_value(const hcu_bitmap_quad_state_t *s)
{
	uint32_t x1=(uint32_t)s->clip_x+s->clip_w-1u, y1=(uint32_t)s->clip_y+s->clip_h-1u;
	return (uint64_t)s->clip_x | (uint64_t)x1<<16 | (uint64_t)s->clip_y<<32 | (uint64_t)y1<<48;
}

static void put_vertex(uint64_t *q,const hcu_bitmap_vertex_t *v,const hcu_bitmap_quad_state_t *s,const tex_info *t)
{
	uint32_t r=gs_channel((v->argb>>16)&255u),g=gs_channel((v->argb>>8)&255u);
	uint32_t b=gs_channel(v->argb&255u),a=gs_channel(v->argb>>24);
	float u=0.5f+v->u*((float)t->width-1.0f), vv=0.5f+v->v*((float)t->height-1.0f);
	q[0]=(uint64_t)r|(uint64_t)g<<32; q[1]=(uint64_t)b|(uint64_t)a<<32;
	q[2]=(uint64_t)fixed_uv(u)|(uint64_t)fixed_uv(vv)<<32; q[3]=0;
	q[4]=(uint64_t)gs_coord(v->x,s->screen_w)|(uint64_t)gs_coord(v->y,s->screen_h)<<32;
	q[5]=s->z&0xFFFFFFu;
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit(chain_t *c,const tex_section *textures,uint32_t image_index,
	const hcu_bitmap_quad_state_t *s,const hcu_bitmap_vertex_t vertices[4])
{
	tex_info image; uint32_t psm,tw,th,tbw,x1,y1,data_qw;
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i;
	static const unsigned order[6]={0,1,2,0,2,3};
	if(!c||!c->base||!textures||!s||!vertices||!textures->data||image_index>=textures->texture_count||
	   !s->screen_w||!s->screen_h||s->screen_w>4095u||s->screen_h>4095u||s->texture_layers!=1u||
	   !s->clip_w||!s->clip_h||s->z>0xFFFFFFu||(unsigned)s->blend>HCU_BITMAP_BLEND_RAW_ADD) return HCU_BITMAP_QUAD_INVALID;
	x1=(uint32_t)s->clip_x+s->clip_w; y1=(uint32_t)s->clip_y+s->clip_h;
	if(x1>s->screen_w||y1>s->screen_h) return HCU_BITMAP_QUAD_INVALID;
	image=tex_get(textures,image_index);
	if(!image.width||!image.height||image.width>4096u||image.height>4096u) return HCU_BITMAP_QUAD_TEX;
	psm=(uint32_t)((s->tex0>>20)&0x3Fu); tw=(uint32_t)((s->tex0>>26)&0xFu);
	th=(uint32_t)((s->tex0>>30)&0xFu); tbw=(uint32_t)((s->tex0>>14)&0x3Fu);
	if(psm!=image.psm||log2_exact(image.width)<0||log2_exact(image.height)<0||
	   tw!=(uint32_t)log2_exact(image.width)||th!=(uint32_t)log2_exact(image.height)||
	   tbw!=((uint32_t)image.width+63u)/64u||((s->tex0>>34)&1u)!=1u||
	   ((s->tex0>>51)&0xFu)!=GS_PSMCT32||((s->tex0>>55)&1u)!=0u) return HCU_BITMAP_QUAD_TEX;
	for(i=0;i<4;i++){
		const hcu_bitmap_vertex_t *v=&vertices[i]; float gx,gy;
		if(!finitef(v->x)||!finitef(v->y)||!finitef(v->u)||!finitef(v->v)||v->u<0.0f||v->u>1.0f||v->v<0.0f||v->v>1.0f) return HCU_BITMAP_QUAD_INVALID;
		gx=2048.0f-(float)s->screen_w*0.5f+v->x; gy=2048.0f-(float)s->screen_h*0.5f+v->y;
		if(gx<0.0f||gy<0.0f||gx>4095.0f||gy>4095.0f) return HCU_BITMAP_QUAD_INVALID;
	}
	/* Premultiplied CE blend: first Cd *= 1-As, then add unweighted Cs.
	 * Reserving both passes together prevents a capacity failure half-way. */
	data_qw=HCU_QUAD_DATA_QW+(s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED?21u:0u);
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,1,0,s->blend==HCU_BITMAP_BLEND_OPAQUE?0:1,0,1,0,0);
	alpha=s->blend==HCU_BITMAP_BLEND_ADD?GS_ALPHA(0,2,0,1,0):GS_ALPHA(0,1,0,1,0);
	if(s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED) alpha=GS_ALPHA(2,1,0,1,0);
	if(s->blend==HCU_BITMAP_BLEND_RAW_ADD) alpha=GS_ALPHA(0,2,2,1,128);
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(5,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=s->tex0; q[3]=GS_A_TEX0_1;
	q[4]=GS_TEX1(1,0,s->point_sampled?0:1,s->point_sampled?0:1,0,0,0); q[5]=GS_A_TEX1_1;
	q[6]=alpha; q[7]=GS_A_ALPHA_1; q[8]=GS_TEST(0,1,0,0,0,0,1,1); q[9]=GS_A_TEST_1;
	q[10]=scissor_value(s); q[11]=GS_A_SCISSOR_1;
	q[12]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[13]=0x531; q+=14;
	for(i=0;i<6;i++,q+=6) put_vertex(q,&vertices[order[i]],s,&image);
	if(s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED) {
		q[0]=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
		q[2]=GS_ALPHA(0,2,2,1,128); q[3]=GS_A_ALPHA_1;
		q[4]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[5]=0x531; q+=6;
		for(i=0;i<6;i++,q+=6) put_vertex(q,&vertices[order[i]],s,&image);
	}
	return HCU_BITMAP_QUAD_OK;
}
