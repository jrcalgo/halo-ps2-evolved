/* Host fixture for the source-extracted CE pathfinder over a synthetic BSP.
 * The Python test injects unchanged path-search and collision-edge functions. */
#include <assert.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define long int32_t
typedef uint8_t byte;
typedef int boolean;
typedef float real;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real x, y; } real_point2d;
typedef struct { real i, j; } real_vector2d;
struct tag_block { void *address; long count; };
struct collision_surface { long plane_designator, first_edge_index; byte flags, breakable; int16_t material; };
struct collision_edge { long vertex_indices[2], edge_indices[2], surface_indices[2]; };
struct collision_vertex { real_point3d point; long first_edge_index; };
struct collision_bsp { struct tag_block surfaces, edges, vertices; };
struct structure_bsp { struct tag_block collision_bsp, pathfinding_surfaces; };
struct path_edge { long adjacent_surface_index; byte adjacent_pathfinding_surface, pad[3]; real_point3d base_point; real_vector3d edge_vector; };
struct path_destination { real_point3d point; long surface_index; real target_radius; };
struct path_input {
	real pathfinding_radius; boolean ignore_broken_surfaces; long ignore_source_object_index;
	long ignore_target_object_index; boolean start_valid; real_point3d start_point;
	long start_surface_index; boolean attractor_valid; real_point3d attractor_point;
	long attractor_object_index; real attractor_radius, attractor_weight;
	boolean search_bounded; real search_maximum_distance;
};
struct path_node {
	int16_t child_node_index, parent_node_index; long parent_node_surface_index, surface_index;
	real_point3d entry_point; real linear_distance_to_entry_point;
	real closest_approach_to_attractor, path_distance_from_origin, cumulative_cost, total_cost_estimate;
	int16_t quantized_cost_estimate, depth, heap_location, last_render_id;
	real closest_distance_to_attractor; real_point3d closest_point_to_attractor;
};
struct path_heap_element { int16_t node_index, quantized_cost_estimate; };
struct path_debug_storage { int path_traverse_result; };
struct path_state {
	struct path_input input; struct path_debug_storage *debug; boolean destination_valid;
	struct path_destination destination; struct structure_bsp const *structure;
	int16_t closest_node_index; real closest_distance, closest_cost_estimate;
	real_point3d closest_point; int16_t node_count;
	struct path_node node_list[0x400]; int16_t heap_count;
	struct path_heap_element heap[1025]; int16_t hash_table[0x1000];
};

enum { MAXIMUM_EDGES_PER_COLLISION_SURFACE = 8, MAXIMUM_PATH_EDGES_PER_COLLISION_SURFACE = 64,
	PATH_NODE_LIST_SIZE = 0x400, PATH_HASH_KEY_MASK = 511, PATH_HASH_TABLE_MASK = 4095,
	_pathfinding_surface_walkable_bit = 6, _pathfinding_surface_breakable_bit = 7,
	_collision_surface_breakable_bit = 3, _error_silent = 0, _error_log = 1,
	_path_traverse_result_none = 0, _path_traverse_result_exhausted_search = 3,
	_path_traverse_result_never_close_enough = 2, _path_traverse_result_overflowed_nodes = 4,
	_path_traverse_result_success = 5 };
#define NONE (-1)
#define TRUE 1
#define FALSE 0
#define SHORT_MAX SHRT_MAX
#define REAL_MAX FLT_MAX
#define PATH_COST_ESTIMATE_GRANULARITY 0.1f
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define PIN(x,lo,hi) (MAX((lo), MIN((x),(hi))))
#define VALID_INDEX(i,n) ((i) >= 0 && (i) < (n))
#define TEST_FLAG(v,b) (((v) & (1u << (b))) != 0)
#define TAG_BLOCK_GET_ELEMENT(block,index,type) ((type *)((byte *)(block)->address + (index) * sizeof(type)))
#define match_assert(file,line,expr) assert(expr)
#define csmemset memset

