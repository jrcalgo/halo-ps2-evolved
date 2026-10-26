/* C4 live pathfinding, real-source driver. Links unchanged CE objects: ai/path.c (A*, build_path),
 * ai/path_smoothing.c, ai/path_structure_bsp.c, ai/path_obstacle_avoidance.c, ai/path_obstacles.c,
 * the collision 2D slice, math, and the tag accessor slice. tests/c4_live_pathfinding_stubs.c supplies
 * data only; tests/c4_live_pathfinding_abort.c aborts on any unexpected call. Compiled and linked by
 * tests/test_c4_live_pathfinding_real.py. */
#include "cseries/cseries.h"
#include "ai/path.h"
#include "objects/objects.h"
#include "objects/object_definitions.h"
#include "physics/collision_model_definitions.h"
#include "physics/collision_bsp_definitions.h"
#include "structures/structure_bsp_definitions.h"
#include "physics/breakable_surfaces.h"
#include "physics/collision_bsp.h"
#include "ai/actors.h"
#include "units/bipeds.h"
#include "physics/collision_usage.h"
#include "units/biped_definitions.h"
#include "ai/ai_debug.h"
#include "memory/data.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* data read by the stub layer */
#define C4_MAX_OBJECTS 16
struct object_definition c4_object_defs[C4_MAX_OBJECTS];
struct collision_model c4_collision_models[C4_MAX_OBJECTS];
short global_current_collision_users[MAXIMUM_COLLISION_USER_STACK_DEPTH];
short global_current_collision_user_depth = 1;   /* one enclosing collision user (bipeds.c:1168 assert) */
long c4_object_list[C4_MAX_OBJECTS];
struct structure_bsp *c4_structure;
struct collision_bsp *c4_collision;
extern struct collision_bsp *global_collision_bsp;
byte *c4_breakable_flags;
struct object_datum c4_objects[C4_MAX_OBJECTS];
short c4_object_count_in_sphere;
extern struct biped_datum c4_unit_biped;
extern struct biped_definition c4_biped_definition;

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)
#define GX 5
#define GY 3
#define NS (GX * GY)
#define NE (GX * (GY + 1) + (GX + 1) * GY)
#define NV ((GX + 1) * (GY + 1))
#define CELL 10.0f
#define GATE 7
#define GATE_INDEX 0
#define CONTROL 13
#define CONTROL_INDEX 1
#define START 5
#define GOAL 9
#define MAX_TICK_BOUND 400
#define STALL_TICKS 30

#define NSALL (NS + 1)           /* + the non-walkable outside surface that closes the mesh */
static struct collision_surface g_surfaces[NSALL];
static struct collision_edge g_edges[NE];
static struct collision_vertex g_vertices[NV];
static real_plane3d g_planes[NSALL];
static byte g_path_flags[NSALL];
static struct pathfinding_sphere g_spheres[C4_MAX_OBJECTS];
static long g_breakable_bits[8];
static struct path_state g_state;

static long vid(int i, int j) { return j * (GX + 1) + i; }
static long hid(int i, int j) { return j * GX + i; }
static long vid_edge(int i, int j) { return GX * (GY + 1) + j * (GX + 1) + i; }

