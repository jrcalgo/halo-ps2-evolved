/* Host driver for path_state_build_path on one raw Blood Gulch route.
   CE functions live in the generated extract and the original translation units.
   This file only supplies the records those functions read and the route fixture. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>

#include "cseries.h"
#include "errors.h"
#include "data.h"
#include "memory_pool.h"
#include "game_state.h"
#include "objects.h"
#include "object_types.h"
#include "units.h"
#include "unit_definitions.h"
#include "bipeds.h"
#include "actors.h"
#include "actor_definitions.h"
#include "ai_debug.h"
#include "ai_profile.h"
#include "path.h"
#include "breakable_surfaces.h"
#include "collision_bsp.h"
#include "collision_bsp_definitions.h"
#include "collision_usage.h"
#include "scenario.h"
#include "structure_bsp_definitions.h"
#include "game.h"
#include "real_math.h"

extern struct structure_bsp *global_structure_bsp;

#define PATHSMOOTH_VARIANT_INDEX 11
#define PATHSMOOTH_DEFINITION_INDEX 22
#define PATHSMOOTH_UNIT_DEFINITION_INDEX 33

struct ai_debug_state ai_debug;
struct ai_profile_globals ai_profile;
struct actor_debug_info *actor_debug_array;

static union real_argb_color pathsmooth_white = {{1.f, 1.f, 1.f, 1.f}};
static union real_argb_color pathsmooth_black = {{1.f, 0.f, 0.f, 0.f}};
static union real_argb_color pathsmooth_red = {{1.f, 1.f, 0.f, 0.f}};
static union real_argb_color pathsmooth_green = {{1.f, 0.f, 1.f, 0.f}};
static union real_argb_color pathsmooth_yellow = {{1.f, 1.f, 1.f, 0.f}};
const union real_argb_color *global_real_argb_white = &pathsmooth_white;
const union real_argb_color *global_real_argb_black = &pathsmooth_black;
const union real_argb_color *global_real_argb_red = &pathsmooth_red;
const union real_argb_color *global_real_argb_green = &pathsmooth_green;
const union real_argb_color *global_real_argb_yellow = &pathsmooth_yellow;

unsigned long D3D__RenderState[144];
real_point3d debug_obstacle_path_start_point;
long debug_obstacle_path_start_surface_index;
real_point3d debug_obstacle_path_goal_point;
long debug_obstacle_path_goal_surface_index;
real debug_obstacle_path_radius;
boolean debug_obstacle_path_finishing;
boolean debug_ignore_broken_surfaces;

short global_current_collision_user_depth;
short global_current_collision_users[MAXIMUM_COLLISION_USER_STACK_DEPTH];

static byte pathsmooth_game_state[48 * 1024 * 1024];
static long pathsmooth_game_state_used;
static struct biped_datum pathsmooth_biped;
static struct actor_variant_definition pathsmooth_variant;
static struct actor_definition pathsmooth_definition;
static struct unit_definition pathsmooth_unit_definition;
static long pathsmooth_unit_index = NONE;
static int pathsmooth_sphere_calls;
static int pathsmooth_sphere_last;
static short pathsmooth_sphere_cluster = 0x7fff;

short __real_objects_in_sphere(
	unsigned long class_flags,
	unsigned long type_flags,
	struct location const *location,
	real_point3d const *center,
	real radius,
	long *object_indices,
	short maximum_count);

static void pathsmooth_fail(const char *message)
{
	fprintf(stderr, "BLOCKED %s\n", message);
	exit(3);
}

void stack_walk(short levels_to_ignore)
{
	fprintf(stderr, "stack_walk %d\n", (int)levels_to_ignore);
}

void display_assert(char *information, char *file, long line, boolean fatal)
{
	fprintf(stderr, "display_assert fatal=%d %s:%ld %s\n",
		fatal ? 1 : 0, file ? file : "", line, information ? information : "");
	fflush(stderr);
}

void system_exit(long code)
{
	exit((int)code);
}

void error(short priority, const char *format, ...)
{
	va_list arguments;

	fprintf(stderr, "ce-error %d ", (int)priority);
	va_start(arguments, format);
	vfprintf(stderr, format, arguments);
	va_end(arguments);
	fputc('\n', stderr);
}

void platform_log(const char *format, ...)
{
	va_list arguments;

	fputs("platform_log ", stderr);
	va_start(arguments, format);
	vfprintf(stderr, format, arguments);
	va_end(arguments);
	fputc('\n', stderr);
}

void *game_state_malloc(const char *name, const char *type, long size)
{
	long aligned = (pathsmooth_game_state_used + 15) & ~15;

	(void)type;
	if (size < 0 || aligned > (long)sizeof(pathsmooth_game_state) - size)
		pathsmooth_fail(name ? name : "game_state_malloc");
	memset(pathsmooth_game_state + aligned, 0, (size_t)size);
	pathsmooth_game_state_used = aligned + size;
	return pathsmooth_game_state + aligned;
}

struct data_array *game_state_data_new(const char *name, short maximum_count, short size)
{
	long bytes = data_allocation_size(maximum_count, size);
	struct data_array *data = game_state_malloc(name, NULL, bytes);

	data_initialize(data, name, maximum_count, size);
	return data;
}

struct memory_pool *memory_pool_new(char const *name, long size)
{
	(void)name;
	(void)size;
	pathsmooth_fail("memory_pool_new");
	return NULL;
}

struct memory_pool *game_state_memory_pool_new(const char *name, long size)
{
	static int dummy;

	(void)name;
	(void)size;
	return (struct memory_pool *)&dummy;
}

boolean game_in_editor(void)
{
	return FALSE;
}

boolean network_game_distributed_client(void)
{
	return FALSE;
}

void encounterless_attach_actor(long actor_index)
{
	/* ai_globals is not a field path_state_build_path reads. The real
	   encounterless_attach_actor only links the actor when that global says
	   the map is initialized; actor_attach_unit has already stored unit_index
	   by the time smoothing runs. Match the step8 record: the flag the real
	   function sets, without inventing an encounter list. */
	actor_get(actor_index)->meta.encounterless = TRUE;
}

