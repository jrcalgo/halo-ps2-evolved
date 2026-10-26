/* C4 live-pathfinding link layer. The real CE translation units (path.c, path_smoothing.c,
 * path_structure_bsp.c, path_obstacle_avoidance.c, path_obstacles.c, collision slice, real_math.c)
 * are linked unchanged. This file supplies only DATA for the accessors those units read
 * (scenario BSP pointers, one scenery object with a pathfinding sphere, the breakable bit vector,
 * debug switches) and aborts the test if any other stubbed symbol is reached. */
#include "cseries/cseries.h"
#include "ai/path.h"
#include "ai/ai_debug.h"
#include "objects/objects.h"
#include "objects/object_definitions.h"
#include "physics/collision_model_definitions.h"
#include "physics/collision_bsp_definitions.h"
#include "structures/structure_bsp_definitions.h"
#include "tag_files/tag_groups.h"
#include "physics/breakable_surfaces.h"
#include "game/game.h"
#include "physics/collision_usage.h"
#include "ai/actor_definitions.h"
#include "units/bipeds.h"
#include "units/biped_definitions.h"
#include "scenario/scenario.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- host-owned scenario data, defined by the driver ---- */
extern struct structure_bsp *c4_structure;
extern struct collision_bsp *c4_collision;
extern byte *c4_breakable_flags;
#define C4_MAX_OBJECTS 16
extern struct object_datum c4_objects[C4_MAX_OBJECTS];
extern long c4_object_list[C4_MAX_OBJECTS];
extern struct biped_datum c4_unit_biped;
extern short c4_object_count_in_sphere;
extern struct object_definition c4_object_defs[C4_MAX_OBJECTS];
extern struct actor_definition c4_actor_definition;
struct biped_datum c4_unit_biped;
struct biped_definition c4_biped_definition;
extern struct collision_model c4_collision_models[C4_MAX_OBJECTS];
struct actor_definition c4_actor_definition;

static void c4_stub_abort(const char *name)
{
	fprintf(stderr, "c4 stub reached: %s\n", name);
	abort();
}

/* ---- data suppliers ---- */
struct structure_bsp *global_structure_bsp_get(void) { return c4_structure; }
struct collision_bsp *global_collision_bsp_get(void) { return c4_collision; }
short global_structure_bsp_index_get(void) { return 0; }
byte *breakable_surface_flags_get(void) { return c4_breakable_flags; }
short game_connection(void) { return _game_connection_local; }
boolean console_is_active(void) { return FALSE; }
boolean input_key_is_down(short key_code) { (void)key_code; return FALSE; }
struct ai_debug_state ai_debug;
real_point3d debug_obstacle_path_start_point;
long debug_obstacle_path_start_surface_index;
real_point3d debug_obstacle_path_goal_point;
long debug_obstacle_path_goal_surface_index;
real debug_obstacle_path_radius;
boolean debug_obstacle_path_finishing;
boolean debug_ignore_broken_surfaces;
const union real_argb_color *global_real_argb_red;
const union real_argb_color *global_real_argb_green;
const union real_argb_color *global_real_argb_white;
const union real_argb_color *global_real_argb_yellow;