static void world_build(void)
{
	int i, j, s, k;
	memset(g_surfaces, 0, sizeof g_surfaces);
	memset(g_edges, 0, sizeof g_edges);
	memset(g_vertices, 0, sizeof g_vertices);
	for (j = 0; j <= GY; j++) for (i = 0; i <= GX; i++) {
		g_vertices[vid(i, j)].point.x = CELL * i;
		g_vertices[vid(i, j)].point.y = CELL * j;
		g_vertices[vid(i, j)].point.z = 0.0f;
	}
	for (j = 0; j <= GY; j++) for (i = 0; i < GX; i++) {
		struct collision_edge *e = &g_edges[hid(i, j)];
		e->vertex_indices[0] = vid(i, j); e->vertex_indices[1] = vid(i + 1, j);
		e->surface_indices[0] = e->surface_indices[1] = NONE;
		e->edge_indices[0] = e->edge_indices[1] = NONE;
	}
	for (j = 0; j < GY; j++) for (i = 0; i <= GX; i++) {
		struct collision_edge *e = &g_edges[vid_edge(i, j)];
		e->vertex_indices[0] = vid(i, j); e->vertex_indices[1] = vid(i, j + 1);
		e->surface_indices[0] = e->surface_indices[1] = NONE;
		e->edge_indices[0] = e->edge_indices[1] = NONE;
	}
	for (s = 0; s < NS; s++) {
		long e[4];
		int ci = s % GX, cj = s / GX;
		e[0] = hid(ci, cj); e[1] = vid_edge(ci + 1, cj); e[2] = hid(ci, cj + 1); e[3] = vid_edge(ci, cj);
		for (k = 0; k < 4; k++) {
			struct collision_edge *edge = &g_edges[e[k]];
			if (edge->surface_indices[0] == NONE) edge->surface_indices[0] = s; else edge->surface_indices[1] = s;
		}
	}
	for (s = 0; s < NS; s++) {
		long e[4];
		int ci = s % GX, cj = s / GX;
		e[0] = hid(ci, cj); e[1] = vid_edge(ci + 1, cj); e[2] = hid(ci, cj + 1); e[3] = vid_edge(ci, cj);
		for (k = 0; k < 4; k++) {
			struct collision_edge *edge = &g_edges[e[k]];
			edge->edge_indices[edge->surface_indices[1] == s] = e[(k + 1) % 4];
		}
		{
			long a[4], b[4];
			a[0] = vid(ci, cj); b[0] = vid(ci + 1, cj);
			a[1] = vid(ci + 1, cj); b[1] = vid(ci + 1, cj + 1);
			a[2] = vid(ci + 1, cj + 1); b[2] = vid(ci, cj + 1);
			a[3] = vid(ci, cj + 1); b[3] = vid(ci, cj);
			for (k = 0; k < 4; k++) {
				struct collision_edge *edge = &g_edges[e[k]];
				/* edge_indices[j] shares vertex[1-j] and lies on surface[j] (path_smoothing.c:462-500):
				 * the right-side cell stores (b,a) so edge_indices[1] meets vertex[0]; a left-only cell keeps (a,b). */
				if (edge->surface_indices[1] == s) { edge->vertex_indices[0] = b[k]; edge->vertex_indices[1] = a[k]; }
				else { edge->vertex_indices[0] = a[k]; edge->vertex_indices[1] = b[k]; }
			}
		}
		g_surfaces[s].plane_designator = s;
		g_surfaces[s].first_edge_index = e[0];
		g_planes[s].n.i = 0.0f; g_planes[s].n.j = 0.0f; g_planes[s].n.k = 1.0f; g_planes[s].d = 0.0f;
		g_path_flags[s] = (byte)(1u << 6);
	}
	/* CE requires a closed mesh (path_state_begin's tag lookups assume every edge has two surfaces):
	 * each perimeter edge borders the outside surface NS, which is non-walkable and whose ring is the
	 * perimeter walked in reverse. */
	{
		long L[2 * (GX + GY)], n = 0, q;
		for (i = 0; i < GX; i++) L[n++] = hid(i, 0);
		for (j = 0; j < GY; j++) L[n++] = vid_edge(GX, j);
		for (i = GX - 1; i >= 0; i--) L[n++] = hid(i, GY);
		for (j = GY - 1; j >= 0; j--) L[n++] = vid_edge(0, j);
		for (q = 0; q < n; q++) {
			struct collision_edge *edge = &g_edges[L[q]];
			CHECK(edge->surface_indices[1] == NONE);
			edge->surface_indices[1] = NS;
			edge->edge_indices[1] = L[(q + n - 1) % n];
		}
		g_surfaces[NS].plane_designator = NS;
		g_surfaces[NS].first_edge_index = L[0];
		g_planes[NS].n.i = 0.0f; g_planes[NS].n.j = 0.0f; g_planes[NS].n.k = 1.0f; g_planes[NS].d = 0.0f;
		g_path_flags[NS] = 0;
	}
	c4_collision = calloc(1, sizeof *c4_collision);
	c4_collision->surfaces.address = g_surfaces; c4_collision->surfaces.count = NSALL;
	c4_collision->edges.address = g_edges; c4_collision->edges.count = NE;
	c4_collision->vertices.address = g_vertices; c4_collision->vertices.count = NV;
	c4_collision->bsp3d.planes.address = g_planes; c4_collision->bsp3d.planes.count = NSALL;
	c4_structure = calloc(1, sizeof *c4_structure);
	c4_structure->collision_bsp.address = c4_collision; c4_structure->collision_bsp.count = 1;
	c4_structure->pathfinding_surfaces.address = g_path_flags; c4_structure->pathfinding_surfaces.count = NSALL;
	c4_breakable_flags = (byte *)g_breakable_bits;
	memset(g_breakable_bits, 0xFF, sizeof g_breakable_bits);
}
static void make_breakable(int s, int index)
{
	g_path_flags[s] |= (byte)(1u << 7);
	g_surfaces[s].flags |= (byte)(1u << 3);
	g_surfaces[s].breakable_surface_index = (byte)index;
}
/* obstacle table: object 0 is the unit (ignored as source); obstacles are objects 1..C4_MAX_OBJECTS-1 */
static void obstacles_clear(void)
{
	memset(c4_objects, 0, sizeof c4_objects);
	memset(c4_object_defs, 0, sizeof c4_object_defs);
	memset(c4_collision_models, 0, sizeof c4_collision_models);
	memset(g_spheres, 0, sizeof g_spheres);
	memset(&c4_unit_biped, 0, sizeof c4_unit_biped);
	c4_unit_biped.object.type = _object_type_biped;      /* the unit: ignored as source */
	c4_unit_biped.object.bounding_sphere_center.x = 5.0f;
	c4_unit_biped.object.bounding_sphere_center.y = 15.0f;
	c4_object_list[0] = 0;
	c4_object_count_in_sphere = 1;
}
static void obstacle_add(real x, real y, real radius)
{
	int k = c4_object_count_in_sphere;
	CHECK(k < C4_MAX_OBJECTS);
	c4_objects[k].object.type = _object_type_scenery;
	c4_objects[k].object.bounding_sphere_center.x = x;
	c4_objects[k].object.bounding_sphere_center.y = y;
	c4_objects[k].object.bounding_sphere_radius = radius;
	c4_objects[k].definition_index = k;
	c4_object_defs[k].object.collision_model.index = k;
	c4_object_defs[k].object.flags = 0;
	g_spheres[k].node_index = (short)NONE;
	g_spheres[k].center.x = 0.0f; g_spheres[k].center.y = 0.0f; g_spheres[k].center.z = 0.0f;
	g_spheres[k].radius = radius;
	c4_collision_models[k].pathfinding_spheres.address = &g_spheres[k];
	c4_collision_models[k].pathfinding_spheres.count = 1;
	c4_object_list[k] = k;
	c4_object_count_in_sphere = (short)(k + 1);
}
static void set_scenery_obstacle(real x, real y, real radius, int present)
{
	obstacles_clear();
	if (present) obstacle_add(x, y, radius);
}
static void scenario_reset(void)
{
	world_build();
	make_breakable(GATE, GATE_INDEX);
	make_breakable(CONTROL, CONTROL_INDEX);
	g_path_flags[12] = 0;     /* wall at (2,2) */
	set_scenery_obstacle(-100.0f, -100.0f, 0.0f, 0);
}
/* Oracle for the broken test: the same bit test as path.c surface_is_broken (path.c:632-657),
 * re-stated because that function is static in path.c. */