void cluster_partition_new(struct cluster_partition *partition, char const *name)
{
	(void)partition;
	(void)name;
}

void cluster_partition_make_valid(struct cluster_partition *partition)
{
	(void)partition;
}

void first_person_legs_reset(void) {}
void damage_initialize(void) {}
void damage_initialize_for_new_map(void) {}
void widgets_initialize(void) {}
void widgets_initialize_for_new_map(void) {}
void object_types_initialize(void) {}
void object_types_initialize_for_new_map(void) {}
void lights_initialize(void) {}
void lights_initialize_for_new_map(void) {}

static void *pathsmooth_object(long object_index, unsigned long valid_type_flags, int missing_is_null)
{
	if (object_index == pathsmooth_unit_index &&
		(valid_type_flags == _object_mask_all ||
			TEST_FLAG(valid_type_flags, pathsmooth_biped.object.type)))
		return &pathsmooth_biped;
	if (missing_is_null)
		return NULL;
	fprintf(stderr, "BLOCKED object_get_and_verify_type index=%ld mask=%08lx\n",
		object_index, valid_type_flags);
	exit(3);
}

void *object_get_and_verify_type(long object_index, unsigned long valid_type_flags)
{
	return pathsmooth_object(object_index, valid_type_flags, FALSE);
}

void *object_try_and_get_and_verify_type(long object_index, unsigned long valid_type_flags)
{
	return pathsmooth_object(object_index, valid_type_flags, TRUE);
}

void *tag_get(long group_tag, long tag_index)
{
	if (group_tag == ACTOR_VARIANT_DEFINITION_TAG && tag_index == PATHSMOOTH_VARIANT_INDEX)
		return &pathsmooth_variant;
	if (group_tag == ACTOR_DEFINITION_TAG && tag_index == PATHSMOOTH_DEFINITION_INDEX)
		return &pathsmooth_definition;
	if (group_tag == UNIT_DEFINITION_TAG && tag_index == PATHSMOOTH_UNIT_DEFINITION_INDEX)
		return &pathsmooth_unit_definition;
	fprintf(stderr, "BLOCKED tag_get group=%08lx index=%ld\n",
		(unsigned long)group_tag, tag_index);
	exit(3);
}

