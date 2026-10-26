/* C4 item 3 host fixture: live-unit pathfinding over a synthetic quad-grid BSP.
 * CE path search, heap, edge builder, surface_is_broken and collision ring helpers are
 * extracted unchanged from source by tests/test_c4_live_pathfinding.py and compiled in at
 * the CE_PATH_FUNCTIONS marker. Seams (documented in docs/reports/m4-c4-live-pathfinding-2026-10-26.md):
 *   - breakable_surface_flags_get(): a host bit vector standing in for the breakable_surfaces globals.
 *   - closest_available_point_on_surface(): AABB clamp (CE's version needs the collision projection).
 *   - unit movement/stall/replan loop: transcription of actor_moving.c:2122-2190 step advance.
 * Output lines are compared bit-for-bit between the native and -m32 builds. */
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
struct collision_surface { long plane_designator, first_edge_index; byte flags, breakable_surface_index; int16_t material; };
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
	LONG_BITS = 32, LONG_BITS_BITS = 5,
	_path_traverse_result_none = 0, _path_traverse_result_exhausted_search = 3,
	_path_traverse_result_never_close_enough = 2, _path_traverse_result_overflowed_nodes = 4,
	_path_traverse_result_success = 5 };
#define csmemset memset
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
#define SET_FLAG(f,b,v) ((v) ? ((f) |= (1u << (b))) : ((f) &= ~(1u << (b))))
#define BIT_VECTOR_TEST_FLAG(bit_vector, bit) (TEST_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1))))
#define BIT_VECTOR_SET_FLAG(bit_vector, bit, enable) (SET_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1)), enable))
#define TAG_BLOCK_GET_ELEMENT(block,index,type) ((type *)((byte *)(block)->address + (index) * sizeof(type)))
#define match_assert(file,line,expr) assert(expr)
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)

#define GRID_NX 5
#define GRID_NY 3
#define GRID_SURFACES (GRID_NX * GRID_NY)
#define GRID_EDGES (GRID_NX * (GRID_NY + 1) + (GRID_NX + 1) * GRID_NY)
#define GRID_VERTICES ((GRID_NX + 1) * (GRID_NY + 1))
#define CELL 10.0f
#define GATE_SURFACE 7      /* cell (2,1): breakable gate, breakable index 0 */
#define GATE_INDEX 0
#define CONTROL_SURFACE 13  /* cell (3,2): breakable, breakable index 1, off the route */
#define CONTROL_INDEX 1
#define START_SURFACE 5     /* cell (0,1) */
#define GOAL_SURFACE 9      /* cell (4,1) */
#define MAX_TICKS 400
#define STALL_TICKS 30
#define UNIT_SPEED 0.5f

static boolean warned_about_collision_surface_edges, warned_about_collision_surface_index;
static void error(short priority, const char *format, ...) { (void)priority; (void)format; }
static real square_root(real x) { return sqrtf(x); }
static real distance_squared3d(const real_point3d *a,const real_point3d *b) { real x=a->x-b->x,y=a->y-b->y,z=a->z-b->z; return x*x+y*y+z*z; }
static real distance3d(const real_point3d *a,const real_point3d *b) { return square_root(distance_squared3d(a,b)); }
static real magnitude_squared3d(const real_vector3d *v) { return v->i*v->i+v->j*v->j+v->k*v->k; }
static real dot_product3d(const real_vector3d *a,const real_vector3d *b) { return a->i*b->i+a->j*b->j+a->k*b->k; }
static real_vector3d *vector_from_points3d(const real_point3d *a,const real_point3d *b,real_vector3d *v) { v->i=b->x-a->x;v->j=b->y-a->y;v->k=b->z-a->z;return v; }
static real_point3d *point_from_line3d(const real_point3d *p,const real_vector3d *v,real t,real_point3d *out) { out->x=p->x+v->i*t;out->y=p->y+v->j*t;out->z=p->z+v->k*t;return out; }

/* ---- breakable bit vector: the host stand-in for physics/breakable_surfaces.c globals ---- */
static long g_breakable_bits[8];   /* 256 breakable indices */
byte *breakable_surface_flags_get(void) { return (byte *)g_breakable_bits; }

/* ---- synthetic grid BSP ---- */
static struct collision_surface g_surfaces[GRID_SURFACES];
static struct collision_edge g_edges[GRID_EDGES];
static struct collision_vertex g_vertices[GRID_VERTICES];
static byte g_path_flags[GRID_SURFACES];
static struct collision_bsp g_collision;
static struct structure_bsp g_structure;

