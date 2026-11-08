#define HCU_BITMAP_GS_RESTORE_IMPL
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
/* GS 128 is opaque. Stay under it so a flash cannot replace the frame. */
#define HCU_FLASH_GS_CAP 96u
#define HCU_FLASH_BLACK_GS 8u

static int flash_near_black(uint32_t argb)
{
	uint32_t r=gs_channel((argb>>16)&255u), g=gs_channel((argb>>8)&255u), b=gs_channel(argb&255u);
	return r<=HCU_FLASH_BLACK_GS && g<=HCU_FLASH_BLACK_GS && b<=HCU_FLASH_BLACK_GS;
}

static uint32_t flash_gs(uint32_t byte, uint32_t cap)
{
	uint32_t c=gs_channel(byte);
	return c>cap?cap:c;
}

static void cap_flash_vertex(uint64_t *q, uint32_t argb, int cap_rgb)
{
	uint32_t a=flash_gs(argb>>24, HCU_FLASH_GS_CAP);
	uint32_t r=cap_rgb?flash_gs((argb>>16)&255u, HCU_FLASH_GS_CAP):(uint32_t)q[0];
	uint32_t g=cap_rgb?flash_gs((argb>>8)&255u, HCU_FLASH_GS_CAP):(uint32_t)(q[0]>>32);
	uint32_t b=cap_rgb?flash_gs(argb&255u, HCU_FLASH_GS_CAP):(uint32_t)q[1];
	q[0]=(uint64_t)r|(uint64_t)g<<32;
	q[1]=(uint64_t)b|(uint64_t)a<<32;
}