static boolean warned_about_collision_surface_edges, warned_about_collision_surface_index;
static void error(short priority, const char *format, ...) { (void)priority; (void)format; }
static real square_root(real x) { return sqrtf(x); }
static real distance_squared3d(const real_point3d *a,const real_point3d *b) { real x=a->x-b->x,y=a->y-b->y,z=a->z-b->z; return x*x+y*y+z*z; }
static real distance3d(const real_point3d *a,const real_point3d *b) { return square_root(distance_squared3d(a,b)); }
static real magnitude_squared3d(const real_vector3d *v) { return v->i*v->i+v->j*v->j+v->k*v->k; }
static real dot_product3d(const real_vector3d *a,const real_vector3d *b) { return a->i*b->i+a->j*b->j+a->k*b->k; }
static real_vector3d *vector_from_points3d(const real_point3d *a,const real_point3d *b,real_vector3d *v) { v->i=b->x-a->x;v->j=b->y-a->y;v->k=b->z-a->z;return v; }
static real_point3d *point_from_line3d(const real_point3d *p,const real_vector3d *v,real t,real_point3d *out) { out->x=p->x+v->i*t;out->y=p->y+v->j*t;out->z=p->z+v->k*t;return out; }

/* CE_PATH_AND_COLLISION_FUNCTIONS */

static struct path_node *path_get_node(struct path_state *state, int16_t index)
{
	assert(index != NONE && index >= 0 && index < state->node_count);
	return &state->node_list[index];
}
static boolean surface_is_broken(struct structure_bsp const *structure, long surface_index)
{ (void)structure; (void)surface_index; return FALSE; }
static real path_attractor_weight(struct path_state *state, real_point3d const *a,
	real_point3d const *b, real *distance_out)
{ (void)state; (void)a; (void)b; (void)distance_out; assert(!"attractor path not part of this fixture"); return 0.0f; }
static real_point3d surface_center(struct collision_bsp const *bsp, long surface_index);
static real closest_available_point_on_surface(struct structure_bsp const *structure,
	long surface_index, real_point3d const *point, real_point3d *closest)
{
	struct collision_bsp const *bsp = TAG_BLOCK_GET_ELEMENT(
		&structure->collision_bsp, 0, struct collision_bsp);
	*closest = surface_center(bsp, surface_index);
	return distance3d(closest, point);
}

static real_point3d surface_center(struct collision_bsp const *bsp, long surface_index)
{
	struct collision_surface const *surface=TAG_BLOCK_GET_ELEMENT(&bsp->surfaces,surface_index,struct collision_surface);
	long edge_index=surface->first_edge_index; real_point3d center={0,0,0}; int count=0, n;
	for(n=0;n<MAXIMUM_EDGES_PER_COLLISION_SURFACE;n++)
	{
		struct collision_edge const *edge;
		struct collision_vertex const *v;
		boolean right;
		if(!VALID_INDEX(edge_index,bsp->edges.count)) break;
		edge=TAG_BLOCK_GET_ELEMENT(&bsp->edges,edge_index,struct collision_edge);
		if(!VALID_INDEX(edge->vertex_indices[0],bsp->vertices.count) || !VALID_INDEX(edge->vertex_indices[1],bsp->vertices.count)) break;
		v=TAG_BLOCK_GET_ELEMENT(&bsp->vertices,edge->vertex_indices[0],struct collision_vertex);
		center.x+=v->point.x; center.y+=v->point.y; center.z+=v->point.z; count++;
		right=(surface_index==edge->surface_indices[1]); edge_index=edge->edge_indices[right];
		if(edge_index==surface->first_edge_index) break;
	}
	assert(count>=3); center.x/=count; center.y/=count; center.z/=count; return center;
}