static long vertex_id(int i, int j) { return j * (GRID_NX + 1) + i; }
static long horizontal_edge_id(int i, int j) { return j * GRID_NX + i; }
static long vertical_edge_id(int i, int j) { return GRID_NX * (GRID_NY + 1) + j * (GRID_NX + 1) + i; }
static void cell_edges(int s, long e[4])
{
	int i = s % GRID_NX, j = s / GRID_NX;
	e[0] = horizontal_edge_id(i, j);
	e[1] = vertical_edge_id(i + 1, j);
	e[2] = horizontal_edge_id(i, j + 1);
	e[3] = vertical_edge_id(i, j);
}
static void grid_build(void)
{
	int i, j, s, k;
	memset(g_surfaces, 0, sizeof g_surfaces);
	memset(g_edges, 0, sizeof g_edges);
	memset(g_vertices, 0, sizeof g_vertices);
	for (j = 0; j <= GRID_NY; j++)
		for (i = 0; i <= GRID_NX; i++) {
			g_vertices[vertex_id(i, j)].point.x = CELL * i;
			g_vertices[vertex_id(i, j)].point.y = CELL * j;
		}
	for (j = 0; j <= GRID_NY; j++)
		for (i = 0; i < GRID_NX; i++) {
			struct collision_edge *e = &g_edges[horizontal_edge_id(i, j)];
			e->vertex_indices[0] = vertex_id(i, j); e->vertex_indices[1] = vertex_id(i + 1, j);
			e->surface_indices[0] = NONE; e->surface_indices[1] = NONE;
			e->edge_indices[0] = NONE; e->edge_indices[1] = NONE;
		}
	for (j = 0; j < GRID_NY; j++)
		for (i = 0; i <= GRID_NX; i++) {
			struct collision_edge *e = &g_edges[vertical_edge_id(i, j)];
			e->vertex_indices[0] = vertex_id(i, j); e->vertex_indices[1] = vertex_id(i, j + 1);
			e->surface_indices[0] = NONE; e->surface_indices[1] = NONE;
			e->edge_indices[0] = NONE; e->edge_indices[1] = NONE;
		}
	for (s = 0; s < GRID_SURFACES; s++) {
		long e[4];
		cell_edges(s, e);
		for (k = 0; k < 4; k++) {
			struct collision_edge *edge = &g_edges[e[k]];
			if (edge->surface_indices[0] == NONE) edge->surface_indices[0] = s;
			else edge->surface_indices[1] = s;
		}
	}
	for (s = 0; s < GRID_SURFACES; s++) {
		long e[4];
		cell_edges(s, e);
		for (k = 0; k < 4; k++) {
			/* ring successor for this surface; slot follows CE's ring walk (right = surface == surface_indices[1]) */
			struct collision_edge *edge = &g_edges[e[k]];
			int slot = (edge->surface_indices[1] == s);
			edge->edge_indices[slot] = e[(k + 1) % 4];
		}
		g_surfaces[s].first_edge_index = e[0];
		g_path_flags[s] = (byte)(1u << _pathfinding_surface_walkable_bit);
	}
	(void)i; (void)j;
	g_collision.surfaces.address = g_surfaces; g_collision.surfaces.count = GRID_SURFACES;
	g_collision.edges.address = g_edges; g_collision.edges.count = GRID_EDGES;
	g_collision.vertices.address = g_vertices; g_collision.vertices.count = GRID_VERTICES;
	g_structure.collision_bsp.address = &g_collision; g_structure.collision_bsp.count = 1;
	g_structure.pathfinding_surfaces.address = g_path_flags; g_structure.pathfinding_surfaces.count = GRID_SURFACES;
}
static void make_breakable(int s, int index)
{
	g_path_flags[s] |= (byte)(1u << _pathfinding_surface_breakable_bit);
	g_surfaces[s].flags |= (byte)(1u << _collision_surface_breakable_bit);
	g_surfaces[s].breakable_surface_index = (byte)index;
}
static void scenario_reset(void)
{
	grid_build();
	make_breakable(GATE_SURFACE, GATE_INDEX);
	make_breakable(CONTROL_SURFACE, CONTROL_INDEX);
	/* wall: (2,2) non-walkable; gate (2,1) is breakable; (2,0) is the open detour cell */
	g_path_flags[12] = 0;
	memset(g_breakable_bits, 0xFF, sizeof g_breakable_bits);
}