static void emit_flash_verts(uint64_t *q, const hcu_bitmap_vertex_t v[4],
	const hcu_bitmap_quad_state_t *s, const unsigned order[6], int cap_a, int cap_rgb)
{
	tex_info none; unsigned i;
	memset(&none,0,sizeof(none)); none.width=1; none.height=1;
	for(i=0;i<6;i++,q+=6){
		put_vertex(q,&v[order[i]],s,&none);
		if(cap_a) cap_flash_vertex(q,v[order[i]].argb,cap_rgb);
	}
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit_flash(chain_t *c,uint16_t screen_w,uint16_t screen_h,
	const hcu_bitmap_rect *r,uint32_t z,int16_t type,uint32_t argb)
{
	hcu_bitmap_quad_state_t s; hcu_bitmap_vertex_t in[4],v[4];
	uint64_t prim,alpha; uint32_t *w; uint64_t *q; unsigned i,pass2; uint32_t data_qw;
	int cap_a, cap_rgb;
	static const unsigned order[6]={0,1,2,0,2,3};
	if(!c||!c->base||!r||type<=0||type>6||z>0xFFFFFFu) return HCU_BITMAP_QUAD_INVALID;
	if(type==5) return HCU_BITMAP_QUAD_OK;
	memset(&s,0,sizeof(s)); s.screen_w=screen_w; s.screen_h=screen_h; s.z=z;
	for(i=0;i<4;i++){
		in[i].x=(i==1||i==2)?(float)r->w:0.0f; in[i].y=(i>=2)?(float)r->h:0.0f;
		in[i].u=0.0f; in[i].v=0.0f; in[i].argb=argb;
	}
	if(hcu_bitmap_quad_place(&s,r,in,v)!=0) return HCU_BITMAP_QUAD_INVALID;
	/* Pass 1 scales Cd by (1-As). A near-black Cs would then add nothing, so skip it. */
	pass2=(type==1||type==3) && !flash_near_black(argb) ? 1u : 0u;
	cap_a=type==1||type==2||type==3;
	cap_rgb=type==1||type==3;
	data_qw=HCU_FLASH_DATA_QW+(pass2?21u:0u);
	if(c->overflow||c->qw>c->cap_qw||
		data_qw+1u+HCU_BITMAP_GS_RESTORE_QW(HCU_BITMAP_GS_RESTORE_DRAW_N)>c->cap_qw-c->qw)
		return HCU_BITMAP_QUAD_CAPACITY;
	if(type==1||type==3) alpha=GS_ALPHA(2,1,0,1,0); /* Cd * (1 - As), then + Cs */
	else alpha=GS_ALPHA(0,1,0,1,0);                 /* darken, min, tint: bounded alpha tint */
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,0,0,1,0,1,0,0); /* untextured, alpha blended */
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(4,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=alpha; q[3]=GS_A_ALPHA_1;
	q[4]=GS_TEST(0,1,0,0,0,0,1,1); q[5]=GS_A_TEST_1;
	q[6]=framebuffer_xyoffset(screen_w,screen_h); q[7]=GS_A_XYOFFSET_1;
	q[8]=scissor_value(&s); q[9]=GS_A_SCISSOR_1;
	q[10]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[11]=0x531; q+=12;
	emit_flash_verts(q,v,&s,order,cap_a,cap_rgb);
	q+=36;
	if(pass2){
		q[0]=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
		q[2]=GS_ALPHA(0,2,2,1,128); q[3]=GS_A_ALPHA_1;
		q[4]=GIF_TAG(6,1,1,prim,GIFX_FLG_PACKED,3); q[5]=0x531; q+=6;
		emit_flash_verts(q,v,&s,order,cap_a,cap_rgb);
	}
	if(!hcu_bitmap_restore_gs_draw_state(c,NULL,NULL,framebuffer_xyoffset(screen_w,screen_h),
		(uint64_t)(screen_w-1u)<<16|(uint64_t)(screen_h-1u)<<48))
		return HCU_BITMAP_QUAD_CAPACITY;
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

/* ---- Controller button glyphs: vector shapes, so a prompt is sharp at any HUD scale. ---- */
#define HCU_GLYPH_MAX_TRIS 96u
#define HCU_GLYPH_SLICES 20u

typedef struct { float x[3], y[3]; uint32_t argb; } glyph_tri_t;
typedef struct { glyph_tri_t t[HCU_GLYPH_MAX_TRIS]; unsigned n; } glyph_mesh_t;

static void gm_tri(glyph_mesh_t *m,float x0,float y0,float x1,float y1,float x2,float y2,uint32_t argb)
{
	glyph_tri_t *t;
	if(m->n>=HCU_GLYPH_MAX_TRIS) return;
	t=&m->t[m->n++];
	t->x[0]=x0; t->y[0]=y0; t->x[1]=x1; t->y[1]=y1; t->x[2]=x2; t->y[2]=y2; t->argb=argb;
}
static void gm_quad(glyph_mesh_t *m,float x0,float y0,float x1,float y1,float x2,float y2,float x3,float y3,uint32_t argb)
{
	gm_tri(m,x0,y0,x1,y1,x2,y2,argb);
	gm_tri(m,x0,y0,x2,y2,x3,y3,argb);
}
/* A stroke from a to b with half thickness ht; both ends are extended by ht so joined strokes meet. */
static void gm_bar(glyph_mesh_t *m,float ax,float ay,float bx,float by,float ht,uint32_t argb)
{
	float dx=bx-ax, dy=by-ay, len=sqrtf(dx*dx+dy*dy), nx, ny, ex, ey;
	if(len<1e-4f) return;
	dx/=len; dy/=len; nx=-dy*ht; ny=dx*ht; ex=dx*ht; ey=dy*ht;
	ax-=ex; ay-=ey; bx+=ex; by+=ey;
	gm_quad(m,ax+nx,ay+ny,bx+nx,by+ny,bx-nx,by-ny,ax-nx,ay-ny,argb);
}
static void gm_ring(glyph_mesh_t *m,float cx,float cy,float ro,float ri,uint32_t argb)
{
	unsigned i;
	for(i=0;i<HCU_GLYPH_SLICES;i++){
		float a0=(float)i*(6.2831853f/(float)HCU_GLYPH_SLICES), a1=(float)(i+1u)*(6.2831853f/(float)HCU_GLYPH_SLICES);
		float c0=cosf(a0),s0=sinf(a0),c1=cosf(a1),s1=sinf(a1);
		if(ri<=0.0f) gm_tri(m,cx,cy,cx+ro*c0,cy+ro*s0,cx+ro*c1,cy+ro*s1,argb);
		else gm_quad(m,cx+ri*c0,cy+ri*s0,cx+ro*c0,cy+ro*s0,cx+ro*c1,cy+ro*s1,cx+ri*c1,cy+ri*s1,argb);
	}
}
/* Letters are 1 unit tall (y -0.5..0.5); returns the advance. */
static float gm_letter(glyph_mesh_t *m,char ch,float x,uint32_t argb)
{
	const float ht=0.085f;
	switch(ch){
	case 'L':
		gm_bar(m,x,-0.5f,x,0.5f,ht,argb); gm_bar(m,x,0.5f,x+0.46f,0.5f,ht,argb); return 0.46f;
	case 'R':
		gm_bar(m,x,-0.5f,x,0.5f,ht,argb); gm_bar(m,x,-0.5f,x+0.4f,-0.5f,ht,argb);
		gm_bar(m,x+0.4f,-0.5f,x+0.4f,0.0f,ht,argb); gm_bar(m,x,0.0f,x+0.4f,0.0f,ht,argb);
		gm_bar(m,x+0.14f,0.0f,x+0.46f,0.5f,ht,argb); return 0.46f;
	case '1':
		gm_bar(m,x+0.16f,-0.5f,x+0.16f,0.5f,ht,argb); gm_bar(m,x-0.08f,-0.3f,x+0.16f,-0.5f,ht,argb); return 0.3f;
	case '2':
		gm_bar(m,x,-0.5f,x+0.42f,-0.5f,ht,argb); gm_bar(m,x+0.42f,-0.5f,x+0.42f,0.0f,ht,argb);
		gm_bar(m,x+0.42f,0.0f,x,0.0f,ht,argb); gm_bar(m,x,0.0f,x,0.5f,ht,argb);
		gm_bar(m,x,0.5f,x+0.42f,0.5f,ht,argb); return 0.42f;
	}
	return 0.0f;
}

static uint32_t glyph_argb(uint32_t rgb,uint32_t alpha_byte,unsigned alpha_pct)
{
	return ((alpha_byte*alpha_pct/100u)<<24)|(rgb&0xFFFFFFu);
}

static void glyph_build(glyph_mesh_t *m,unsigned glyph,uint32_t fade)
{
	m->n=0;
	if(glyph>=1u && glyph<=4u){
		uint32_t plate=glyph_argb(0x1C1E22u,fade,92u), rim=glyph_argb(0x8A8E96u,fade,95u), sym;
		gm_ring(m,0.0f,0.0f,1.0f,0.0f,rim);
		gm_ring(m,0.0f,0.0f,0.9f,0.0f,plate);
		switch(glyph){
		case 1u: sym=glyph_argb(0x7B9CF2u,fade,100u);
			gm_bar(m,-0.42f,-0.42f,0.42f,0.42f,0.085f,sym); gm_bar(m,-0.42f,0.42f,0.42f,-0.42f,0.085f,sym); break;
		case 2u: sym=glyph_argb(0xF0605Eu,fade,100u); gm_ring(m,0.0f,0.0f,0.5f,0.35f,sym); break;
		case 3u: sym=glyph_argb(0xEBA6DCu,fade,100u);
			gm_bar(m,-0.4f,-0.4f,0.4f,-0.4f,0.075f,sym); gm_bar(m,0.4f,-0.4f,0.4f,0.4f,0.075f,sym);
			gm_bar(m,0.4f,0.4f,-0.4f,0.4f,0.075f,sym); gm_bar(m,-0.4f,0.4f,-0.4f,-0.4f,0.075f,sym); break;
		default: sym=glyph_argb(0x4FCDA6u,fade,100u);
			gm_bar(m,0.0f,-0.5f,0.48f,0.36f,0.07f,sym); gm_bar(m,0.48f,0.36f,-0.48f,0.36f,0.07f,sym);
			gm_bar(m,-0.48f,0.36f,0.0f,-0.5f,0.07f,sym); break;
		}
	} else if(glyph>=5u && glyph<=8u){
		/* shoulder / trigger plate: a rectangle with chamfered corners, then the label in white */
		uint32_t rim=glyph_argb(0x8A8E96u,fade,95u), plate=glyph_argb(0x1C1E22u,fade,92u), ink=glyph_argb(0xF2F2F2u,fade,100u);
		static const char *const label[4]={"R1","L1","L2","R2"};
		const char *s=label[glyph-5u];
		float w[2], total, x;
		unsigned k;
		const float hw=1.6f, hh=1.0f, ch=0.34f;
		const float rx[8]={-hw+ch,hw-ch,hw,hw,hw-ch,-hw+ch,-hw,-hw}, ry[8]={-hh,-hh,-hh+ch,hh-ch,hh,hh,hh-ch,-hh+ch};
		for(k=0;k<8u;k++) gm_tri(m,0.0f,0.0f,rx[k],ry[k],rx[(k+1u)&7u],ry[(k+1u)&7u],rim);
		{ const float ix[8]={-hw+ch+0.08f,hw-ch-0.08f,hw-0.09f,hw-0.09f,hw-ch-0.08f,-hw+ch+0.08f,-hw+0.09f,-hw+0.09f};
		  const float iy[8]={-hh+0.09f,-hh+0.09f,-hh+ch+0.04f,hh-ch-0.04f,hh-0.09f,hh-0.09f,hh-ch-0.04f,-hh+ch+0.04f};
		  for(k=0;k<8u;k++) gm_tri(m,0.0f,0.0f,ix[k],iy[k],ix[(k+1u)&7u],iy[(k+1u)&7u],plate); }
		{ glyph_mesh_t *scratch=m; unsigned keep=m->n;
		  w[0]=gm_letter(scratch,s[0],0.0f,0); w[1]=gm_letter(scratch,s[1],0.0f,0);
		  m->n=keep; } /* measuring call only: its triangles are dropped */
		total=w[0]+0.22f+w[1]; x=-total*0.5f;
		x+=gm_letter(m,s[0],x,ink)+0.22f; gm_letter(m,s[1],x,ink);
	}
}

hcu_bitmap_quad_status hcu_bitmap_quad_emit_glyph(chain_t *c,uint16_t screen_w,uint16_t screen_h,
	const hcu_bitmap_rect *r,unsigned glyph,float cx,float cy,float height,uint32_t argb)
{
	hcu_bitmap_quad_state_t s; hcu_bitmap_vertex_t probe[4],placed[4];
	glyph_mesh_t mesh; uint64_t prim; uint32_t *w; uint64_t *q; unsigned i,k; uint32_t data_qw,fade;
	float scale,px,py,unit,ext_x,ext_y; tex_info none;
	if(!c||!c->base||!r||!screen_w||!screen_h||screen_w>4095u||screen_h>4095u||glyph<1u||glyph>8u)
		return HCU_BITMAP_QUAD_INVALID;
	if(!finitef(cx)||!finitef(cy)||!finitef(height)||height<1.0f) return HCU_BITMAP_QUAD_INVALID;
	fade=argb>>24;
	if(fade<4u) return HCU_BITMAP_QUAD_OK;
	memset(&s,0,sizeof(s)); s.screen_w=screen_w; s.screen_h=screen_h; s.z=0xFFFFFFu;
	for(i=0;i<4;i++){ probe[i].x=cx; probe[i].y=cy; probe[i].u=0.0f; probe[i].v=0.0f; probe[i].argb=argb; }
	if(hcu_bitmap_quad_place(&s,r,probe,placed)!=0) return HCU_BITMAP_QUAD_INVALID;
	scale=(float)r->w/(float)screen_w < (float)r->h/(float)screen_h ?
		(float)r->w/(float)screen_w : (float)r->h/(float)screen_h;
	if(scale>1.0f) scale=1.0f;
	px=placed[0].x; py=placed[0].y; unit=height*0.5f*scale;
	if(unit<1.0f) return HCU_BITMAP_QUAD_OK;
	ext_x=unit*(glyph>=5u?1.6f:1.0f); ext_y=unit;
	{ float x0=px-ext_x-1.0f, y0=py-ext_y-1.0f, x1=px+ext_x+1.0f, y1=py+ext_y+1.0f;
	  if(x0<0.0f) x0=0.0f;
	  if(y0<0.0f) y0=0.0f;
	  if(x1>(float)screen_w) x1=(float)screen_w;
	  if(y1>(float)screen_h) y1=(float)screen_h;
	  if(x1-x0<1.0f||y1-y0<1.0f) return HCU_BITMAP_QUAD_OK;
	  s.clip_x=(uint16_t)x0; s.clip_y=(uint16_t)y0; s.clip_w=(uint16_t)(x1-x0); s.clip_h=(uint16_t)(y1-y0); }
	glyph_build(&mesh,glyph,fade);
	if(!mesh.n) return HCU_BITMAP_QUAD_OK;
	data_qw=1u+5u+1u+mesh.n*9u;
	if(c->overflow||c->qw>c->cap_qw||data_qw+1u>c->cap_qw-c->qw) return HCU_BITMAP_QUAD_CAPACITY;
	prim=GS_PRIM(GSX_PRIM_TRIANGLE,1,0,0,1,0,1,0,0);
	w=(uint32_t*)chain_cnt(c,data_qw,0); if(!w) return HCU_BITMAP_QUAD_CAPACITY;
	w[0]=VIF_CODE(VIF_NOP,0,0); w[1]=VIF_CODE(VIF_NOP,0,0); w[2]=VIF_CODE(VIF_FLUSHA,0,0); w[3]=VIF_CODE(VIF_DIRECT,0,data_qw-1u);
	q=(uint64_t*)(w+4);
	q[0]=GIF_TAG(4,1,0,0,GIFX_FLG_PACKED,1); q[1]=GIF_REGS_AD;
	q[2]=GS_ALPHA(0,1,0,1,0); q[3]=GS_A_ALPHA_1; /* Cs*As + Cd*(1-As) */
	q[4]=GS_TEST(0,1,0,0,0,0,1,1); q[5]=GS_A_TEST_1;
	q[6]=framebuffer_xyoffset(screen_w,screen_h); q[7]=GS_A_XYOFFSET_1;
	q[8]=scissor_value(&s); q[9]=GS_A_SCISSOR_1;
	q[10]=GIF_TAG(mesh.n*3u,1,1,prim,GIFX_FLG_PACKED,3); q[11]=0x531; q+=12;
	memset(&none,0,sizeof(none)); none.width=1; none.height=1;
	for(i=0;i<mesh.n;i++)
		for(k=0;k<3u;k++){
			hcu_bitmap_vertex_t v;
			v.x=px+mesh.t[i].x[k]*unit; v.y=py+mesh.t[i].y[k]*unit; v.u=0.0f; v.v=0.0f; v.argb=mesh.t[i].argb;
			put_vertex(q,&v,&s,&none); q+=6;
		}
	return HCU_BITMAP_QUAD_OK;
}