static void run_search(int middle_walkable, struct structure_bsp *structure,
	struct path_state *state, struct collision_bsp *collision,
	struct collision_surface surfaces[3], struct collision_edge edges[10],
	struct collision_vertex vertices[8], byte path_flags[3])
{
	static const real_point3d points[8] = {
		{0,0,0},{10,0,0},{10,10,0},{0,10,0},
		{20,0,0},{20,10,0},{30,0,0},{30,10,0}
	};
	static const int32_t edge_vertices[10][2] = {
		{0,1},{1,2},{2,3},{3,0},{1,4},{4,5},{5,2},{4,6},{6,7},{7,5}
	};
	int i;
	memset(surfaces, 0, sizeof(struct collision_surface)*3);
	memset(edges, 0, sizeof(struct collision_edge)*10);
	for (i=0;i<8;i++) vertices[i].point=points[i];
	for (i=0;i<10;i++) { edges[i].vertex_indices[0]=edge_vertices[i][0]; edges[i].vertex_indices[1]=edge_vertices[i][1]; edges[i].surface_indices[0]=NONE; edges[i].surface_indices[1]=NONE; }
	/* Tile 0 ring: e0,e1(shared 0/1),e2,e3. */
	surfaces[0].first_edge_index=0;
	edges[0].surface_indices[0]=0; edges[0].surface_indices[1]=0; edges[0].edge_indices[1]=1;
	edges[1].surface_indices[0]=0; edges[1].surface_indices[1]=1; edges[1].edge_indices[0]=2;
	edges[2].surface_indices[0]=0; edges[2].surface_indices[1]=0; edges[2].edge_indices[1]=3;
	edges[3].surface_indices[0]=0; edges[3].surface_indices[1]=0; edges[3].edge_indices[1]=0;
	/* Tile 1 ring: shared e1,e4,e6,e5(shared 1/2). */
	surfaces[1].first_edge_index=1;
	edges[1].edge_indices[1]=4; edges[4].surface_indices[0]=1; edges[4].edge_indices[0]=6;
	edges[4].surface_indices[1]=1; edges[4].edge_indices[1]=6;
	edges[6].surface_indices[0]=1; edges[6].surface_indices[1]=1; edges[6].edge_indices[1]=5;
	edges[5].surface_indices[0]=1; edges[5].surface_indices[1]=2; edges[5].edge_indices[0]=1;
	/* Tile 2 ring: shared e5,e7,e8,e9. */
	surfaces[2].first_edge_index=5;
	edges[5].edge_indices[1]=7; edges[7].surface_indices[0]=2; edges[7].surface_indices[1]=2; edges[7].edge_indices[1]=8;
	edges[8].surface_indices[0]=2; edges[8].surface_indices[1]=2; edges[8].edge_indices[1]=9;
	edges[9].surface_indices[0]=2; edges[9].surface_indices[1]=2; edges[9].edge_indices[1]=5;
	for (i=0;i<3;i++) { path_flags[i]=(byte)(1u<<_pathfinding_surface_walkable_bit); }
	if (!middle_walkable) path_flags[1]=0;
	collision->surfaces.address=surfaces; collision->surfaces.count=3;
	collision->edges.address=edges; collision->edges.count=10;
	collision->vertices.address=vertices; collision->vertices.count=8;
	structure->collision_bsp.address=collision; structure->collision_bsp.count=1;
	structure->pathfinding_surfaces.address=path_flags; structure->pathfinding_surfaces.count=3;
	memset(state,0,sizeof(*state));
	state->structure=structure; state->input.pathfinding_radius=0.5f;
	state->input.start_valid=TRUE; state->input.start_point=(real_point3d){5,5,0};
	state->input.start_surface_index=0;
	state->destination_valid=TRUE; state->destination.point=(real_point3d){29,5,0};
	state->destination.surface_index=2; state->destination.target_radius=0.0f;
	path_state_reset(state);
	assert(path_state_begin(state));
	assert(path_state_traverse(state) == middle_walkable);
}