/* CE_PATH_FUNCTIONS */

/* ---- CE closest-point seam: AABB clamp of the grid cell ---- */
static int g_retail_mode;
static real_point3d ring_center(long surface_index)
{
	struct collision_surface const *surface = TAG_BLOCK_GET_ELEMENT(&g_collision.surfaces, surface_index, struct collision_surface);
	long edge_index = surface->first_edge_index;
	real_point3d center = {0, 0, 0};
	int count = 0, n;
	for (n = 0; n < MAXIMUM_EDGES_PER_COLLISION_SURFACE; n++) {
		struct collision_edge const *edge;
		struct collision_vertex const *v;
		boolean right;
		if (!VALID_INDEX(edge_index, g_collision.edges.count)) break;
		edge = TAG_BLOCK_GET_ELEMENT(&g_collision.edges, edge_index, struct collision_edge);
		if (!VALID_INDEX(edge->vertex_indices[0], g_collision.vertices.count) || !VALID_INDEX(edge->vertex_indices[1], g_collision.vertices.count)) break;
		v = TAG_BLOCK_GET_ELEMENT(&g_collision.vertices, edge->vertex_indices[0], struct collision_vertex);
		center.x += v->point.x; center.y += v->point.y; center.z += v->point.z; count++;
		right = (surface_index == edge->surface_indices[1]);
		edge_index = edge->edge_indices[right];
		if (edge_index == surface->first_edge_index) break;
	}
	assert(count >= 3);
	center.x /= count; center.y /= count; center.z /= count;
	return center;
}
static real closest_available_point_on_surface(struct structure_bsp const *structure,
	long surface_index, real_point3d const *point, real_point3d *closest)
{
	int i, j;
	(void)structure;
	if (g_retail_mode) {
		*closest = ring_center(surface_index);
		return distance3d(closest, point);
	}
	i = surface_index % GRID_NX; j = surface_index / GRID_NX;
	closest->x = PIN(point->x, CELL * i, CELL * (i + 1));
	closest->y = PIN(point->y, CELL * j, CELL * (j + 1));
	closest->z = 0.0f;
	return distance3d(closest, point);
}
static real path_attractor_weight(struct path_state *state, real_point3d const *a,
	real_point3d const *b, real *distance_out)
{ (void)state; (void)a; (void)b; (void)distance_out; assert(!"attractor path not part of this fixture"); return 0.0f; }
static struct path_node *path_get_node(struct path_state *state, int16_t index)
{
	assert(index != NONE && index >= 0 && index < state->node_count);
	return &state->node_list[index];
}

/* ---- planning and unit model ---- */
struct route {
	int count;
	long surfaces[GRID_SURFACES];
	real_point3d points[GRID_SURFACES];   /* step point per depth, as build_path_... raw_steps assigns */
	real cost[GRID_SURFACES];
};
static struct path_state g_path;

