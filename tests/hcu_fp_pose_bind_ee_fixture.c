/* Exercises the production pose_fn by including the EE adapter directly. The synthetic
 * MODL node records and palettes are asset-free; only model accessors are stubbed. */
#define HCU_RENDER_OBJECTS_EE 1
#define HCU_C3_OBJECT_PREPARE_CACHE 0
#include <stdio.h>
#include <stdlib.h>
#include "stream/hcu_render_objects.c"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s line %d\n", #x, __LINE__); return 1; } } while (0)

static model_node s_test_nodes[3];
model_info model_get(const model_section *s, uint32_t index)
{
	model_info m; (void)s; (void)index; memset(&m, 0, sizeof m); m.node_count = 3; return m;
}
model_node model_get_node(const model_section *s, const model_info *m, uint32_t node)
{
	(void)s; (void)m; return s_test_nodes[node];
}
void model_select_permutations(const model_section *s, const model_info *m, const char *variant, uint16_t *out)
{
	uint32_t i; (void)s; (void)variant; for (i=0;i<m->region_count;i++) out[i]=0;
}

static float max_delta(const mat4 *a, const mat4 *b)
{
	float d=0; unsigned i,j; for(i=0;i<4;i++)for(j=0;j<4;j++)if(fabsf(a->m[i][j]-b->m[i][j])>d)d=fabsf(a->m[i][j]-b->m[i][j]); return d;
}
static void identity_quat(float q[4]) { q[0]=q[1]=q[2]=0.0f; q[3]=1.0f; }
static void make_camera(halo_ps2_snapshot_camera *c, float x, float yaw, float pitch)
{
	float cp=cosf(pitch),sp=sinf(pitch),cy=cosf(yaw),sy=sinf(yaw);
	memset(c,0,sizeof *c); c->position[0]=x;c->position[1]=-3.0f*x;c->position[2]=1.0f+x*0.1f;
	c->forward[0]=cp*cy;c->forward[1]=cp*sy;c->forward[2]=sp;
	c->up[0]=-sp*cy;c->up[1]=-sp*sy;c->up[2]=cp;
}
static void write_snapshot_matrix(const mat4 *m, halo_ps2_snapshot_matrix4x3 *out)
{
	unsigned i,j; out->scale=1.0f;
	for(i=0;i<3;i++)for(j=0;j<3;j++){
		float x=m->m[i][j]; if(i==0)out->forward[j]=x;else if(i==1)out->left[j]=x;else out->up[j]=x;
	}
	for(j=0;j<3;j++)out->position[j]=m->m[3][j];
}
static void make_palettes(halo_ps2_frame_snapshot *snap, unsigned view, int animated)
{
	skel_xform local[3]; int16_t parent[3]={-1,0,1}; mat4 root,world[3]; unsigned i;
	for(i=0;i<3;i++){
		memcpy(local[i].rot,s_test_nodes[i].rotation,sizeof local[i].rot);
		memcpy(local[i].trans,s_test_nodes[i].translation,sizeof local[i].trans);
		local[i].scale=s_test_nodes[i].scale;
	}
	if(animated){
		/* Change two local rotations while retaining authored bind translations. */
		local[1].rot[2]=0.38268343f;local[1].rot[3]=0.92387953f;
		local[2].rot[0]=0.25881904f;local[2].rot[3]=0.96592583f;
	}
	{
		float q[4]={0,0,0,1},t[3]={0.17f+view*0.03f,-0.04f,0.02f};mat4_from_trs(&root,q,t,1.0f);
	}
	if(skel_world(world,local,parent,3,&root))abort();
	snap->views[view].first_person_weapon_palette_first=(uint16_t)(view*3u);
	snap->views[view].first_person_weapon_palette_count=3;
	for(i=0;i<3;i++)write_snapshot_matrix(&world[i],&snap->palette[view*3u+i]);
}
static int call_pose(halo_ps2_frame_snapshot *snap, unsigned view, uint16_t flags,
	object_nodes_t *out, mat4 source_world[3])
{
	hcu_render_object_draw d; object_t ob; unsigned i;
	memset(&d,0,sizeof d);memset(&ob,0,sizeof ob);d.slot=0;d.flags=flags;
	d.palette_first=snap->views[view].first_person_weapon_palette_first;d.palette_count=3;
	s_pose_snapshot=snap;s_fp_cam=&snap->views[view].camera;
	if(pose_fn(&d,&ob,out)!=1)return -1;
	for(i=0;i<3;i++){
		halo_ps2_snapshot_matrix4x3 composed;
		const halo_ps2_snapshot_matrix4x3 *src=&snap->palette[d.palette_first+i];
		if(flags&HCU_OBJECTS_FLAG_CAMERA_LOCAL){if(hcu_render_first_person_world(&snap->views[view].camera,src,&composed))return -2;source_world[i]=mat_from_snapshot(&composed);}
		else source_world[i]=mat_from_snapshot(src);
	}
	return 0;
}
static int check_default_skin(unsigned view, const mat4 world[3], const object_nodes_t *out)
{
	skel_xform bind[3];int16_t parent[3]={-1,0,1};mat4 def[3],inv,expected,identity;unsigned i;
	for(i=0;i<3;i++){memcpy(bind[i].rot,s_test_nodes[i].rotation,sizeof bind[i].rot);memcpy(bind[i].trans,s_test_nodes[i].translation,sizeof bind[i].trans);bind[i].scale=s_test_nodes[i].scale;}
	mat4_identity(&identity);if(skel_world(def,bind,parent,3,&identity))return -1;
	for(i=0;i<3;i++){
		mat4_rigid_inverse(&inv,&def[i]);mat4_mul(&expected,&inv,&world[i]);
		if(max_delta(&out->world[i],&world[i])>1e-5f||max_delta(&out->skin[i],&expected)>1e-5f)return -2;
	}
	(void)view;return 0;
}