static int oracle_surface_broken(long s)
{
	struct collision_surface const *surface = &g_surfaces[s];
	if (!TEST_FLAG(surface->flags, 3)) return 0;
	return !BIT_VECTOR_TEST_FLAG(g_breakable_bits, surface->breakable_surface_index);
}

static real_point3d pt(real x, real y) { real_point3d p; p.x = x; p.y = y; p.z = 0.0f; return p; }
static real_point3d cell_center(int s) { return pt(CELL * (s % GX) + 5.0f, CELL * (s / GX) + 5.0f); }
static int cell_of(real_point3d p) { return (int)floorf(p.y / CELL) * GX + (int)floorf(p.x / CELL); }

/* a point is on valid ground when it lies in a walkable, unbroken cell (edge tolerance) */
static int on_valid_ground(real_point3d p)
{
	int s, i, j;
	for (s = 0; s < NS; s++) {
		i = s % GX; j = s / GX;
		if (!((g_path_flags[s] >> 6) & 1)) continue;
		if (oracle_surface_broken(s)) continue;
		if (p.x >= CELL * i - 0.01f && p.x <= CELL * (i + 1) + 0.01f &&
			p.y >= CELL * j - 0.01f && p.y <= CELL * (j + 1) + 0.01f) return 1;
	}
	return 0;
}
static void sample_segment_valid(real_point3d a, real_point3d b)
{
	int k;
	for (k = 0; k <= 40; k++) {
		real_point3d p;
		real t = (real)k / 40.0f;
		p.x = a.x + (b.x - a.x) * t; p.y = a.y + (b.y - a.y) * t; p.z = 0.0f;
		CHECK(on_valid_ground(p));
	}
}

/* Real A* followed by the real build path (smoothing then obstacle avoidance). */
static int plan(struct path_result *result, long start_surface, real_point3d start, long goal_surface, real_point3d goal)
{
	struct path_input input;
	path_input_new(&input, 0.5f, FALSE, 0);
	path_input_set_start(&input, &start, start_surface);
	path_state_new(&input, &g_state, NULL);
	path_state_destination(&g_state, &goal, goal_surface, 0.0f);
	if (!path_state_find(&g_state)) return 0;
	return path_state_build_path(&g_state, result) ? 1 : 0;
}
static void print_path(const char *label, const struct path_result *r)
{
	int k;
	printf("c4-live-real %s valid=%d steps=%d finishes=%d", label, (int)r->valid, (int)r->step_count, (int)r->steps_finish_path);
	for (k = 0; k < r->step_count; k++)
		printf(" [%d:%.4f,%.4f]", (int)r->steps[k].surface_index, (double)r->steps[k].point.x, (double)r->steps[k].point.y);
	printf("\n");
}
static void check_path_invariants(const char *label, const struct path_result *r, real_point3d start, real_point3d goal)
{
	int k;
	real_point3d prev = start;
	CHECK(r->valid);
	CHECK(r->step_count >= 1);
	for (k = 0; k < r->step_count; k++) {
		long s = r->steps[k].surface_index;
		CHECK(TEST_FLAG(g_path_flags[s], 6));
		CHECK(!oracle_surface_broken(s));
		sample_segment_valid(prev, r->steps[k].point);
		prev = r->steps[k].point;
	}
	CHECK(r->steps_finish_path);
	CHECK(fabsf(r->steps[r->step_count - 1].point.x - goal.x) < 0.5f && fabsf(r->steps[r->step_count - 1].point.y - goal.y) < 0.5f);
	CHECK(r->steps[r->step_count - 1].surface_index == GOAL);
	printf("c4-live-real %s invariants=walkable,unbroken,segments_on_valid_ground,goal_preserved result=passed\n", label);
}