static int plan_route(long start_surface, real_point3d start, long goal_surface, real_point3d goal, struct route *out)
{
	int16_t node;
	int d;
	memset(&g_path, 0, sizeof g_path);
	g_path.structure = &g_structure;
	g_path.input.pathfinding_radius = 0.5f;
	g_path.input.start_valid = TRUE;
	g_path.input.start_point = start;
	g_path.input.start_surface_index = start_surface;
	g_path.destination_valid = TRUE;
	g_path.destination.point = goal;
	g_path.destination.surface_index = goal_surface;
	g_path.destination.target_radius = 0.0f;
	path_state_reset(&g_path);
	if (!path_state_begin(&g_path)) return -1;
	if (!path_state_traverse(&g_path)) return -1;
	node = g_path.closest_node_index;
	if (node < 0 || g_path.node_list[node].surface_index != goal_surface) return -1;
	out->count = g_path.node_list[node].depth + 1;
	for (; node != NONE; node = g_path.node_list[node].parent_node_index) {
		d = g_path.node_list[node].depth;
		out->surfaces[d] = g_path.node_list[node].surface_index;
		out->cost[d] = g_path.node_list[node].cumulative_cost;
		out->points[d] = g_path.node_list[node].entry_point;   /* replaced below for d < count-1 */
	}
	for (d = 0; d < out->count - 1; d++) out->points[d] = out->points[d + 1];
	out->points[out->count - 1] = goal;
	return out->count;
}
static int route_contains(const struct route *r, long s)
{
	int k;
	for (k = 0; k < r->count; k++) if (r->surfaces[k] == s) return 1;
	return 0;
}
static void route_print(const char *label, const struct route *r)
{
	int k;
	printf("c4-live-path %s route=", label);
	for (k = 0; k < r->count; k++) printf("%s%d", k ? "," : "", (int)r->surfaces[k]);
	printf(" cost=%.4f", (double)r->cost[r->count - 1]);
	printf(" depth=%d", r->count - 1);
	printf("\n");
}
static void route_check_invariants(const char *label, const struct route *r, long start)
{
	int k;
	CHECK(r->count >= 2);
	CHECK(r->surfaces[0] == start);
	CHECK(r->surfaces[r->count - 1] == GOAL_SURFACE);
	for (k = 0; k < r->count; k++) {
		long s = r->surfaces[k];
		CHECK(TEST_FLAG(g_path_flags[s], _pathfinding_surface_walkable_bit));
		CHECK(!surface_is_broken(&g_structure, s));
		if (k > 0) {
			int ai = r->surfaces[k - 1] % GRID_NX, aj = r->surfaces[k - 1] / GRID_NX;
			int bi = s % GRID_NX, bj = s / GRID_NX;
			CHECK(abs(ai - bi) + abs(aj - bj) == 1);   /* consecutive surfaces share a collision edge */
			CHECK(r->cost[k] >= r->cost[k - 1]);       /* monotone cumulative cost */
		}
	}
	printf("c4-live-path %s invariants=adjacent,walkable,unbroken,monotone_cost result=passed\n", label);
}

/* Unit advance: transcription of actor_moving.c:2143-2170 (non-thwarted branch). */
struct unit { real_point3d pos; int step; };
static int unit_cell(real_point3d p)
{
	int i = (int)floorf(p.x / CELL), j = (int)floorf(p.y / CELL);
	if (i < 0 || j < 0 || i >= GRID_NX || j >= GRID_NY) return NONE;
	return j * GRID_NX + i;
}
/* A point is on a valid surface when it lies in the cell's box (with epsilon) of a route surface. */
static int unit_on_route(const struct route *r, real_point3d p)
{
	int k;
	for (k = 0; k < r->count; k++) {
		int s = (int)r->surfaces[k], i = s % GRID_NX, j = s / GRID_NX;
		if (p.x >= CELL * i - 0.01f && p.x <= CELL * (i + 1) + 0.01f &&
			p.y >= CELL * j - 0.01f && p.y <= CELL * (j + 1) + 0.01f) return 1;
	}
	return 0;
}
/* Returns 1 when the unit has reached the final step. Does not move when held. */
static int unit_tick(struct unit *u, const struct route *r, int held)
{
	real_point3d target;
	real dx, dy, len;
	while (u->step + 1 < r->count) {
		real_point3d const *sp = &r->points[u->step];
		real ddx = sp->x - u->pos.x, ddy = sp->y - u->pos.y;
		if (ddx * ddx + ddy * ddy < 0.15f * 0.15f) u->step++;
		else break;
	}
	{
		real_point3d const *g = &r->points[r->count - 1];
		real gx = g->x - u->pos.x, gy = g->y - u->pos.y;
		if (u->step + 1 == r->count && gx * gx + gy * gy < 0.15f * 0.15f) return 1;
	}
	if (held) return 0;
	target = r->points[u->step];
	dx = target.x - u->pos.x; dy = target.y - u->pos.y;
	len = sqrtf(dx * dx + dy * dy);
	if (len > 0.0f) {
		real move = len < UNIT_SPEED ? len : UNIT_SPEED;
		u->pos.x += dx / len * move;
		u->pos.y += dy / len * move;
	}
	return 0;
}
static real_point3d point_xy(real x, real y) { real_point3d p; p.x = x; p.y = y; p.z = 0.0f; return p; }
static real_point3d cell_center(int s) { return point_xy(CELL * (s % GRID_NX) + 5.0f, CELL * (s / GRID_NX) + 5.0f); }

/* breakable_surface_port_break analogue (physics/breakable_surfaces.c:330) */
static void destroy_breakable(long index) { BIT_VECTOR_SET_FLAG(g_breakable_bits, index, FALSE); }