int main(void)
{
	static halo_ps2_frame_snapshot snap, before;
	static object_nodes_t out;
	mat4 expected_world[3], prior_roots[4]; unsigned i,v; float maxpose=0;
	memset(s_test_nodes,0,sizeof s_test_nodes);
	memcpy(s_test_nodes[0].name,"root",5);s_test_nodes[0].parent=-1;s_test_nodes[0].translation[0]=0.10f;s_test_nodes[0].translation[2]=0.20f;identity_quat(s_test_nodes[0].rotation);s_test_nodes[0].scale=1;
	memcpy(s_test_nodes[1].name,"arm",4);s_test_nodes[1].parent=0;s_test_nodes[1].translation[0]=0.31f;s_test_nodes[1].rotation[2]=0.25881904f;s_test_nodes[1].rotation[3]=0.96592583f;s_test_nodes[1].scale=1;
	memcpy(s_test_nodes[2].name,"hand",5);s_test_nodes[2].parent=1;s_test_nodes[2].translation[1]=0.27f;s_test_nodes[2].rotation[1]=0.13052619f;s_test_nodes[2].rotation[3]=0.99144486f;s_test_nodes[2].scale=1;
	s_slots[0].loaded=1;
	for(v=0;v<4;v++){
		make_camera(&snap.views[v].camera,1.0f+v*2.0f,-0.8f+v*0.53f,-0.31f+v*0.19f);
		make_palettes(&snap,v,1);
	}
	snap.version=HALO_PS2_FRAME_SNAPSHOT_VERSION;snap.view_count=4;snap.palette_count=12;
	memcpy(&before,&snap,sizeof snap);
	for(v=0;v<4;v++){
		CHECK(call_pose(&snap,v,HCU_OBJECTS_FLAG_SKINNED|HCU_OBJECTS_FLAG_CAMERA_LOCAL,&out,expected_world)==0);
		CHECK(out.count==3);CHECK(check_default_skin(v,expected_world,&out)==0);
		if(v>0)CHECK(max_delta(&prior_roots[0],&out.world[0])>0.01f);
		prior_roots[0]=out.world[0];
		for(i=0;i<3;i++){float d=max_delta(&out.world[i],&out.skin[i]);if(d>maxpose)maxpose=d;}
	}
	CHECK(maxpose>0.1f); /* nonidentity bind / animated node data reached actual callback */
	CHECK(memcmp(&before,&snap,sizeof snap)==0); /* all four source/player palettes remained immutable */
	/* Identity/default pose must cancel each node's own bind transform, leaving only camera root. */
	make_palettes(&snap,0,0);
	CHECK(call_pose(&snap,0,HCU_OBJECTS_FLAG_SKINNED|HCU_OBJECTS_FLAG_CAMERA_LOCAL,&out,expected_world)==0);
	{
		halo_ps2_snapshot_matrix4x3 graph_root,cam;mat4 root_local,camera_root;float q[4]={0,0,0,1},t[3]={0.17f,-0.04f,0.02f};
		mat4_from_trs(&root_local,q,t,1.0f);write_snapshot_matrix(&root_local,&graph_root);
		CHECK(hcu_render_first_person_world(&snap.views[0].camera,&graph_root,&cam)==0);camera_root=mat_from_snapshot(&cam);
		for(i=0;i<3;i++)CHECK(max_delta(&out.skin[i],&camera_root)<5e-5f);
	}
	/* World-object palettes without CAMERA_LOCAL keep their prior direct skin contract. */
	{
		mat4 direct[3];
		for(i=0;i<3;i++){snap.palette[i].position[0]=8.0f+i;snap.palette[i].position[1]=2.0f-i;}
		CHECK(call_pose(&snap,0,HCU_OBJECTS_FLAG_SKINNED,&out,direct)==0);
		for(i=0;i<3;i++)CHECK(max_delta(&out.skin[i],&direct[i])<1e-6f&&max_delta(&out.world[i],&direct[i])<1e-6f);
	}
	puts("hcu FP inverse-bind production pose_fn fixture passed (3-node hierarchy, 4 views, yaw/pitch, identity, world path)");
	return 0;
}
