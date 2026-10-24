/*
 * Include the pinned CE player unit in this test-only translation unit so
 * the fixture can call its otherwise-static PVS aggregation routine.  The
 * linker keeps only that routine and its direct dependencies.
 */
/* This TU includes several CE headers whose external-inline prototypes are
 * paired with linux_msvc_semantics' weak COMDAT pragmas. Expose those inlines
 * with external linkage (as CE's MSVC build does) for this isolated TU. */
#undef __inline
#define __inline __inline__
#define players_reconnect_to_structure_bsp players_reconnect_to_structure_bsp_ce
#include "../submodules/halo-ce-universal/source/game/players.c"
#undef players_reconnect_to_structure_bsp

/* This slice deliberately fixes environmental inputs to ordinary local-game
 * mode with no PVS activation owner.  It does not replace player iteration,
 * PVS row access, or vector aggregation. */
boolean game_in_editor(void)
{
	return FALSE;
}

short objects_get_activating_cluster_index(void)
{
	return NONE;
}

void hcu_test_players_compute_combined_pvs(
	unsigned long *combined_pvs,
	boolean local_player_only)
{
	players_compute_combined_pvs(combined_pvs, local_player_only);
}