/* ---- scenarios ---- */
static void scenario_surface_selection(void)
{
	struct route r;
	real_point3d gate = cell_center(GATE_SURFACE);
	scenario_reset();
	CHECK(plan_route(NONE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) < 0);
	printf("c4-live-path surface_selection.none_start rejected=1 result=passed\n");
	{
		struct path_state s; real_point3d below = cell_center(START_SURFACE);
		below.z = -2000.0f;
		memset(&s, 0, sizeof s);
		s.structure = &g_structure; s.input.start_valid = TRUE; s.input.start_point = below;
		s.input.start_surface_index = START_SURFACE; s.input.pathfinding_radius = 0.5f;
		s.destination_valid = TRUE; s.destination.point = cell_center(GOAL_SURFACE); s.destination.surface_index = GOAL_SURFACE;
		path_state_reset(&s);
		CHECK(!path_state_begin(&s));
	}
	printf("c4-live-path surface_selection.below_world rejected=1 result=passed\n");
	/* mover standing on the breakable gate, gate intact */
	CHECK(plan_route(GATE_SURFACE, gate, GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	route_print("surface_selection.gate_start_intact", &r);
	/* same mover after the gate is destroyed: begin does not test the start surface (CE checks neighbours only) */
	destroy_breakable(GATE_INDEX);
	CHECK(surface_is_broken(&g_structure, GATE_SURFACE));
	CHECK(plan_route(GATE_SURFACE, gate, GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	route_print("surface_selection.gate_start_broken", &r);
	CHECK(r.count == 3 && r.surfaces[1] == 8);
	printf("c4-live-path surface_selection.gate_start_broken start_not_tested=1 result=passed\n");
}

static void sample_segment_on_route(const struct route *r, real_point3d a, real_point3d b)
{
	int k;
	for (k = 0; k <= 20; k++) {
		real_point3d p;
		real t = (real)k / 20.0f;
		p.x = a.x + (b.x - a.x) * t; p.y = a.y + (b.y - a.y) * t; p.z = 0.0f;
		CHECK(unit_on_route(r, p));
	}
}
static void scenario_path_construction(void)
{
	struct route r;
	real_point3d prev = cell_center(START_SURFACE);
	int k;
	scenario_reset();
	CHECK(plan_route(START_SURFACE, prev, GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	route_check_invariants("path_construction.intact", &r, START_SURFACE);
	CHECK(route_contains(&r, GATE_SURFACE));
	for (k = 0; k < r.count; k++) {
		sample_segment_on_route(&r, prev, r.points[k]);   /* no step segment leaves the route's surfaces */
		prev = r.points[k];
	}
	route_print("path_construction.intact", &r);
	printf("c4-live-path path_construction.segments_on_route samples=%d result=passed\n", (r.count) * 21);
}
static void scenario_obstacle_avoidance(void)
{
	struct route r;
	scenario_reset();
	/* dynamic obstacle occupies the gate link: the only per-link input CE's A* reads is the walkable flag */
	g_path_flags[GATE_SURFACE] &= (byte)~(1u << _pathfinding_surface_walkable_bit);
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	CHECK(!route_contains(&r, GATE_SURFACE));
	CHECK(route_contains(&r, 2));
	route_check_invariants("obstacle_avoidance.gate_blocked", &r, START_SURFACE);
	route_print("obstacle_avoidance.gate_blocked", &r);
	/* obstacle also occupies the detour: no link remains, the query must report no path */
	g_path_flags[2] &= (byte)~(1u << _pathfinding_surface_walkable_bit);
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) < 0);
	printf("c4-live-path obstacle_avoidance.detour_blocked no_path=1 result=passed\n");
}
static void scenario_movement_progress(void)
{
	struct route r;
	struct unit u;
	int ticks = 0, done = 0;
	scenario_reset();
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	u.pos = cell_center(START_SURFACE); u.step = 0;
	while (!done && ticks < MAX_TICKS) {
		done = unit_tick(&u, &r, 0);
		ticks++;
		CHECK(unit_on_route(&r, u.pos));
	}
	CHECK(done);
	CHECK(unit_cell(u.pos) == GOAL_SURFACE);
	printf("c4-live-path movement_progress ticks=%d bound=%d final_surface=%d result=passed\n",
		ticks, MAX_TICKS, unit_cell(u.pos));
}
static void scenario_recovery(void)
{
	struct route r, replanned;
	struct unit u;
	real_point3d prev;
	int tick, stalled = 0, replans = 0, done = 0;
	scenario_reset();
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &r) > 0);
	CHECK(route_contains(&r, GATE_SURFACE));
	u.pos = cell_center(START_SURFACE); u.step = 0;
	for (tick = 0; tick < MAX_TICKS && !done; tick++) {
		int held;
		if (tick == 20) g_path_flags[GATE_SURFACE] &= (byte)~(1u << _pathfinding_surface_walkable_bit);
		held = (tick >= 20 && replans == 0);   /* unit blocked until a replan occurs */
		prev = u.pos;
		done = unit_tick(&u, &r, held);
		if (fabsf(u.pos.x - prev.x) < 1e-6f && fabsf(u.pos.y - prev.y) < 1e-6f) stalled++;
		else stalled = 0;
		if (!done && stalled >= STALL_TICKS && replans == 0) {
			CHECK(plan_route(unit_cell(u.pos), u.pos, GOAL_SURFACE, cell_center(GOAL_SURFACE), &replanned) > 0);
			CHECK(!route_contains(&replanned, GATE_SURFACE));
			route_check_invariants("recovery.replanned", &replanned, unit_cell(u.pos));
			r = replanned;
			u.step = 0;
			replans++;
			stalled = 0;
		}
	}
	CHECK(done);
	CHECK(replans == 1);
	CHECK(unit_cell(u.pos) == GOAL_SURFACE);
	printf("c4-live-path recovery.stall_replan stall_ticks=%d replans=%d ticks=%d final_surface=%d result=passed\n",
		STALL_TICKS, replans, tick, unit_cell(u.pos));
}
static void scenario_breakable_mutation(void)
{
	struct route before, after;
	struct unit u;
	int tick, done = 0;
	scenario_reset();
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &before) > 0);
	CHECK(route_contains(&before, GATE_SURFACE));
	u.pos = cell_center(START_SURFACE); u.step = 0;
	for (tick = 0; tick < 25; tick++) unit_tick(&u, &before, 0);
	CHECK(unit_cell(u.pos) == 6);
	destroy_breakable(GATE_INDEX);
	CHECK(surface_is_broken(&g_structure, GATE_SURFACE));
	CHECK(TEST_FLAG(g_path_flags[GATE_SURFACE], _pathfinding_surface_walkable_bit));
	CHECK(TEST_FLAG(g_path_flags[GATE_SURFACE], _pathfinding_surface_breakable_bit));
	CHECK(route_contains(&before, GATE_SURFACE));   /* stale route still names the gate */
	CHECK(plan_route(unit_cell(u.pos), u.pos, GOAL_SURFACE, cell_center(GOAL_SURFACE), &after) > 0);
	CHECK(!route_contains(&after, GATE_SURFACE));
	route_check_invariants("breakable_mutation.replanned", &after, unit_cell(u.pos));
	route_print("breakable_mutation.replanned", &after);
	u.step = 0;
	for (tick = 0; tick < MAX_TICKS && !done; tick++) {
		done = unit_tick(&u, &after, 0);
		CHECK(unit_cell(u.pos) != GATE_SURFACE);
		CHECK(unit_on_route(&after, u.pos));
	}
	CHECK(done);
	printf("c4-live-path breakable_mutation.destroy_mid_path ticks_after_break=%d flags_unchanged=1 stale_route_names_gate=1 result=passed\n", tick);
}
static void scenario_breakable_control(void)
{
	struct route before, after;
	int k, same;
	scenario_reset();
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &before) > 0);
	destroy_breakable(CONTROL_INDEX);
	CHECK(surface_is_broken(&g_structure, CONTROL_SURFACE));
	CHECK(plan_route(START_SURFACE, cell_center(START_SURFACE), GOAL_SURFACE, cell_center(GOAL_SURFACE), &after) > 0);
	same = before.count == after.count;
	for (k = 0; same && k < before.count; k++) same = before.surfaces[k] == after.surfaces[k];
	CHECK(same);
	printf("c4-live-path breakable_mutation.off_route_control route_unchanged=1 result=passed\n");
}

