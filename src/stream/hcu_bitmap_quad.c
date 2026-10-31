#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

#define GS_A_SCISSOR_1 0x40u
#define GS_A_XYOFFSET_1 0x18u
/* One VIF qword, seven GIF state qwords (TEX0, TEX1, CLAMP, ALPHA, TEST,
 * XYOFFSET, SCISSOR), one draw tag, 6 * 3 vertex qwords. XYOFFSET is the
 * full framebuffer: a dropped restore after the last split view must not
 * shift HUD quads out of their per-pane scissor. */
#define HCU_QUAD_DATA_QW (1u + 8u + 1u + 6u * 3u)

static int finitef(float x) { return isfinite(x); }
static int log2_exact(uint32_t x) { int n=0; if (!x || (x & (x-1u))) return -1; while (x>1u) {x>>=1;n++;} return n; }
static uint32_t fixed_uv(float x) { return (uint32_t)(int32_t)floorf(x*16.0f+0.5f); }
/* Matches bsp_render emit_viewport_state for a viewport at (0,0) covering the screen. */
static uint64_t framebuffer_xyoffset(uint16_t screen_w, uint16_t screen_h)
{
	int xo = (2048 * 16) - (int)screen_w * 8;
	int yo = (2048 * 16) - (int)screen_h * 8;
	return (uint64_t)(xo & 0xFFFF) | ((uint64_t)(yo & 0xFFFF) << 32);
}
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
	/* A tag colour with alpha 0 still tints; the texture's own alpha is the
	 * coverage. Modulate would otherwise zero every HUD sprite. */
	if(!a) a=128u;
	float u=0.5f+v->u*((float)t->width-1.0f), vv=0.5f+v->v*((float)t->height-1.0f);
	q[0]=(uint64_t)r|(uint64_t)g<<32; q[1]=(uint64_t)b|(uint64_t)a<<32;
	q[2]=(uint64_t)fixed_uv(u)|(uint64_t)fixed_uv(vv)<<32; q[3]=0;
	q[4]=(uint64_t)gs_coord(v->x,s->screen_w)|(uint64_t)gs_coord(v->y,s->screen_h)<<32;
	q[5]=s->z&0xFFFFFFu;
}

int hcu_bitmap_view_resolve(const hcu_bitmap_view *views, uint32_t view_count,
	int32_t window_index, int32_t screen_w, int32_t screen_h, hcu_bitmap_rect *out)
{
	uint32_t i;
	if (!out || screen_w <= 0 || screen_h <= 0 || view_count > HCU_BITMAP_MAX_VIEWS) return -1;
	if (view_count == 0u) {
		out->x = 0; out->y = 0; out->w = screen_w; out->h = screen_h;
		return 0;
	}
	if (!views) return -1;
	for (i = 0; i < view_count; i++)
		if (views[i].window_index == window_index) { *out = views[i].rect; return 0; }
	return -1;
}

