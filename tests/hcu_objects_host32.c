/*
 * Include the pinned CE object unit for the isolated player-PVS fixture.
 * This exposes the real object header lookup and parent-chain traversal while
 * matching CE's MSVC-style external inline semantics on the host ILP32 build.
 */
#undef __inline
#define __inline __inline__
#define object_get_and_verify_type hcu_ce_object_get_and_verify_type
#define objects_get_activating_cluster_index hcu_ce_objects_get_activating_cluster_index
#define cluster_get_first_collideable_object hcu_ce_cluster_get_first_collideable_object
#define cluster_get_next_collideable_object hcu_ce_cluster_get_next_collideable_object
#define object_marker_begin hcu_ce_object_marker_begin
#define object_marker_end hcu_ce_object_marker_end
#define object_mark_function hcu_ce_object_mark_function
#define objects_disconnect_from_structure_bsp hcu_ce_objects_disconnect_from_structure_bsp
#define objects_reconnect_to_structure_bsp hcu_ce_objects_reconnect_to_structure_bsp
#include "../submodules/halo-ce-universal/source/objects/objects.c"

unsigned hcu_test_real_object_lookup_count;

void *hcu_test_real_object_get_and_verify_type(
	long object_index,
	unsigned long valid_type_flags)
{
	++hcu_test_real_object_lookup_count;
	return hcu_ce_object_get_and_verify_type(object_index, valid_type_flags);
}