static void scenario_smoothing(void)
{
	struct path_result r;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	scenario_reset();
	CHECK(plan(&r, START, s, GOAL, g));
	check_path_invariants("smoothing.intact", &r, s, g);
	print_path("smoothing.intact", &r);
	/* determinism inside one process */
	{
		struct path_result again;
		CHECK(plan(&again, START, s, GOAL, g));
		int k;
		CHECK(r.valid == again.valid && r.step_count == again.step_count && r.steps_finish_path == again.steps_finish_path);
		for (k = 0; k < r.step_count; k++) {
			CHECK(r.steps[k].surface_index == again.steps[k].surface_index);
			CHECK(memcmp(&r.steps[k].point, &again.steps[k].point, sizeof(real_point3d)) == 0);
		}
	}
	printf("c4-live-real smoothing.deterministic result=passed\n");
}
static void scenario_blocked_link(void)
{
	struct path_result r;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	scenario_reset();
	g_path_flags[GATE] &= (byte)~(1u << 6);      /* blocked link: gate not walkable */
	CHECK(plan(&r, START, s, GOAL, g));
	check_path_invariants("smoothing.gate_blocked", &r, s, g);
	print_path("smoothing.gate_blocked", &r);
	{
		int k;
		for (k = 0; k < r.step_count; k++) CHECK(r.steps[k].surface_index != GATE);
	}
	printf("c4-live-real smoothing.gate_blocked avoids_gate=1 result=passed\n");
}
static void scenario_breakable_destroy(void)
{
	struct path_result r;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	scenario_reset();
	CHECK(oracle_surface_broken(GATE) == 0);
	g_breakable_bits[0] &= ~(1L << GATE_INDEX);
	CHECK(oracle_surface_broken(GATE));
	CHECK(plan(&r, START, s, GOAL, g));
	check_path_invariants("smoothing.gate_destroyed", &r, s, g);
	print_path("smoothing.gate_destroyed", &r);
	printf("c4-live-real breakable.smoothing_avoids_destroyed result=passed\n");
}

/* ---- actor-level driver (real actor_path_refresh and actor_destination_update) ---- */
static struct actor_datum g_actor[1];
static struct actor_debug_info g_actor_debug[1];
struct actor_debug_info *actor_debug_array = g_actor_debug;
long c4_game_time;
void *datum_get(struct data_array *array, long index)
{
	(void)array;
	if (index != 0) { fprintf(stderr, "c4 datum_get index %ld\n", (long)index); abort(); }
	return &g_actor[0];
}
long game_time_get(void) { return c4_game_time; }
/* object origin: the datum's bounding-sphere centre, which this fixture uses as the object position */
real_point3d *object_get_origin(long object_index, real_point3d *origin)
{
	struct object_datum const *object = (struct object_datum const *)object_get_and_verify_type(object_index, 0);
	*origin = object->object.bounding_sphere_center;
	return origin;
}
struct path_debug_storage *ai_debug_get_path_storage(long actor_index) { (void)actor_index; return NULL; }
/* actors.c:1448 vehicle and obey branches cannot compile (vehicle_definition absent from the HCU tree);
 * the non-vehicle default that this unit uses is 0.5 (MAX(tolerance, 0.2f)). */