int hcu_bitmap_quad_place(hcu_bitmap_quad_state_t *s, const hcu_bitmap_rect *r,
	const hcu_bitmap_vertex_t in[4], hcu_bitmap_vertex_t out[4])
{
	unsigned i;
	if (!s || !r || !in || !out || !s->screen_w || !s->screen_h) return -1;
	if (r->x < 0 || r->y < 0 || r->w <= 0 || r->h <= 0) return -1;
	if ((int64_t)r->x + r->w > s->screen_w || (int64_t)r->y + r->h > s->screen_h) return -1;
	if (r->x > 4095 || r->y > 4095 || r->w > 4095 || r->h > 4095) return -1;
	s->clip_x = (uint16_t)r->x; s->clip_y = (uint16_t)r->y;
	s->clip_w = (uint16_t)r->w; s->clip_h = (uint16_t)r->h;
	/* A split pane shows the single-player HUD layout shrunk to fit: the
	 * producer lays the HUD out in a virtual frame of pane/scale pixels
	 * (hud_split_view_begin), and the same uniform scale maps it back. A
	 * full-screen rect has scale 1. */
	{
		float sx = (float)r->w / (float)s->screen_w, sy = (float)r->h / (float)s->screen_h;
		float scale = sx < sy ? sx : sy;
		if (scale > 1.0f) scale = 1.0f;
		for (i = 0; i < 4; i++) {
			out[i] = in[i];
			out[i].x = in[i].x * scale + (float)r->x;
			out[i].y = in[i].y * scale + (float)r->y;
		}
	}
	return 0;
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit_validated(chain_t *c,const tex_info *validated_image,
	const hcu_bitmap_quad_state_t *s,const hcu_bitmap_vertex_t vertices[4])
{
	tex_info image; uint32_t psm,tw,th,tbw,x1,y1,data_qw;
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i;
	static const unsigned order[6]={0,1,2,0,2,3};
	if(!c||!c->base||!validated_image||!s||!vertices||
	   !s->screen_w||!s->screen_h||s->screen_w>4095u||s->screen_h>4095u||s->texture_layers!=1u||
	   !s->clip_w||!s->clip_h||s->z>0xFFFFFFu||(unsigned)s->blend>HCU_BITMAP_BLEND_SUBTRACT ||
	   s->alpha_test>HCU_BITMAP_ALPHA_TEST_EMPTY) return HCU_BITMAP_QUAD_INVALID;
	x1=(uint32_t)s->clip_x+s->clip_w; y1=(uint32_t)s->clip_y+s->clip_h;
	if(x1>s->screen_w||y1>s->screen_h) return HCU_BITMAP_QUAD_INVALID;
	image=*validated_image;
	if(!image.width||!image.height||image.width>4096u||image.height>4096u) return HCU_BITMAP_QUAD_TEX;
	psm=(uint32_t)((s->tex0>>20)&0x3Fu); tw=(uint32_t)((s->tex0>>26)&0xFu);
	th=(uint32_t)((s->tex0>>30)&0xFu); tbw=(uint32_t)((s->tex0>>14)&0x3Fu);
	if(psm!=image.psm||log2_exact(image.width)<0||log2_exact(image.height)<0||
	   tw!=(uint32_t)log2_exact(image.width)||th!=(uint32_t)log2_exact(image.height)||
	   tbw!=((uint32_t)image.width+63u)/64u||((s->tex0>>34)&1u)!=1u||
	   ((s->tex0>>51)&0xFu)!=GS_PSMCT32||((s->tex0>>55)&1u)!=0u) return HCU_BITMAP_QUAD_TEX;
	for(i=0;i<4;i++){
		const hcu_bitmap_vertex_t *v=&vertices[i]; float gx,gy;
		float lo=s->uv_extended?-8.0f:0.0f, hi=s->uv_extended?8.0f:1.0f;
		if(!finitef(v->x)||!finitef(v->y)||!finitef(v->u)||!finitef(v->v)||v->u<lo||v->u>hi||v->v<lo||v->v>hi) return HCU_BITMAP_QUAD_INVALID;
		gx=2048.0f-(float)s->screen_w*0.5f+v->x; gy=2048.0f-(float)s->screen_h*0.5f+v->y;
		if(gx<0.0f||gy<0.0f||gx>4095.0f||gy>4095.0f) return HCU_BITMAP_QUAD_INVALID;
	}
	/* Meter fills keep the two-pass premult (low texture alpha still adds Cs).
	 * Ordinary HUD sprites use one straight-alpha pass, Cs*As+Cd*(1-As).
	 * Retail mode 7 is Cs+Cd*(1-As); that second GIF tag sits after EOP and
	 * the GS never draws it, so a sprite whose colour is Cs disappeared. */
	{
		int meter_premult=s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED && s->alpha_test;
		data_qw=HCU_QUAD_DATA_QW+(meter_premult?21u:0u)+(s->alpha_test?2u:0u);
	}
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,1,0,s->blend==HCU_BITMAP_BLEND_OPAQUE?0:1,0,1,0,0);
	alpha=s->blend==HCU_BITMAP_BLEND_ADD?GS_ALPHA(0,2,0,1,0):GS_ALPHA(0,1,0,1,0);
	if(s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED && s->alpha_test) alpha=GS_ALPHA(2,1,0,1,0);
	if(s->blend==HCU_BITMAP_BLEND_RAW_ADD) alpha=GS_ALPHA(0,2,2,1,128);
	if(s->blend==HCU_BITMAP_BLEND_SUBTRACT) alpha=GS_ALPHA(1,0,2,2,128);
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(7,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=s->tex0; q[3]=GS_A_TEX0_1;
	q[4]=GS_TEX1(1,0,s->point_sampled?0:1,s->point_sampled?0:1,0,0,0); q[5]=GS_A_TEX1_1;
	q[6]=s->clamp ? s->clamp : GS_CLAMP(1,1,0,image.width-1u,0,image.height-1u); q[7]=GS_A_CLAMP_1;
	q[8]=alpha; q[9]=GS_A_ALPHA_1;
	/* Meter passes use the GS alpha test; every other quad writes TEST off, as before. */
	q[10]=s->alpha_test?GS_TEST(1,s->alpha_test==HCU_BITMAP_ALPHA_TEST_FILL?5:2,s->alpha_ref,0,0,0,1,1)
		:GS_TEST(0,1,0,0,0,0,1,1);
	q[11]=GS_A_TEST_1;
	q[12]=framebuffer_xyoffset(s->screen_w,s->screen_h); q[13]=GS_A_XYOFFSET_1;
	q[14]=scissor_value(s); q[15]=GS_A_SCISSOR_1;
	q[16]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[17]=0x531; q+=18;
	for(i=0;i<6;i++,q+=6) put_vertex(q,&vertices[order[i]],s,&image);
	if(s->blend==HCU_BITMAP_BLEND_PREMULTIPLIED && s->alpha_test) {
		q[0]=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
		q[2]=GS_ALPHA(0,2,2,1,128); q[3]=GS_A_ALPHA_1;
		q[4]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[5]=0x531; q+=6;
		for(i=0;i<6;i++,q+=6) put_vertex(q,&vertices[order[i]],s,&image);
	}
	if(s->alpha_test){
		/* Restore TEST to alpha-test off so GS state after this packet is as before the meter. */
		q[0]=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
		q[2]=GS_TEST(0,1,0,0,0,0,1,1); q[3]=GS_A_TEST_1;
	}
	return HCU_BITMAP_QUAD_OK;
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit(chain_t *c,const tex_section *textures,uint32_t image_index,
	const hcu_bitmap_quad_state_t *s,const hcu_bitmap_vertex_t vertices[4])
{
	tex_info image;
	if(!textures||!textures->data||image_index>=textures->texture_count) return HCU_BITMAP_QUAD_INVALID;
	image=tex_get(textures,image_index);
	return hcu_bitmap_quad_emit_validated(c,&image,s,vertices);
}

/* One VIF qword, a GIF A+D tag with ALPHA/TEST/XYOFFSET/SCISSOR, one draw tag,
 * 6 * 3 vertex qwords. */
#define HCU_FLASH_DATA_QW (1u + 5u + 1u + 6u * 3u)

hcu_bitmap_quad_status hcu_bitmap_quad_emit_flash(chain_t *c,uint16_t screen_w,uint16_t screen_h,
	const hcu_bitmap_rect *r,uint32_t z,int16_t type,uint32_t argb)
{
	hcu_bitmap_quad_state_t s; hcu_bitmap_vertex_t in[4],v[4];
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i,pass2; uint32_t data_qw;
	static const unsigned order[6]={0,1,2,0,2,3};
	if(!c||!c->base||!r||type<=0||type>6||z>0xFFFFFFu) return HCU_BITMAP_QUAD_INVALID;
	if(type==5) return HCU_BITMAP_QUAD_OK;
	memset(&s,0,sizeof(s)); s.screen_w=screen_w; s.screen_h=screen_h; s.z=z;
	for(i=0;i<4;i++){
		in[i].x=(i==1||i==2)?(float)r->w:0.0f; in[i].y=(i>=2)?(float)r->h:0.0f;
		in[i].u=0.0f; in[i].v=0.0f; in[i].argb=argb;
	}
	if(hcu_bitmap_quad_place(&s,r,in,v)!=0) return HCU_BITMAP_QUAD_INVALID;
	pass2=(type==1||type==3)?1u:0u;
	data_qw=HCU_FLASH_DATA_QW+(pass2?21u:0u);
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	if(type==1||type==3) alpha=GS_ALPHA(2,1,0,1,0);          /* Cd * (1 - As), then + Cs */
	else if(type==2||type==4) alpha=GS_ALPHA(1,0,2,2,128);   /* Cd - Cs */
	else alpha=GS_ALPHA(0,1,0,1,0);                          /* Cs*As + Cd*(1-As) */
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,0,0,1,0,1,0,0);          /* untextured, alpha blended */
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(4,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=alpha; q[3]=GS_A_ALPHA_1;
	q[4]=GS_TEST(0,1,0,0,0,0,1,1); q[5]=GS_A_TEST_1;
	q[6]=framebuffer_xyoffset(screen_w,screen_h); q[7]=GS_A_XYOFFSET_1;
	q[8]=scissor_value(&s); q[9]=GS_A_SCISSOR_1;
	q[10]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[11]=0x531; q+=12;
	{ tex_info none; memset(&none,0,sizeof(none)); none.width=1; none.height=1;
	  for(i=0;i<6;i++,q+=6) put_vertex(q,&v[order[i]],&s,&none); }
	if(pass2){
		q[0]=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
		q[2]=GS_ALPHA(0,2,2,1,128); q[3]=GS_A_ALPHA_1;
		q[4]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[5]=0x531; q+=6;
		{ tex_info none; memset(&none,0,sizeof(none)); none.width=1; none.height=1;
		  for(i=0;i<6;i++,q+=6) put_vertex(q,&v[order[i]],&s,&none); }
	}
	return HCU_BITMAP_QUAD_OK;
}

/* One VIF qword, a GIF A+D tag with ALPHA/TEST/XYOFFSET/SCISSOR, one draw tag,
 * then a 16-slice ring: 16 * 2 triangles * 3 vertices. */
#define HCU_RING_SLICES 16u
#define HCU_RING_DATA_QW (1u + 5u + 1u + HCU_RING_SLICES * 2u * 3u * 3u)

hcu_bitmap_quad_status hcu_bitmap_quad_emit_ring(chain_t *c,uint16_t screen_w,uint16_t screen_h,
	const hcu_bitmap_rect *r,float cx,float cy,float outer,float inner,uint32_t argb)
{
	hcu_bitmap_quad_state_t s; hcu_bitmap_vertex_t probe[4],placed[4];
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i; uint32_t data_qw;
	float scale,ox,oy,px,py,ro,ri; tex_info none;
	if(!c||!c->base||!r||!screen_w||!screen_h||screen_w>4095u||screen_h>4095u) return HCU_BITMAP_QUAD_INVALID;
	if(!finitef(cx)||!finitef(cy)||!finitef(outer)||!finitef(inner)||outer<=0.0f||inner<0.0f||inner>=outer)
		return HCU_BITMAP_QUAD_INVALID;
	/* the sweep shares the HUD quad's virtual-frame scale and pane offset */
	memset(&s,0,sizeof(s)); s.screen_w=screen_w; s.screen_h=screen_h; s.z=0xFFFFFFu;
	for(i=0;i<4;i++){ probe[i].x=cx; probe[i].y=cy; probe[i].u=0.0f; probe[i].v=0.0f; probe[i].argb=argb; }
	if(hcu_bitmap_quad_place(&s,r,probe,placed)!=0) return HCU_BITMAP_QUAD_INVALID;
	scale=(float)r->w/(float)screen_w < (float)r->h/(float)screen_h ?
		(float)r->w/(float)screen_w : (float)r->h/(float)screen_h;
	if(scale>1.0f) scale=1.0f;
	px=placed[0].x; py=placed[0].y; ro=outer*scale; ri=inner*scale;
	if(ro<0.5f) return HCU_BITMAP_QUAD_OK;
	/* the ring's own bounding square, so the pane scissor and the disc clip agree */
	ox=px-ro; oy=py-ro;
	if(ox<0.0f) ox=0.0f;
	if(oy<0.0f) oy=0.0f;
	{ float x1=px+ro, y1=py+ro;
	  if(x1>(float)screen_w) x1=(float)screen_w;
	  if(y1>(float)screen_h) y1=(float)screen_h;
	  if(x1-ox<1.0f||y1-oy<1.0f) return HCU_BITMAP_QUAD_OK;
	  s.clip_x=(uint16_t)ox; s.clip_y=(uint16_t)oy;
	  s.clip_w=(uint16_t)(x1-ox); s.clip_h=(uint16_t)(y1-oy); }
	data_qw=HCU_RING_DATA_QW;
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	alpha=GS_ALPHA(0,2,2,1,128); /* Cs + Cd, like the sweep's additive square */
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,0,0,1,0,1,0,0);
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(4,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=alpha; q[3]=GS_A_ALPHA_1;
	q[4]=GS_TEST(0,1,0,0,0,0,1,1); q[5]=GS_A_TEST_1;
	q[6]=framebuffer_xyoffset(screen_w,screen_h); q[7]=GS_A_XYOFFSET_1;
	q[8]=scissor_value(&s); q[9]=GS_A_SCISSOR_1;
	q[10]=GIF_TAG(HCU_RING_SLICES*2u*3u,1,1,prim,GIFX_FLG_PACKED,3); q[11]=0x531; q+=12;
	memset(&none,0,sizeof(none)); none.width=1; none.height=1;
	for(i=0;i<HCU_RING_SLICES;i++){
		float a0=(float)i*(6.2831853f/(float)HCU_RING_SLICES);
		float a1=(float)(i+1u)*(6.2831853f/(float)HCU_RING_SLICES);
		float c0=cosf(a0),s0=sinf(a0),c1=cosf(a1),s1=sinf(a1);
		hcu_bitmap_vertex_t tri[6]; unsigned k;
		tri[0].x=px+ri*c0; tri[0].y=py+ri*s0; tri[1].x=px+ro*c0; tri[1].y=py+ro*s0;
		tri[2].x=px+ro*c1; tri[2].y=py+ro*s1; tri[3].x=px+ri*c0; tri[3].y=py+ri*s0;
		tri[4].x=px+ro*c1; tri[4].y=py+ro*s1; tri[5].x=px+ri*c1; tri[5].y=py+ri*s1;
		for(k=0;k<6;k++){ tri[k].u=0.0f; tri[k].v=0.0f; tri[k].argb=argb; put_vertex(q,&tri[k],&s,&none); q+=6; }
	}
	return HCU_BITMAP_QUAD_OK;
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit_marker(chain_t *c,uint16_t screen_w,uint16_t screen_h,
	const hcu_bitmap_rect *r,const hcu_bitmap_vertex_t vertices[4],int subtract)
{
	hcu_bitmap_quad_state_t s; hcu_bitmap_vertex_t v[4];
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i; uint32_t data_qw;
	static const unsigned order[6]={0,1,2,0,2,3};
	if(!c||!c->base||!r||!vertices||!screen_w||!screen_h||screen_w>4095u||screen_h>4095u)
		return HCU_BITMAP_QUAD_INVALID;
	memset(&s,0,sizeof(s)); s.screen_w=screen_w; s.screen_h=screen_h; s.z=0xFFFFFFu;
	if(hcu_bitmap_quad_place(&s,r,vertices,v)!=0) return HCU_BITMAP_QUAD_INVALID;
	for(i=0;i<4;i++){
		float gx,gy;
		if(!finitef(v[i].x)||!finitef(v[i].y)) return HCU_BITMAP_QUAD_INVALID;
		gx=2048.0f-(float)screen_w*0.5f+v[i].x; gy=2048.0f-(float)screen_h*0.5f+v[i].y;
		if(gx<0.0f||gy<0.0f||gx>4095.0f||gy>4095.0f) return HCU_BITMAP_QUAD_INVALID;
	}
	data_qw=HCU_FLASH_DATA_QW;
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	alpha=subtract?GS_ALPHA(1,0,2,2,128):GS_ALPHA(0,2,2,1,128);
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,0,0,1,0,1,0,0);
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(4,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=alpha; q[3]=GS_A_ALPHA_1;
	q[4]=GS_TEST(0,1,0,0,0,0,1,1); q[5]=GS_A_TEST_1;
	q[6]=framebuffer_xyoffset(screen_w,screen_h); q[7]=GS_A_XYOFFSET_1;
	q[8]=scissor_value(&s); q[9]=GS_A_SCISSOR_1;
	q[10]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[11]=0x531; q+=12;
	{ tex_info none; memset(&none,0,sizeof(none)); none.width=1; none.height=1;
	  for(i=0;i<6;i++,q+=6) put_vertex(q,&v[order[i]],&s,&none); }
	return HCU_BITMAP_QUAD_OK;
}