static void route_check_invariants_retail(const char *label, const struct route *r);
static int run_retail(const char *filename, long n1, long n2)
{
	FILE *input = fopen(filename, "rb");
	uint32_t counts[4];
	struct collision_surface *surfaces;
	struct collision_edge *edges;
	struct collision_vertex *vertices;
	byte *flags;
	struct route before, after;
	real_point3d c1, c2;
	uint32_t s;
	int breakables = 0, k, same;
	if (!input || fread(counts, sizeof counts, 1, input) != 1) return 10;
	if (counts[0] == 0 || counts[0] > 100000 || counts[1] > 1000000 || counts[2] > 1000000 || counts[3] != counts[0]) return 11;
	surfaces = calloc(counts[0], sizeof *surfaces); edges = calloc(counts[1], sizeof *edges);
	vertices = calloc(counts[2], sizeof *vertices); flags = calloc(counts[3], 1);
	if (!surfaces || !edges || !vertices || !flags) return 12;
	if (fread(surfaces, sizeof *surfaces, counts[0], input) != counts[0] ||
		fread(edges, sizeof *edges, counts[1], input) != counts[1] ||
		fread(vertices, sizeof *vertices, counts[2], input) != counts[2] ||
		fread(flags, 1, counts[3], input) != counts[3]) return 13;
	fclose(input);
	g_collision.surfaces.address = surfaces; g_collision.surfaces.count = (long)counts[0];
	g_collision.edges.address = edges; g_collision.edges.count = (long)counts[1];
	g_collision.vertices.address = vertices; g_collision.vertices.count = (long)counts[2];
	g_structure.collision_bsp.address = &g_collision; g_structure.collision_bsp.count = 1;
	g_structure.pathfinding_surfaces.address = flags; g_structure.pathfinding_surfaces.count = (long)counts[3];
	memset(g_breakable_bits, 0xFF, sizeof g_breakable_bits);
	g_retail_mode = 1;
	CHECK(n1 >= 0 && n2 >= 0 && (uint32_t)n1 < counts[0] && (uint32_t)n2 < counts[0]);
	for (s = 0; s < counts[0]; s++) {
		if (!TEST_FLAG(surfaces[s].flags, _collision_surface_breakable_bit)) continue;
		breakables++;
		CHECK(!surface_is_broken(&g_structure, (long)s));
		printf("c4-live-path retail.breakable surface=%d index=%d path_flags=%d intact_broken=0 result=passed\n",
			(int)s, (int)surfaces[s].breakable_surface_index, (int)flags[s]);
	}
	CHECK(breakables > 0);
	c1 = ring_center(n1); c2 = ring_center(n2);
	CHECK(plan_route(n1, c1, n2, c2, &before) > 0);
	route_check_invariants_retail("retail.intact", &before);
	route_print("retail.intact", &before);
	for (s = 0; s < counts[0]; s++)
		if (TEST_FLAG(surfaces[s].flags, _collision_surface_breakable_bit))
			destroy_breakable(surfaces[s].breakable_surface_index);
	for (s = 0; s < counts[0]; s++)
		if (TEST_FLAG(surfaces[s].flags, _collision_surface_breakable_bit))
			CHECK(surface_is_broken(&g_structure, (long)s));
	CHECK(plan_route(n1, c1, n2, c2, &after) > 0);
	same = before.count == after.count;
	for (k = 0; same && k < before.count; k++) same = before.surfaces[k] == after.surfaces[k];
	CHECK(same);
	printf("c4-live-path retail.breakable_mutation breakables=%d route_unchanged=1 result=passed\n", breakables);
	return 0;
}

static void route_check_invariants_retail(const char *label, const struct route *r)
{
	int k;
	CHECK(r->count >= 2);
	for (k = 0; k < r->count; k++) {
		CHECK(TEST_FLAG(((byte const *)g_structure.pathfinding_surfaces.address)[r->surfaces[k]], _pathfinding_surface_walkable_bit));
		CHECK(!surface_is_broken(&g_structure, r->surfaces[k]));
		if (k > 0) CHECK(r->cost[k] >= r->cost[k - 1]);
	}
	printf("c4-live-path %s invariants=walkable,unbroken,monotone_cost result=passed\n", label);
}

int main(int argc, char **argv)
{
	if (argc == 5 && strcmp(argv[1], "retail") == 0)
		return run_retail(argv[2], atol(argv[3]), atol(argv[4]));
	if (argc != 1) return 2;
	scenario_surface_selection();
	scenario_path_construction();
	scenario_obstacle_avoidance();
	scenario_movement_progress();
	scenario_recovery();
	scenario_breakable_mutation();
	scenario_breakable_control();
	printf("c4-live-path summary scenarios=7 result=passed\n");
	return 0;
}
#undef long