real actor_destination_tolerance(long actor_index) { (void)actor_index; return 0.5f; }
static void actor_setup(real_point3d position, long start_surface, real_point3d goal, long goal_surface)
{
	memset(&g_actor[0], 0, sizeof g_actor[0]);
	g_actor[0].meta.unit_index = 0;               /* the unit object: ignored as obstacle source */
	g_actor[0].meta.timeslice = TRUE;
	g_actor[0].input.vehicle_index = NONE;
	g_actor[0].input.vehicle_driver_type = _actor_vehicle_driver_none;
	g_actor[0].input.pathfinding_surface_index = start_surface;   /* actor_find_pathfinding_location early-out */
	g_actor[0].input.pathfinding_point = position;
	g_actor[0].input.position.body_position = position;
	g_actor[0].control.path.destination.point = goal;
	g_actor[0].control.path.destination.surface_index = goal_surface;
	g_actor[0].control.path.destination.target_radius = 0.0f;
	g_actor[0].control.path.destination_orders.destination_type = _destination_raw_location;
	g_actor[0].control.path.destination_orders.raw.point = goal;             /* actor_moving.c:1884 */
	g_actor[0].control.path.destination_orders.raw.surface_index = goal_surface;
	g_actor[0].control.path.destination_orders.ignore_target_object_index = NONE;
	g_actor[0].control.path.destination_original_distance = 0.0f;
	g_actor[0].danger_zone.danger_type = 0;
	c4_unit_biped.object.bounding_sphere_center = position;
	c4_unit_biped.object.type = _object_type_biped;
}
/* movement integrator (the unit's motion model, outside actor_moving.c): moves toward the current step point */
static void actor_integrate(real_point3d *pos, const struct actor_datum *a)
{
	real_point3d target = a->control.moving_towards_point;
	real dx = target.x - pos->x, dy = target.y - pos->y, len = sqrtf(dx * dx + dy * dy);
	if (a->control.moving && len > 0.0f) {
		real move = len < 0.5f ? len : 0.5f;
		pos->x += dx / len * move;
		pos->y += dy / len * move;
	}
}
static int oracle_valid_point(real_point3d p) { return on_valid_ground(p); }
static void scenario_actor_progress(void)
{
	int tick, done = 0;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	struct path_result unused_result; (void)unused_result;
	scenario_reset();
	actor_setup(s, START, g, GOAL);
	CHECK(actor_path_refresh(0, TRUE, NULL));
	CHECK(g_actor[0].control.path.path.valid);
	for (tick = 0; tick < MAX_TICK_BOUND && !done; tick++) {
		real_point3d before = g_actor[0].input.position.body_position;
		g_actor[0].meta.timeslice = TRUE;
		g_actor[0].control.path.refreshed_this_tick = FALSE;
		/* the unit's support surface, as biped_find_pathfinding_surface_index would supply each tick */
		g_actor[0].input.pathfinding_surface_index = cell_of(g_actor[0].input.position.body_position);
		g_actor[0].input.pathfinding_point = g_actor[0].input.position.body_position;
		actor_destination_update(0);
		actor_integrate(&g_actor[0].input.position.body_position, &g_actor[0]);
		g_actor[0].input.pathfinding_point = g_actor[0].input.position.body_position;
		CHECK(oracle_valid_point(g_actor[0].input.position.body_position));
		done = g_actor[0].control.path.at_destination || !g_actor[0].control.path.path.valid;
		(void)before;
	}
	CHECK(g_actor[0].control.path.at_destination);
	printf("c4-live-real actor.progress ticks=%d bound=%d final_surface=%d result=passed\n",
		tick, MAX_TICK_BOUND, cell_of(g_actor[0].input.position.body_position));
}


/* does the smoothed path's polyline (from start through the step points) pass through the cell? */
static int path_crosses_cell(const struct path_result *r, real_point3d start, long surface)
{
	int k, n;
	real_point3d prev = start;
	int i = surface % GX, j = surface / GX;
	for (k = 0; k < r->step_count; k++) {
		for (n = 0; n <= 40; n++) {
			real t = (real)n / 40.0f;
			real x = prev.x + (r->steps[k].point.x - prev.x) * t;
			real y = prev.y + (r->steps[k].point.y - prev.y) * t;
			if (x > CELL * i + 0.01f && x < CELL * (i + 1) - 0.01f && y > CELL * j + 0.01f && y < CELL * (j + 1) - 0.01f) return 1;
		}
		prev = r->steps[k].point;
	}
	return 0;
}
static void scenario_actor_recovery(void)
{
	int tick, done = 0, stalled = 0, replans = 0, held_ticks = 0;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	real_point3d last;
	scenario_reset();
	actor_setup(s, START, g, GOAL);
	CHECK(actor_path_refresh(0, TRUE, NULL));
	CHECK(path_crosses_cell(&g_actor[0].control.path.path, s, GATE));
	last = g_actor[0].input.position.body_position;
	for (tick = 0; tick < MAX_TICK_BOUND && !done; tick++) {
		real_point3d before = g_actor[0].input.position.body_position;
		int held = (tick >= 20 && replans == 0);       /* blocked after the obstacle appears */
		if (tick == 20) g_path_flags[GATE] &= (byte)~(1u << 6);   /* dynamic obstacle on the gate link */
		g_actor[0].input.pathfinding_surface_index = cell_of(before);
		g_actor[0].input.pathfinding_point = before;
		g_actor[0].control.path.refreshed_this_tick = FALSE;
		g_actor[0].meta.timeslice = TRUE;
		actor_destination_update(0);
		if (!held) actor_integrate(&g_actor[0].input.position.body_position, &g_actor[0]);
		CHECK(oracle_valid_point(g_actor[0].input.position.body_position));
		if (fabsf(g_actor[0].input.position.body_position.x - before.x) < 1e-6f &&
			fabsf(g_actor[0].input.position.body_position.y - before.y) < 1e-6f) stalled++;
		else stalled = 0;
		if (held) held_ticks++;
		if (replans == 0 && stalled >= STALL_TICKS) {
			/* stall detected by the driver: replan with the real actor_path_refresh */
			g_actor[0].input.pathfinding_surface_index = cell_of(g_actor[0].input.position.body_position);
			CHECK(actor_path_refresh(0, TRUE, NULL));
			CHECK(g_actor[0].control.path.path.valid);
			CHECK(!path_crosses_cell(&g_actor[0].control.path.path, g_actor[0].input.position.body_position, GATE));
			replans++;
			stalled = 0;
		}
		done = g_actor[0].control.path.at_destination || !g_actor[0].control.path.path.valid;
	}
	CHECK(replans == 1);
	CHECK(g_actor[0].control.path.at_destination);
	CHECK(cell_of(g_actor[0].input.position.body_position) == GOAL);
	printf("c4-live-real actor.recovery stall_ticks=%d replans=%d held=%d ticks=%d final_surface=%d avoided_gate=1 result=passed\n",
		STALL_TICKS, replans, held_ticks, tick, cell_of(g_actor[0].input.position.body_position));
	(void)last;
}