short __wrap_objects_in_sphere(
	unsigned long class_flags,
	unsigned long type_flags,
	struct location const *location,
	real_point3d const *center,
	real radius,
	long *object_indices,
	short maximum_count)
{
	short count = __real_objects_in_sphere(
		class_flags, type_flags, location, center, radius, object_indices, maximum_count);

	pathsmooth_sphere_calls++;
	pathsmooth_sphere_last = count;
	pathsmooth_sphere_cluster = location ? location->cluster_index : (short)0x7fff;
	return count;
}

static real_point3d pathsmooth_surface_center(struct collision_bsp const *bsp, long surface_index)
{
	struct collision_surface const *surface = TAG_BLOCK_GET_ELEMENT(
		&bsp->surfaces, surface_index, struct collision_surface);
	long edge_index = surface->first_edge_index;
	real_point3d center = {0, 0, 0};
	int count = 0;
	int edge_number;

	for (edge_number = 0; edge_number < MAXIMUM_EDGES_PER_COLLISION_SURFACE; edge_number++)
	{
		struct collision_edge const *edge;
		struct collision_vertex const *vertex;
		boolean right;

		if (!VALID_INDEX(edge_index, bsp->edges.count))
			break;
		edge = TAG_BLOCK_GET_ELEMENT(&bsp->edges, edge_index, struct collision_edge);
		if (!VALID_INDEX(edge->vertex_indices[0], bsp->vertices.count) ||
			!VALID_INDEX(edge->vertex_indices[1], bsp->vertices.count))
			break;
		right = (surface_index == edge->surface_indices[1]);
		vertex = TAG_BLOCK_GET_ELEMENT(
			&bsp->vertices, edge->vertex_indices[right], struct collision_vertex);
		center.x += vertex->point.x;
		center.y += vertex->point.y;
		center.z += vertex->point.z;
		count++;
		edge_index = edge->edge_indices[right];
		if (edge_index == surface->first_edge_index)
			break;
	}
	if (count < 3)
		pathsmooth_fail("pathsmooth_surface_center count");
	center.x /= (real)count;
	center.y /= (real)count;
	center.z /= (real)count;
	return center;
}

static void pathsmooth_prepare_unit(real_point3d const *position)
{
	short weapon;

	memset(&pathsmooth_biped, 0, sizeof(pathsmooth_biped));
	pathsmooth_biped.definition_index = PATHSMOOTH_UNIT_DEFINITION_INDEX;
	pathsmooth_biped.object.type = _object_type_biped;
	pathsmooth_biped.object.position = *position;
	pathsmooth_biped.object.bounding_sphere_center = *position;
	pathsmooth_biped.object.location.leaf_index = NONE;
	pathsmooth_biped.object.location.cluster_index = NONE;
	pathsmooth_biped.object.parent_object_index = NONE;
	pathsmooth_biped.object.first_child_object_index = NONE;
	pathsmooth_biped.object.next_object_index = NONE;
	pathsmooth_biped.unit.actor_index = NONE;
	pathsmooth_biped.unit.swarm_actor_index = NONE;
	pathsmooth_biped.unit.player_index = NONE;
	for (weapon = 0; weapon < MAXIMUM_WEAPONS_PER_UNIT; weapon++)
		pathsmooth_biped.unit.weapon_object_indices[weapon] = NONE;
}

static void pathsmooth_print_chain(int run, struct path_state *state)
{
	short chain[64];
	short node;
	int count = 0;
	int index;

	node = path_node_from_hash_table(state, state->destination.surface_index);
	while (node != NONE && count < 64)
	{
		chain[count++] = (short)state->node_list[node].surface_index;
		node = state->node_list[node].parent_node_index;
	}
	printf("CHAIN run=%d n=%d", run, count);
	for (index = count - 1; index >= 0; index--)
		printf(" %d", (int)chain[index]);
	printf("\n");
}

static void pathsmooth_print_steps(int run, char const *kind, int count, struct path_step const *steps)
{
	int index;

	printf("%s run=%d n=%d\n", kind, run, count);
	for (index = 0; index < count; index++)
		printf("POINT %s run=%d i=%d surface=%ld x=%.9g y=%.9g z=%.9g\n",
			kind, run, index, steps[index].surface_index,
			steps[index].point.x, steps[index].point.y, steps[index].point.z);
}