static int run_retail_route(const char *filename, long start_surface, long goal_surface)
{
	FILE *input=fopen(filename,"rb");
	uint32_t counts[4];
	struct structure_bsp structure; struct collision_bsp collision;
	struct collision_surface *surfaces;
	struct collision_edge *edges;
	struct collision_vertex *vertices;
	byte *flags;
	struct path_state state;
	real_point3d start_point,goal_point;
	int result;
	if(!input || fread(counts,sizeof(counts),1,input)!=1) return 10;
	if(counts[0]==0 || counts[0]>100000 || counts[1]>1000000 || counts[2]>1000000 || counts[3]!=counts[0]) return 11;
	surfaces=calloc(counts[0],sizeof(*surfaces)); edges=calloc(counts[1],sizeof(*edges));
	vertices=calloc(counts[2],sizeof(*vertices)); flags=calloc(counts[3],1);
	if(!surfaces || !edges || !vertices || !flags) return 12;
	if(fread(surfaces,sizeof(*surfaces),counts[0],input)!=counts[0] ||
		fread(edges,sizeof(*edges),counts[1],input)!=counts[1] ||
		fread(vertices,sizeof(*vertices),counts[2],input)!=counts[2] ||
		fread(flags,1,counts[3],input)!=counts[3]) return 13;
	fclose(input);
	collision.surfaces.address=surfaces; collision.surfaces.count=(long)counts[0];
	collision.edges.address=edges; collision.edges.count=(long)counts[1];
	collision.vertices.address=vertices; collision.vertices.count=(long)counts[2];
	structure.collision_bsp.address=&collision; structure.collision_bsp.count=1;
	structure.pathfinding_surfaces.address=flags; structure.pathfinding_surfaces.count=(long)counts[3];
	assert(VALID_INDEX(start_surface,(long)counts[0]) && VALID_INDEX(goal_surface,(long)counts[0]));
	assert(TEST_FLAG(flags[start_surface],_pathfinding_surface_walkable_bit));
	assert(TEST_FLAG(flags[goal_surface],_pathfinding_surface_walkable_bit));
	start_point=surface_center(&collision,start_surface); goal_point=surface_center(&collision,goal_surface);
	memset(&state,0,sizeof(state)); state.structure=&structure;
	state.input.pathfinding_radius=0.5f; state.input.start_valid=TRUE;
	state.input.start_point=start_point; state.input.start_surface_index=start_surface;
	state.destination_valid=TRUE; state.destination.point=goal_point;
	state.destination.surface_index=goal_surface; state.destination.target_radius=0.0f;
	path_state_reset(&state);
	assert(path_state_begin(&state)); result=path_state_traverse(&state);
	if (!result || state.closest_node_index < 0 ||
		state.node_list[state.closest_node_index].surface_index != goal_surface) {
		fprintf(stderr, "retail route diagnostic start=%d goal=%d result=%d closest=%d depth=%d nodes=%d distance=%f\n",
			(int)start_surface, (int)goal_surface, result,
			state.closest_node_index >= 0 ? (int)state.node_list[state.closest_node_index].surface_index : -1,
			state.closest_node_index >= 0 ? (int)state.node_list[state.closest_node_index].depth : -1,
			(int)state.node_count, state.closest_distance);
	}
	assert(result && state.closest_node_index>=0);
	assert(state.node_list[state.closest_node_index].surface_index==goal_surface);
	{
		int16_t node = state.closest_node_index;
		int guard = 0;
		printf("ce-bot-path retail_bsp start=%d goal=%d depth=%d discovered=%d path=",
		(int)start_surface,(int)goal_surface,
		(int)state.node_list[state.closest_node_index].depth,(int)state.node_count);
		while (node != NONE && guard++ <= state.node_count) {
			printf("%s%d", guard == 1 ? "" : ",",
				(int)state.node_list[node].surface_index);
			node = state.node_list[node].parent_node_index;
		}
		assert(guard <= state.node_count + 1);
		printf(" result=passed\n");
	}
	free(flags); free(vertices); free(edges); free(surfaces);
	return 0;
}

int main(int argc, char **argv)
{
	struct structure_bsp structure; struct collision_bsp collision;
	struct collision_surface surfaces[3]; struct collision_edge edges[10];
	struct collision_vertex vertices[8]; byte flags[3]; struct path_state state;
	if (argc == 4)
		return run_retail_route(argv[1],(long)atoi(argv[2]),(long)atoi(argv[3]));
	if (argc != 1) return 2;
	run_search(TRUE,&structure,&state,&collision,surfaces,edges,vertices,flags);
	assert(state.closest_node_index>=0);
	assert(state.node_list[state.closest_node_index].surface_index==2);
	assert(state.node_list[state.closest_node_index].parent_node_surface_index==1);
	assert(state.closest_distance==0.0f);
	printf("ce-bot-path synthetic_walkable nodes=%d target_surface=%d parent=%d result=passed\n",
		state.node_count,state.node_list[state.closest_node_index].surface_index,
		state.node_list[state.closest_node_index].parent_node_surface_index);
	run_search(FALSE,&structure,&state,&collision,surfaces,edges,vertices,flags);
	assert(state.closest_node_index==0 && state.closest_distance>0.0f);
	printf("ce-bot-path synthetic_blocked nodes=%d target_unreached=1 result=passed\n",state.node_count);
	return 0;
}
#undef long