/* ---- point-to-surface selection: real biped_find_pathfinding_surface_index (units/bipeds.c:1537) ---- */
long biped_find_pathfinding_surface_index(long biped_index, real_point3d *pathfinding_point);
static long select_surface(long support, long last, real_point3d point, real_point3d *out_point, long attempt_time)
{
	c4_unit_biped.biped.pathfinding_surface_index = NONE;
	c4_unit_biped.biped.pathfinding_point = point;
	c4_unit_biped.biped.support_surface_index = support;
	c4_unit_biped.biped.last_pathfinding_surface_index = last;
	c4_unit_biped.biped.last_pathfinding_attempt_time = attempt_time;
	c4_game_time = 1000;
	*out_point = point;
	return biped_find_pathfinding_surface_index(0, out_point);
}
static void scenario_selection_synthetic(void)
{
	real_point3d out, p;
	long found;
	scenario_reset();
	memset(&c4_biped_definition, 0, sizeof c4_biped_definition);
	/* support surface branch: point projected onto the support surface */
	p = pt(25.0f, 15.0f);
	found = select_surface(GATE, NONE, p, &out, -1);
	CHECK(found == GATE);
	CHECK(cell_of(out) == GATE && fabsf(out.z) < 1e-3f);
	printf("c4-live-real selection.support_surface selected=%ld projected=%.3f,%.3f result=passed\n", found, (double)out.x, (double)out.y);
	/* last-surface branch: point inside the last surface is kept on it */
	/* attempt throttle: no new search in the same game tick, the surface stays NONE */
	found = select_surface(GATE, NONE, pt(25.0f, 15.0f), &out, 1000);
	CHECK(found == NONE);
	printf("c4-live-real selection.attempt_throttled selected=%ld result=passed\n", found);
	/* flying bipeds take no surface */
	c4_biped_definition.biped.flags |= (word)(1u << _biped_flying_bit);
	found = select_surface(GATE, NONE, pt(25.0f, 15.0f), &out, -1);
	CHECK(found == NONE);
	printf("c4-live-real selection.flying selected=%ld result=passed\n", found);
	c4_biped_definition.biped.flags = 0;
}


static real min_distance_to_disc(const struct path_result *r, real_point3d start, real cx, real cy)
{
	int k, n;
	real best = 1e30f;
	real_point3d prev = start;
	for (k = 0; k < r->step_count; k++) {
		for (n = 0; n <= 40; n++) {
			real t = (real)n / 40.0f;
			real x = prev.x + (r->steps[k].point.x - prev.x) * t - cx;
			real y = prev.y + (r->steps[k].point.y - prev.y) * t - cy;
			real d = sqrtf(x * x + y * y);
			if (d < best) best = d;
		}
		prev = r->steps[k].point;
	}
	return best;
}
static void scenario_disc_avoidance(void)
{
	struct path_result r;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	real min_d;
	scenario_reset();
	set_scenery_obstacle(8.0f, 15.0f, 2.0f, 1);      /* dynamic obstacle disc inside the step-start search radius */
	CHECK(plan(&r, START, s, GOAL, g));
	check_path_invariants("disc.steer", &r, s, g);
	min_d = min_distance_to_disc(&r, s, 8.0f, 15.0f);
	CHECK(min_d >= 2.0f);                              /* the path never enters the obstacle disc */
	print_path("disc.steer", &r);
	printf("c4-live-real disc.steer min_distance=%.3f radius=2.000 steered_around=1 result=passed\n", (double)min_d);
	/* characterisation (not a blocked report): CE returns a valid straight path when the step start lies inside the disc */
	scenario_reset();
	set_scenery_obstacle(5.0f, 15.0f, 40.0f, 1);
	CHECK(plan(&r, START, s, GOAL, g));
	CHECK(r.valid && r.step_count == 1);
	printf("c4-live-real disc.start_inside_characterised valid=%d steps=%d result=passed\n", (int)r.valid, (int)r.step_count);
}


/* ---- retail mode: full-record payload (tests/test_c4_live_pathfinding_real.py: raw collision records and
 * BSP trees copied byte-for-byte from the decompressed Prisoner BSP). Records map 1:1 onto the CE structs. */