static int pathsmooth_run(
	int run,
	struct path_input const *input,
	real_point3d const *goal,
	long goal_surface,
	struct path_result *result)
{
	struct path_state *state = calloc(1, sizeof(*state));
	struct path_debug_storage *debug = calloc(1, sizeof(*debug));
	boolean found;
	boolean built;

	if (!state || !debug)
		pathsmooth_fail("path_state allocation");
	printf("FIND begin run=%d\n", run);
	fflush(stdout);
	path_state_new(input, state, debug);
	path_state_destination(state, goal, goal_surface, 0.0f);
	found = path_state_find(state);
	printf("FIND end run=%d found=%d nodes=%d\n", run, found ? 1 : 0, (int)state->node_count);
	fflush(stdout);
	if (!found)
	{
		free(debug);
		free(state);
		return 4;
	}
	pathsmooth_print_chain(run, state);
	built = path_state_build_path(state, result);
	printf("BUILD run=%d built=%d valid=%d steps=%d finish=%d result=%d raw=%d smoothed=%d avoided=%d\n",
		run, built ? 1 : 0, result->valid ? 1 : 0, (int)result->step_count,
		result->steps_finish_path ? 1 : 0,
		debug->path_build_result, (int)debug->raw_step_count,
		(int)debug->smoothed_step_count, (int)debug->avoided_step_count);
	pathsmooth_print_steps(run, "RESULT", result->step_count, result->steps);
	pathsmooth_print_steps(run, "RAW", debug->raw_step_count, debug->raw_steps);
	pathsmooth_print_steps(run, "SMOOTHED", debug->smoothed_step_count, debug->smoothed_steps);
	{
		struct collision_bsp const *bsp = TAG_BLOCK_GET_ELEMENT(
			&global_structure_bsp->collision_bsp, 0, struct collision_bsp);
		int index;

		for (index = 0; index < result->step_count; index++)
		{
			real_point2d point2d;

			point2d.x = result->steps[index].point.x;
			point2d.y = result->steps[index].point.y;
			printf("CE_TEST2D run=%d i=%d surface=%ld cw_z=%d\n",
				run, index, result->steps[index].surface_index,
				collision_surface_test_point2d(
					bsp,
					result->steps[index].surface_index,
					_z,
					TRUE,
					&point2d) ? 1 : 0);
		}
	}
	fflush(stdout);
	free(debug);
	free(state);
	return built && result->valid ? 0 : 5;
}

