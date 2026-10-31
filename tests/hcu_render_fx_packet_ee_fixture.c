/* Includes the production adapter so the fixture calls its real static fx_pass. */
#define HCU_RENDER_OBJECTS_EE 1
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stream/hcu_render_objects.c"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %s at %d\n",#x,__LINE__); return 1; } } while (0)

static unsigned char mem[65536] __attribute__((aligned(16)));
static unsigned char guard[64];
int main(int argc,char **argv) {
  uint32_t limit, used, bucket_count, initial_scope, general_limit; chain_t chain; render_ctx_t rc; camera_t cam; render_options_t opt;
  float clip[4][4]; halo_ps2_frame_snapshot snap; halo_ps2_frame_fx_geometry_vertex geo[4]; FILE *f;
  if(argc!=6) return 2; limit=(uint32_t)strtoul(argv[1],0,0); uint32_t count=(uint32_t)strtoul(argv[2],0,0); bucket_count=(uint32_t)strtoul(argv[3],0,0); initial_scope=(uint32_t)strtoul(argv[4],0,0); if(count>HCU_FX_MAX_PER_VIEW || bucket_count<1u || bucket_count>2u || initial_scope>2u) return 3;
  memset(mem,0xa5,sizeof mem); memset(guard,0x6d,sizeof guard); memset(&rc,0,sizeof rc); memset(&snap,0,sizeof snap); memset(&opt,0,sizeof opt);
  camera_init(&cam); cam.aspect=640.0f/448.0f; cam.near_z=.1f; camera_clip_matrix(&cam,clip);
  rc.chain=&chain;rc.cam=&cam;rc.clip=(const float (*)[4])clip;rc.opt=&opt;rc.viewport_w=640;rc.viewport_h=448;
  general_limit=(initial_scope==CHAIN_SCOPE_GENERAL || limit==0u)?limit:limit-1u;
  chain_init(&chain,mem,limit+1u);chain_set_limits(&chain,general_limit,limit);if(initial_scope!=CHAIN_SCOPE_GENERAL)chain_set_scope(&chain,initial_scope);
  snap.view_count=1; snap.views[0].camera.position[0]=0;snap.views[0].camera.forward[0]=1;snap.views[0].camera.up[2]=1;snap.views[0].camera.z_near=.1f;
  s_snapshot=&snap;s_cur_view=0;s_fx_count=count;memset(&s_view_counters,0,sizeof s_view_counters);
  /* A native decal quadrilateral is production input geometry. Camera faces +X. */
  memset(geo,0,sizeof geo);
  geo[0].position[0]=5;geo[0].position[1]=-.5f;geo[0].position[2]=-.5f;
  geo[1].position[0]=5;geo[1].position[1]= .5f;geo[1].position[2]=-.5f;
  geo[2].position[0]=5;geo[2].position[1]= .5f;geo[2].position[2]= .5f;
  geo[3].position[0]=5;geo[3].position[1]=-.5f;geo[3].position[2]= .5f;
  for(uint32_t i=0;i<count;i++){memset(&s_fx[i],0,sizeof s_fx[i]);s_fx[i].kind=HALO_PS2_FRAME_FX_DECAL;s_fx[i].flags=HALO_PS2_FRAME_FX_NATIVE_GEOMETRY;s_fx[i].native_geometry=geo;s_fx[i].scale=1;s_fx[i].framebuffer_blend_function=(uint8_t)(bucket_count>1u && (i&1u) ? 3u : 0u);s_fx[i].color_argb[0]=1;s_fx[i].color_argb[1]=1;s_fx[i].color_argb[2]=1;s_fx[i].color_argb[3]=1;}
  fx_pass(&rc,0); used=chain.qw;
  CHECK(!chain.overflow);CHECK(used<=limit);CHECK(chain.deferred==0 || used<limit);CHECK(chain.scope==initial_scope);CHECK(chain.limit==general_limit);CHECK(chain.hud_limit==limit);CHECK(chain.cap_qw==limit+1u);
  for(unsigned i=(limit+1u)*16u;i<sizeof mem;i++) CHECK(mem[i]==0xa5);
  chain_set_scope(&chain,CHAIN_SCOPE_CLOSE); chain_end(&chain,0); CHECK(!chain.overflow);
  for(unsigned i=(limit+1u)*16u;i<sizeof mem;i++) CHECK(mem[i]==0xa5);
  f=fopen(argv[5],"wb");CHECK(f);CHECK(fwrite(mem,16,chain.qw,f)==chain.qw);fclose(f);
  fprintf(stderr,"limit=%u count=%u buckets=%u scope=%u used-before-END=%u deferred=%u drawn=%u skipped=%u\n",limit,count,bucket_count,initial_scope,used,chain.deferred,s_view_counters.fx_drawn,s_view_counters.fx_skipped_space);
  return 0;
}
/* Texture source is deliberately disabled; these fail-closed stubs satisfy uncalled branches. */
int hcu_asset_profile_lookup(const hcu_asset_profile_view *v,uint32_t t,uint32_t id,hcu_asset_chunk_view *o){(void)v;(void)t;(void)id;(void)o;return -1;}
int hcu_asset_profile_read_chunk(const hcu_asset_profile_view *v,uint32_t t,uint32_t id,void *d,uint32_t n){(void)v;(void)t;(void)id;(void)d;(void)n;return -1;}
tex_status tex_open(tex_section *s,const uint8_t *d,size_t n){(void)s;(void)d;(void)n;return TEX_ERR_LAYOUT;}
tex_info tex_get(const tex_section *s,uint32_t i){tex_info x;(void)s;(void)i;memset(&x,0,sizeof x);return x;}
int tex_mip(const tex_section *s,const tex_info *t,uint32_t l,tex_mip_view *o){(void)s;(void)t;(void)l;(void)o;return 0;}
const uint8_t *tex_clut(const tex_section *s,const tex_info *t){(void)s;(void)t;return NULL;}
int bsp_render_fx_texture(uint32_t k,const bsp_fx_tex_src *s,uint64_t *t){(void)k;(void)s;(void)t;return -1;}
int bsp_render_fx_texture_resident(uint32_t k,uint16_t w,uint16_t h,uint8_t p,uint64_t *t){(void)k;(void)w;(void)h;(void)p;(void)t;return -1;}
u64 rb_take_pending(void){return 0;}
const u32 *rb_zbuf_page_ptr(void){static const u32 z=1;return &z;}