struct collision_leaf { word flags; short bsp2d_reference_count; long first_bsp2d_reference_index; };   /* collision_bsp.c:199 */
struct bsp2d_reference { long plane_designator; long root_index; };                                   /* collision_bsp.c:206 */
static struct collision_surface *r_surfaces;
static struct collision_edge *r_edges;
static struct collision_vertex *r_vertices;
static struct bsp3d_node *r_nodes;
static real_plane3d *r_planes;
static struct collision_leaf *r_leaves;
static struct bsp2d_reference *r_refs;
static struct bsp2d_node *r_bsp2d;
static byte *r_flags;
static void *r_read_block(const unsigned char *buf, long *at, long count, long size)
{
	void *block = calloc((size_t)(count > 0 ? count : 1), (size_t)size);
	CHECK(block != NULL);
	memcpy(block, buf + *at, (size_t)(count * size));
	*at += count * size;
	return block;
}
/* builds the real collision structures from the payload; returns the surface count */
static long retail_load(const char *path)
{
	FILE *f = fopen(path, "rb");
	unsigned char *buf;
	long len, at, c[9], i;
	if (!f) return -1;
	fseek(f, 0, SEEK_END); len = ftell(f); fseek(f, 0, SEEK_SET);
	buf = malloc((size_t)len);
	CHECK(buf && fread(buf, 1, (size_t)len, f) == (size_t)len);
	fclose(f);
	for (i = 0; i < 9; i++) c[i] = (long)(buf[i * 4] | (buf[i * 4 + 1] << 8) | (buf[i * 4 + 2] << 16) | ((unsigned long)buf[i * 4 + 3] << 24));
	at = 36;
	r_surfaces = r_read_block(buf, &at, c[0], 12);
	r_edges = r_read_block(buf, &at, c[1], 24);
	r_vertices = r_read_block(buf, &at, c[2], 16);
	r_flags = r_read_block(buf, &at, c[3], 1);
	r_nodes = r_read_block(buf, &at, c[4], 12);
	r_planes = r_read_block(buf, &at, c[5], 16);
	r_leaves = r_read_block(buf, &at, c[6], 8);
	r_refs = r_read_block(buf, &at, c[7], 8);
	r_bsp2d = r_read_block(buf, &at, c[8], 20);
	CHECK(at == len);
	c4_collision = calloc(1, sizeof *c4_collision);
	global_collision_bsp = c4_collision;
	c4_collision->surfaces.address = r_surfaces; c4_collision->surfaces.count = c[0];
	c4_collision->edges.address = r_edges; c4_collision->edges.count = c[1];
	c4_collision->vertices.address = r_vertices; c4_collision->vertices.count = c[2];
	c4_collision->bsp3d.nodes.address = r_nodes; c4_collision->bsp3d.nodes.count = c[4];
	c4_collision->bsp3d.planes.address = r_planes; c4_collision->bsp3d.planes.count = c[5];
	c4_collision->leaves.address = r_leaves; c4_collision->leaves.count = c[6];
	c4_collision->bsp2d_references.address = r_refs; c4_collision->bsp2d_references.count = c[7];
	c4_collision->bsp2d.nodes.address = r_bsp2d; c4_collision->bsp2d.nodes.count = c[8];
	c4_structure = calloc(1, sizeof *c4_structure);
	c4_structure->collision_bsp.address = c4_collision; c4_structure->collision_bsp.count = 1;
	c4_structure->pathfinding_surfaces.address = r_flags; c4_structure->pathfinding_surfaces.count = c[3];
	memset(g_breakable_bits, 0xFF, sizeof g_breakable_bits);
	c4_breakable_flags = (byte *)g_breakable_bits;
	free(buf);
	return c[0];
}
static real_point3d ring_probe(long s)
{
	/* the probe point: the first ring triangle's centroid, lifted onto the surface plane (x,y kept) */
	struct collision_surface const *surface = &r_surfaces[s];
	long edge_index = surface->first_edge_index, start = edge_index;
	real_point3d pts[3], p;
	int m = 0, guard;
	for (guard = 0; guard < 64 && m < 3; guard++) {
		struct collision_edge const *edge = &r_edges[edge_index];
		int reverse = edge->surface_indices[1] == s;
		pts[m++] = r_vertices[edge->vertex_indices[reverse]].point;
		edge_index = edge->edge_indices[reverse];
		if (edge_index == start) break;
	}
	CHECK(m == 3);
	p.x = (pts[0].x + pts[1].x + pts[2].x) / 3.0f;
	p.y = (pts[0].y + pts[1].y + pts[2].y) / 3.0f;
	p.z = (pts[0].z + pts[1].z + pts[2].z) / 3.0f;
	return p;
}
/* one row per surface: 2D point-test verdict (collision_bsp.c:823, sign TRUE as bipeds.c:1585),
 * ground-search result (bipeds.c:1475 via collision_bsp_test_vector), and the full selector result */
static int run_retail_selection(const char *path, long surface)
{
	long n = retail_load(path);
	real_point3d probe, out;
	boolean verdict2d;
	long ground, selected;
	CHECK(n > 0 && surface >= 0 && surface < n);
	probe = ring_probe(surface);
	c4_unit_biped.object.bounding_sphere_center = probe;
	verdict2d = collision_surface_test_point2d(c4_collision, surface, _z, TRUE, (real_point2d const *)&probe);
	ground = select_surface(NONE, NONE, probe, &out, -1);
	c4_unit_biped.object.bounding_sphere_center = probe;
	selected = select_surface(NONE, surface, probe, &out, -1);
	printf("c4-live-real retail.selection surface=%ld normal_z=%.3f verdict2d=%d ground=%ld selected=%ld result=%s\n",
		surface, (double)r_planes[surface].n.k, (int)verdict2d, ground, selected,
		selected == surface ? "passed" : "failed");
	return selected == surface ? 0 : 1;
}


