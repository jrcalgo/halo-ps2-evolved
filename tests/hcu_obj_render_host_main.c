/* Behavioral host test for the real obj_render_pass, using tiny platform/chain/model shims. */
#include "render/obj_render.h"
#include "render/gs.h"
#include <stdio.h>
#include <string.h>

static unsigned chain_calls;
static unsigned basis_calls;
static int fail_pose;
void *chain_cnt(chain_t *c, uint32_t q, uint64_t pair) { (void)pair; chain_calls++; c->qw += q; return c->base; }
void chain_ref(chain_t *c, const void *p, uint32_t q, uint64_t pair) { (void)p; (void)pair; c->qw += q; }
int chain_has_space(const chain_t *c, uint32_t q) { return c->qw + q <= c->cap_qw; }
u64 rb_take_pending(void) { return 0; }
void rb_set_pending(u64 p) { (void)p; }
void rb_fog_params(float *k, float *b) { *k = 1.0f; *b = 0.0f; }
uint32_t rb_model_entry(void) { return 1; }
const uint32_t *rb_zbuf_page_ptr(void) { static uint32_t z; return &z; }
u64 rb_object_tex0(unsigned i, const tex_image_t *img, u64 t) { (void)i;(void)img;(void)t; return 0; }
void camera_basis(const camera_t *c, float r[3], float u[3], float f[3]) { (void)c; basis_calls++;r[0]=0;r[1]=1;r[2]=0;u[0]=0;u[1]=0;u[2]=1;f[0]=1;f[1]=f[2]=0; }
int frustum_sphere(const frustum_t *f, const float c[3], float r) { (void)f;(void)r; return c[0] < 50.0f; }
void mat4_transform_point(const mat4 *m, const float p[3], float o[3]) { unsigned i; for(i=0;i<3;i++) o[i]=m->m[3][i]+p[0]*m->m[0][i]+p[1]*m->m[1][i]+p[2]*m->m[2][i]; }
float lodctl_distance_scale(const lodctl_t *l) { (void)l; return 1.0f; }
int lodctl_lod_bias(const lodctl_t *l) { (void)l; return 0; }
model_info model_get(const model_section *s, uint32_t i) { model_info m; (void)s;(void)i; memset(&m,0,sizeof m); m.radius=2.0f; m.region_count=1; m.permutation_count=1; return m; }
void model_select_permutations(const model_section *s,const model_info *m,const char *v,uint16_t *o) { (void)s;(void)m;(void)v;o[0]=0; }
uint32_t model_pick_lod(const model_info *m,float d) { (void)m;(void)d; return 0; }
model_part_range model_parts(const model_section *s,const model_info *m,uint32_t p,uint32_t l) { model_part_range r; (void)s;(void)m;(void)p;(void)l;r.first_part=0;r.part_count=0;return r; }
model_part model_get_part(const model_section *s,uint32_t i) { model_part p;(void)s;(void)i;memset(&p,0,sizeof p);return p; }
model_batch model_get_batch(const model_section *s,uint32_t i) { model_batch b;(void)s;(void)i;memset(&b,0,sizeof b);return b; }
const uint8_t *model_batch_vif(const model_section *s,const model_batch *b) { (void)s;(void)b;return NULL; }
void skel_palette_entry(float out[5][4],const mat4 *m,const float clip[4][4],const float light[3]) { (void)m;(void)clip;(void)light;memset(out,0,80); }
unsigned objects_pose(const object_t *o,const object_world_t *w,object_nodes_t *n) { (void)o;(void)w;memset(n,0,sizeof *n);n->count=1;return 1; }
unsigned objects_pose_static(const object_t *o,const object_world_t *w,object_nodes_t *n) { return objects_pose(o,w,n); }
unsigned objects_pose_model(const object_world_t *w,int m,int g,unsigned a,float f,unsigned no,const mat4 *r,object_nodes_t *n) { (void)w;(void)m;(void)g;(void)a;(void)f;(void)no;(void)r;memset(n,0,sizeof *n);return 0; }
int bsp_find_cluster(const bsp_section *b,const float p[3]) { (void)b;(void)p;return -1; }
void scen_cluster_light(const scen_section *s,uint32_t b,uint32_t c,scen_light *l) { (void)s;(void)b;(void)c;memset(l,0,sizeof *l); }
uint32_t model_batch_vif_dummy(void) { return 0; }
void clip_pack_vertex(const cvert *v,int c,const clip_gs *g,uint32_t *o) { (void)v;(void)c;(void)g;(void)o; }
int clip_polygon(const cvert in[3],float near_z,cvert out[CLIP_MAX_VERTS]) { (void)in;(void)near_z;(void)out;return 0; }
void clip_project(const float m[4][4],const float p[3],cvert *v) { (void)m;(void)p;(void)v; }

static int pose(void *u,const object_t *o,object_nodes_t *n) { (void)u; if (fail_pose) return 0; return objects_pose(o,NULL,n) != 0; }
static int run_case(int span_mode, int cached, int culled)
{
	model_section models; object_t ob; object_table_t table; obj_render_t render; camera_t cam; frustum_t fr; float clip[4][4]={{0}}; render_options_t opt; chain_t chain; render_ctx_t rc;
	memset(&models,0,sizeof models); memset(&ob,0,sizeof ob); memset(&table,0,sizeof table); memset(&render,0,sizeof render); memset(&cam,0,sizeof cam); memset(&fr,0,sizeof fr); memset(&opt,0,sizeof opt); memset(&chain,0,sizeof chain);
	cam.hfov=1.0f; cam.near_z=0.1f; ob.model=0; ob.region_count=1; ob.radius=2.0f; ob.flags=OBJ_F_VISIBLE; ob.root.m[0][0]=ob.root.m[1][1]=ob.root.m[2][2]=ob.root.m[3][3]=1.0f; ob.root.m[3][0]=5.0f; fail_pose=culled;
	table.obj[0]=ob; table.count=1; chain.base=(uint8_t *)&clip; chain.cap_qw=256;
	rc.chain=&chain;rc.cam=&cam;rc.clip=(const float (*)[4])clip;rc.frustum=&fr;rc.opt=&opt;
	render.world.models=&models;render.max_distance=culled?1.0f:1000.0f;render.max_batches=100;render.draw_objects=1;render.pose=pose;
	if(span_mode){render.span=&ob;render.span_count=1;}else render.table=&table;
	chain_calls=0; basis_calls=0;
	if(cached){obj_render_begin_view(&rc);render.setup_emitted=1;}
	obj_render_pass(&render,&rc);
	obj_render_pass(&render,&rc);
	if(render.st_visible != (culled?0u:1u) || render.st_culled != (culled?1u:0u)) { fprintf(stderr,"stats vis=%u cull=%u target=%d\n",render.st_visible,render.st_culled,culled); return 1; }
	if(chain.qw != (cached ? (culled ? 10u : 16u) : (culled ? 20u : 26u))) return 2;
	if(basis_calls != (cached ? 1u : 2u)) return 3;
	return 0;
}
int main(void)
{
	int a=run_case(0,0,0),b=run_case(1,0,0),c=run_case(0,1,0),d=run_case(1,1,0),e=run_case(1,1,1);
	if(a||b||c||d||e){fprintf(stderr,"obj_render host failure %d %d %d %d %d\n",a,b,c,d,e);return 1;}
	puts("obj_render span/table/setup behavior passed");return 0;
}