int main(int argc, char **argv)
{
	FILE *input;
	unsigned int counts[7];
	byte *surfaces;
	byte *edges;
	byte *vertices;
	byte *planes;
	byte *flags;
	byte *shadow_surfaces;
	byte *shadow_edges;
	byte *shadow_vertices;
	byte *shadow_planes;
	byte *shadow_flags;
	struct structure_bsp structure_bsp;
	struct collision_bsp collision_bsp;
	real_point3d start_point;
	real_point3d goal_point;
	struct path_input path_input;
	struct path_result first;
	struct path_result second;
	long actor_index;
	struct actor_datum *actor;
	struct object_header_datum *header;
	short depth_before;
	short users_before[MAXIMUM_COLLISION_USER_STACK_DEPTH];
	byte breakable_before[32];
	int first_status;
	int second_status;

	setvbuf(stdout, NULL, _IOLBF, 0);
	if (argc != 2)
		return 2;
	input = fopen(argv[1], "rb");
	if (!input || fread(counts, sizeof(counts), 1, input) != 1)
		return 10;
	if (counts[0] == 0 || counts[0] > 200000 || counts[1] > 400000 ||
		counts[2] > 200000 || counts[3] > 200000 || counts[4] != counts[0])
		return 11;
	surfaces = malloc((size_t)counts[0] * 12);
	edges = malloc((size_t)counts[1] * 24);
	vertices = malloc((size_t)counts[2] * 16);
	planes = malloc((size_t)counts[3] * 16);
	flags = malloc(counts[4]);
	if (!surfaces || !edges || !vertices || !planes || !flags)
		return 12;
	if (fread(surfaces, 12, counts[0], input) != counts[0] ||
		fread(edges, 24, counts[1], input) != counts[1] ||
		fread(vertices, 16, counts[2], input) != counts[2] ||
		fread(planes, 16, counts[3], input) != counts[3] ||
		fread(flags, 1, counts[4], input) != counts[4])
		return 13;
	fclose(input);
	shadow_surfaces = malloc((size_t)counts[0] * 12);
	shadow_edges = malloc((size_t)counts[1] * 24);
	shadow_vertices = malloc((size_t)counts[2] * 16);
	shadow_planes = malloc((size_t)counts[3] * 16);
	shadow_flags = malloc(counts[4]);
	if (!shadow_surfaces || !shadow_edges || !shadow_vertices || !shadow_planes || !shadow_flags)
		return 12;
	memcpy(shadow_surfaces, surfaces, (size_t)counts[0] * 12);
	memcpy(shadow_edges, edges, (size_t)counts[1] * 24);
	memcpy(shadow_vertices, vertices, (size_t)counts[2] * 16);
	memcpy(shadow_planes, planes, (size_t)counts[3] * 16);
	memcpy(shadow_flags, flags, counts[4]);

	memset(&collision_bsp, 0, sizeof(collision_bsp));
	memset(&structure_bsp, 0, sizeof(structure_bsp));
	collision_bsp.bsp3d.planes.count = (long)counts[3];
	collision_bsp.bsp3d.planes.address = planes;
	collision_bsp.surfaces.count = (long)counts[0];
	collision_bsp.surfaces.address = surfaces;
	collision_bsp.edges.count = (long)counts[1];
	collision_bsp.edges.address = edges;
	collision_bsp.vertices.count = (long)counts[2];
	collision_bsp.vertices.address = vertices;
	structure_bsp.collision_bsp.count = 1;
	structure_bsp.collision_bsp.address = &collision_bsp;
	structure_bsp.pathfinding_surfaces.count = (long)counts[4];
	structure_bsp.pathfinding_surfaces.address = flags;
	global_structure_bsp = &structure_bsp;
	global_collision_bsp = &collision_bsp;
	global_structure_bsp_index = 0;
	global_current_collision_user_depth = 1;
	global_current_collision_users[0] = 1;
	depth_before = global_current_collision_user_depth;
	memcpy(users_before, global_current_collision_users, sizeof(users_before));

	actor_debug_array = calloc(MAXIMUM_NUMBER_OF_ACTORS, sizeof(*actor_debug_array));
	if (!actor_debug_array)
		pathsmooth_fail("actor_debug_array");
	memset(&pathsmooth_definition, 0, sizeof(pathsmooth_definition));
	pathsmooth_definition.type = 0;
	pathsmooth_definition.flags = 0;
	pathsmooth_definition.moving.pathfinding_radius = 0.f;
	pathsmooth_definition.moving.glass_ignorance_chance = 0.f;
	memset(&pathsmooth_variant, 0, sizeof(pathsmooth_variant));
	pathsmooth_variant.actor_reference.group_tag = ACTOR_DEFINITION_TAG;
	pathsmooth_variant.actor_reference.index = PATHSMOOTH_DEFINITION_INDEX;
	memset(&pathsmooth_unit_definition, 0, sizeof(pathsmooth_unit_definition));

	game_connection_set(_game_connection_local);
	objects_initialize();
	objects_initialize_for_new_map();
	actors_initialize();
	actors_initialize_for_new_map();
	breakable_surfaces_initialize();
	breakable_surfaces_initialize_for_new_map();
	memcpy(breakable_before, breakable_surface_flags_get(), sizeof(breakable_before));

	pathsmooth_unit_index = datum_new_at_index(object_header_data, (0x8001L << 16) | 7);
	if (pathsmooth_unit_index == NONE)
		pathsmooth_fail("datum_new_at_index object_header");
	header = object_header_get(pathsmooth_unit_index);
	header->type = _object_type_biped;
	header->datum = (struct object_datum *)&pathsmooth_biped;

	start_point = pathsmooth_surface_center(&collision_bsp, (long)counts[5]);
	goal_point = pathsmooth_surface_center(&collision_bsp, (long)counts[6]);
	pathsmooth_prepare_unit(&start_point);
	actor_index = actor_create_for_unit(
		FALSE, pathsmooth_unit_index, PATHSMOOTH_VARIANT_INDEX,
		NONE, NONE, FALSE, NONE, FALSE, 1, 2, NONE, NONE);
	if (actor_index == NONE)
		pathsmooth_fail("actor_create_for_unit");
	actor = actor_get(actor_index);
	if (actor->meta.unit_index != pathsmooth_unit_index)
		pathsmooth_fail("actor_attach_unit meta.unit_index");
	actor->input.pathfinding_point = start_point;
	actor->input.pathfinding_surface_index = (long)counts[5];
	actor_path_input_new(actor_index, &path_input);
	if (path_input.ignore_source_object_index != actor->meta.unit_index)
		pathsmooth_fail("actor_path_input_new ignore_source_object_index");
	if (actor->input.vehicle_driver_type != _actor_vehicle_driver_none)
		pathsmooth_fail("actor_input.vehicle_driver_type");
	if (pathsmooth_biped.object.location.cluster_index != NONE)
		pathsmooth_fail("object.location.cluster_index");

	printf("IDENTITY actor=%ld unit=%ld ignore_source=%ld cluster=%d radius=%.9g ignorant=%d driver=%d connection=%d smooth_off=%d avoid_off=%d\n",
		actor_index, pathsmooth_unit_index, path_input.ignore_source_object_index,
		(int)pathsmooth_biped.object.location.cluster_index,
		path_input.pathfinding_radius,
		path_input.ignore_broken_surfaces ? 1 : 0,
		(int)actor->input.vehicle_driver_type,
		(int)game_connection(),
		ai_debug.path_disable_smoothing ? 1 : 0,
		ai_debug.path_disable_obstacle_avoidance ? 1 : 0);
	printf("ROUTE start=%u goal=%u start_xyz=%.9g %.9g %.9g goal_xyz=%.9g %.9g %.9g\n",
		counts[5], counts[6],
		start_point.x, start_point.y, start_point.z,
		goal_point.x, goal_point.y, goal_point.z);
	fflush(stdout);

	memset(&first, 0, sizeof(first));
	memset(&second, 0, sizeof(second));
	first_status = pathsmooth_run(0, &path_input, &goal_point, (long)counts[6], &first);
	second_status = pathsmooth_run(1, &path_input, &goal_point, (long)counts[6], &second);
	printf("SPHERE calls=%d last=%d cluster=%d\n",
		pathsmooth_sphere_calls, pathsmooth_sphere_last, (int)pathsmooth_sphere_cluster);
	printf("BSP_UNCHANGED %d\n",
		memcmp(shadow_surfaces, surfaces, (size_t)counts[0] * 12) == 0 &&
		memcmp(shadow_edges, edges, (size_t)counts[1] * 24) == 0 &&
		memcmp(shadow_vertices, vertices, (size_t)counts[2] * 16) == 0 &&
		memcmp(shadow_planes, planes, (size_t)counts[3] * 16) == 0 &&
		memcmp(shadow_flags, flags, counts[4]) == 0);
	printf("BREAKABLE_UNCHANGED %d\n",
		memcmp(breakable_before, breakable_surface_flags_get(), sizeof(breakable_before)) == 0);
	printf("COLLISION_DEPTH %d %d users=%d\n",
		(int)depth_before, (int)global_current_collision_user_depth,
		memcmp(users_before, global_current_collision_users, sizeof(users_before)) == 0);
	printf("DETERMINISTIC %d\n", memcmp(&first, &second, sizeof(first)) == 0);
	printf("STATUS %d %d\n", first_status, second_status);
	fflush(stdout);
	if (first_status || second_status)
		return first_status ? first_status : second_status;
	if (pathsmooth_sphere_last != 0 || pathsmooth_sphere_cluster != NONE)
		return 6;
	if (memcmp(&first, &second, sizeof(first)) != 0)
		return 6;
	if (memcmp(shadow_surfaces, surfaces, (size_t)counts[0] * 12) != 0 ||
		memcmp(shadow_edges, edges, (size_t)counts[1] * 24) != 0 ||
		memcmp(shadow_vertices, vertices, (size_t)counts[2] * 16) != 0 ||
		memcmp(shadow_planes, planes, (size_t)counts[3] * 16) != 0 ||
		memcmp(shadow_flags, flags, counts[4]) != 0)
		return 6;
	if (global_current_collision_user_depth != depth_before ||
		memcmp(users_before, global_current_collision_users, sizeof(users_before)) != 0)
		return 6;
	return 0;
}