void *tag_get(long group_tag, long tag_index)
{
	(void)tag_index;
	if (group_tag == OBJECT_DEFINITION_TAG) {
		if (tag_index < 0 || tag_index >= C4_MAX_OBJECTS) c4_stub_abort("object definition index");
		return &c4_object_defs[tag_index];
	}
	if (group_tag == 'coll') {
		if (tag_index < 0 || tag_index >= C4_MAX_OBJECTS) c4_stub_abort("collision model index");
		return &c4_collision_models[tag_index];
	}
	if (group_tag == ACTOR_DEFINITION_TAG) return &c4_actor_definition;
	if (group_tag == BIPED_DEFINITION_TAG) return &c4_biped_definition;
	fprintf(stderr, "c4 tag_get group 0x%lx index %ld\n", (unsigned long)group_tag, (long)tag_index);
	c4_stub_abort("tag_get");
	return NULL;
}
/* unit 0 is a biped: its datum shares the object datum's prefix (definition_index, object) */
void *object_get_and_verify_type(long object_index, unsigned long type_mask)
{
	(void)type_mask;
	if (object_index < 0 || object_index >= C4_MAX_OBJECTS) c4_stub_abort("object_get_and_verify_type");
	if (object_index == 0) return &c4_unit_biped;
	return &c4_objects[object_index];
}
void *object_try_and_get_and_verify_type(long object_index, unsigned long type_mask)
{
	if (object_index < 0 || object_index >= C4_MAX_OBJECTS) return NULL;
	return object_get_and_verify_type(object_index, type_mask);
}
short objects_in_sphere(unsigned long class_flags, unsigned long type_flags, struct location const *location,
	real_point3d const *center, real radius, long *object_indices, short maximum_count)
{
	(void)class_flags; (void)type_flags; (void)location; (void)center; (void)radius;
	long k;
	(void)location;
	if (c4_object_count_in_sphere > maximum_count) c4_stub_abort("objects_in_sphere");
	for (k = 0; k < c4_object_count_in_sphere; k++) object_indices[k] = c4_object_list[k];   /* list[0] is the unit */
	return c4_object_count_in_sphere;
}
real_matrix4x3 *object_get_world_matrix(long object_index, real_matrix4x3 *matrix)
{
	struct object_datum const *object = (struct object_datum const *)object_get_and_verify_type(object_index, 0);
	matrix->scale = 1.0f;
	matrix->forward.i = 1.0f; matrix->forward.j = 0.0f; matrix->forward.k = 0.0f;
	matrix->left.i = 0.0f; matrix->left.j = 1.0f; matrix->left.k = 0.0f;
	matrix->up.i = 0.0f; matrix->up.j = 0.0f; matrix->up.k = 1.0f;
	matrix->position = object->object.bounding_sphere_center;
	return matrix;
}

/* ---- diagnostics and byte helpers: no effect on the path results ---- */
void error(short priority, const char *format, ...) { (void)priority; (void)format; }
void console_printf(const char *format, ...) { (void)format; }
char temporary[256];
char *csprintf(char *buffer, char *format, ...)
{
	va_list args;
	va_start(args, format);
	vsnprintf(buffer, 256, format, args);
	va_end(args);
	return buffer;
}
void *csmemset(void *buffer, long c, unsigned long size)
{
	unsigned char *d = buffer; unsigned long k;
	for (k = 0; k < size; k++) d[k] = (unsigned char)c;
	return buffer;
}
void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	unsigned char *d = destination; const unsigned char *src = source; unsigned long k;
	for (k = 0; k < size; k++) d[k] = src[k];
	return destination;
}
unsigned long csstrlen(const char *s1) { unsigned long n = 0; while (s1[n]) n++; return n; }

/* custom-edition tag cache state: the host never loads a cache, so the index-check branch is taken */
boolean custom_edition_cache_tags_loaded(void) { return FALSE; }
/* data referenced only by ai_profile.c printing paths that the driven code never reaches */
struct data_array *actor_data, *swarm_data, *swarm_component_data;
char encounter_data[64], prop_data[64], rasterizer_globals[64];
long csmemcmp(const void *a, const void *b, unsigned long size)
{
	const unsigned char *x = a, *y = b; unsigned long k;
	for (k = 0; k < size; k++) if (x[k] != y[k]) return x[k] < y[k] ? -1 : 1;
	return 0;
}
/* cseries allocator and string wrappers: forwarding to the C library with no CE-side behaviour */
#undef malloc
#undef free
void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *p;
	(void)clear; (void)file; (void)line;
	p = malloc((size_t)size);
	if (!p && size) abort();
	return p;
}
void debug_free(void *ptr, const char *file, long line)
{
	(void)file; (void)line;
	free(ptr);
}
long csstrcmp(const char *s1, const char *s2)
{
	while (*s1 && *s1 == *s2) { s1++; s2++; }
	return (long)((unsigned char)*s1 - (unsigned char)*s2);
}

/* scenario globals read by the whole collision_bsp.c object (scenario/scenario.c defines them in the engine) */
struct collision_bsp *global_collision_bsp;
/* profiling hooks (collision_usage.h): timing counters only, no effect on any result */
void collision_log_start_time(LARGE_INTEGER *start_time) { (void)start_time; }
void collision_log_end_time(short collision_function, __int64 end_time) { (void)collision_function; (void)end_time; }
void collision_log_usage(short collision_function) { (void)collision_function; }