/* Item 3: destroy the breakable gate while the actor is mid-path. The real actor_destination_update
 * refreshes the path each tick (actor_moving.c:2109 -> refresh, which rebuilds unless at destination,
 * actor_moving.c:2003-2012), so the first real refresh after the break must route around the gate. */
static void scenario_midpath_breakable(void)
{
	int tick, done = 0, broken_at = -1, crossed_before = 0, entered_gate = 0;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	real_point3d prev_pos;
	scenario_reset();
	actor_setup(s, START, g, GOAL);
	CHECK(actor_path_refresh(0, TRUE, NULL));
	crossed_before = path_crosses_cell(&g_actor[0].control.path.path, s, GATE);
	CHECK(crossed_before);
	for (tick = 0; tick < MAX_TICK_BOUND && !done; tick++) {
		prev_pos = g_actor[0].input.position.body_position;
		if (broken_at < 0 && g_actor[0].input.position.body_position.x >= 15.0f) {
			BIT_VECTOR_SET_FLAG(g_breakable_bits, GATE_INDEX, FALSE);
			CHECK(oracle_surface_broken(GATE));
			broken_at = tick;
		}
		g_actor[0].input.pathfinding_surface_index = cell_of(prev_pos);
		g_actor[0].input.pathfinding_point = prev_pos;
		g_actor[0].control.path.refreshed_this_tick = FALSE;
		g_actor[0].meta.timeslice = TRUE;
		actor_destination_update(0);
		if (broken_at >= 0 && tick == broken_at + 1) {
			CHECK(g_actor[0].control.path.path.valid);
			CHECK(!path_crosses_cell(&g_actor[0].control.path.path, prev_pos, GATE));
		}
		actor_integrate(&g_actor[0].input.position.body_position, &g_actor[0]);
		if (cell_of(g_actor[0].input.position.body_position) == GATE) entered_gate = 1;
		CHECK(oracle_valid_point(g_actor[0].input.position.body_position));
		done = g_actor[0].control.path.at_destination || !g_actor[0].control.path.path.valid;
	}
	CHECK(broken_at >= 0);
	CHECK(!entered_gate);
	CHECK(g_actor[0].control.path.at_destination);
	CHECK(cell_of(g_actor[0].input.position.body_position) == GOAL);
	printf("c4-live-real midpath.breakable crossed_before=%d broken_at_tick=%d entered_gate=%d ticks=%d final_surface=%d result=passed\n",
		crossed_before, broken_at, entered_gate, tick, cell_of(g_actor[0].input.position.body_position));
}

/* Item 2: blocked avoidance (path_obstacle_avoidance.c:1082). Eight scenery discs (r=3) on a ring of
 * radius 3 around the start leave no free exit within the 4-unit collection radius (:975). */
static void scenario_blocked_avoidance(void)
{
	struct path_result r;
	real_point3d s = cell_center(START), g = cell_center(GOAL);
	struct path_step raw;
	struct path_step out[4];
	short out_count = 0;
	boolean finishes = FALSE;
	boolean avoided;
	int k;
	real ang;
	scenario_reset();
	obstacles_clear();
	for (k = 0; k < 8; k++) {
		ang = (real)k * 0.785398f;
		obstacle_add(5.0f + 3.0f * cosf(ang), 15.0f + 3.0f * sinf(ang), 3.0f);
	}
	{
		struct path_input in;
		path_input_new(&in, 0.5f, FALSE, 0);
		path_input_set_start(&in, &s, START);
		path_state_new(&in, &g_state, NULL);
		path_state_destination(&g_state, &g, GOAL, 0.0f);
		CHECK(path_state_find(&g_state));
	}
	raw.surface_index = GOAL;
	raw.point = g;
	avoided = path_avoid_obstacles(&g_state, 1, &raw, &out_count, out, &finishes);
	CHECK(avoided == FALSE);
	CHECK(plan(&r, START, s, GOAL, g) == 0);
	printf("c4-live-real avoidance.blocked discs=8 find=1 avoid_returned=%d build_valid=0 result=passed\n", (int)avoided);
	(void)finishes;
}

int main(int argc, char **argv)
{
	setvbuf(stdout, NULL, _IONBF, 0);
	if (argc == 4 && strcmp(argv[1], "retail") == 0) return run_retail_selection(argv[2], atol(argv[3]));
	(void)argc; (void)argv;
	scenario_smoothing();
	scenario_blocked_link();
	scenario_actor_progress();
	scenario_breakable_destroy();
	scenario_actor_recovery();
	scenario_selection_synthetic();
	scenario_midpath_breakable();
	scenario_blocked_avoidance();
	scenario_disc_avoidance();
	printf("c4-live-real summary scenarios=9 result=passed\n");
	return 0;
}
