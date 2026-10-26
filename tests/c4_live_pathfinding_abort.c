/* C4 link layer: abort-only stubs. Declared without the CE headers on purpose; any call is
 * outside the driven paths and fails the test. Kept header-free so signatures need no match. */
#include <stdio.h>
#include <stdlib.h>

static void c4_abort_stub(const char *name)
{
	fprintf(stderr, "c4 stub reached: %s\n", name);
	abort();
}

/* ---- harness-owned, not expected on any driven path: abort if reached ---- */
#define C4_ABORT(name) void name(void) { c4_abort_stub(#name); }
C4_ABORT(object_get_node_matrix)
C4_ABORT(render_debug_circle)
C4_ABORT(render_debug_line)
C4_ABORT(render_debug_point)
C4_ABORT(render_debug_sphere)

C4_ABORT(system_exit)
C4_ABORT(_control87)
C4_ABORT(rasterizer_draw_string)
C4_ABORT(draw_string_set_color)
C4_ABORT(draw_string_set_tab_stops)
C4_ABORT(interface_set_bitmap_text_draw_mode)
C4_ABORT(actor_iterator_new)
C4_ABORT(actor_iterator_next)
C4_ABORT(observer_get_camera)
C4_ABORT(unit_get_head_position)
C4_ABORT(periodic_functions_initialize)
C4_ABORT(periodic_functions_dispose)
C4_ABORT(random_math_initialize)
C4_ABORT(random_math_dispose)
C4_ABORT(actor_action_debug_color)
C4_ABORT(actor_activation_debug_color)

C4_ABORT(tag_index_error)
/* report the failing CE match_assert location; then abort (the assert is a real CE failure) */
void display_assert(const char *expression, const char *file, long line, int fatal)
{
	(void)fatal;
	fprintf(stderr, "c4 CE assertion: %s:%ld: %s\n", file ? file : "?", (long)line, expression ? expression : "?");
	abort();
}
C4_ABORT(actor_action_deny_transition)
C4_ABORT(actor_clear_discarded_firing_positions)
C4_ABORT(actor_perception_find_prop_pathfinding_location)
C4_ABORT(actor_set_dormant)
C4_ABORT(actor_type_swarm_aim_jump)
C4_ABORT(actor_unit_control_crouch)
C4_ABORT(actor_unit_control_jump)
C4_ABORT(actor_unit_control_stop_animation_impulse)
C4_ABORT(ai_communication_event)
C4_ABORT(ai_debug_describe_actor)
C4_ABORT(biped_build_flying_axes)
C4_ABORT(get_global_random_seed_address)
C4_ABORT(global_scenario_get)
C4_ABORT(point_from_line3d)
C4_ABORT(seed_random)
C4_ABORT(unit_is_busy)
C4_ABORT(unit_leap_begin)
C4_ABORT(valid_real_normal2d)
C4_ABORT(vehicle_find_pathfinding_surface_index)
C4_ABORT(vehicle_stuck)
C4_ABORT(collision_test_vector)
