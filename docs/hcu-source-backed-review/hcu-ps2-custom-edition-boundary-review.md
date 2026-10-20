# M0 rooted Custom Edition cache/BSP boundary review

Thirteen rooted hooks connect CE's cache loader and game to OpenCE's
Custom-Edition cache, map catalogue, geometry and vehicle-placement modules.
They remain pending: the PS2 port currently has generated zero/no-op bodies,
while the parent product direction requires eventual CE-mod compatibility.
The current stock-map boot smoke does not qualify these paths.

## Cache and tag ownership

`cache_file_header_verify` calls `custom_edition_cache_refuse` before Xbox
header/version checks. With a false stub, a CE cache may fall through and be
rejected only by later stock checks, losing the format-specific diagnostic and
selection policy. `scenario_tags_load` calls `custom_edition_level_name` to
choose the CE-prefixed custom-map route; when selected,
`custom_edition_cache_tags_load` must return converted tag-header/tag-instance
state or the CE map is not playable. Native `custom_edition_cache_tags_load`
identifies version-609 cache files, opens separate bitmap/sound resource maps,
loads and validates tag data, converts CE definitions, and only then commits
`tags_loaded`/cache state. A null body is not that loader.

The `custom_edition_cache_tags_loaded` predicate branches several shared CE
paths: cache-file reads, tag block/data pointer resolution, reference checking,
game-engine behavior, HUD bitmap flags, and BSP load/unload. Returning false
selects the stock Xbox layout; returning true is only valid after the converted
cache is fully owned and validated. Its unload counterpart must dispose BSP,
bitmap/model/sound conversions and file resources before clearing the cache
state. The PS2 must eventually give that converted tag cache bounded memory,
alignment, file-reader and lifetime owners that fit the EE budget.

## BSP and vehicle consequences

For CE maps, the native `custom_edition_structure_bsp_reference_valid`
checks the reference's file interval and destination against the CE tag-cache
range (BSP bytes load above converted tag data). The load/unload functions
materialize and release converted BSP geometry. A false validator or no-op
geometry adapter cannot establish a usable CE BSP.

There is also an immediate stock-parity defect in the current PS2 stubs:
`object_types_place_all` skips a vehicle when
`custom_edition_vehicle_placement_allowed(placement)` returns false. The
native contract returns true for non-CE maps (`!custom_edition_vehicles_by_placement()`),
then applies placement spawn flags only when a CE cache is active. The PS2
generated `custom_edition_vehicle_placement_allowed` returns false, so the
current implementation suppresses ordinary stock vehicle placements too.
This is gameplay state, not merely future CE map support. It needs a stock-map
vehicle-placement fixture and a state adapter that preserves the CE fallback
contract before M0 can disposition it.

`custom_edition_vehicles_by_placement` controls `game_engine_remap_vehicle`:
true preserves a CE map's map-defined vehicle set; false uses stock Xbox game
variant remapping. The paired placement predicate applies CE multiplayer
spawn flags. The map-name/description functions are catalogue presentation
calls, but their display indices and returned storage still require a defined
PS2 catalogue/fallback contract.

## Disposition and acceptance

All thirteen ledger entries stay pending. Do not exclude them as “Custom
Edition-only”: their integration includes shared loader branches, and the
vehicle-placement stub is already observably wrong for stock maps. Before
approval or implementation, qualify (1) stock-map header handling and vehicle
placement, (2) a CE cache/tag/resource fixture including malformed input and
unload, (3) CE BSP address bounds/materialization, (4) game-mode vehicle spawn
flags/remapping, and (5) map name/description fallback. The CE cache's memory
owner and peak working set must be measured before choosing its pool size.

Regression anchor:
`tests/test_hcu_external_review.py::test_custom_edition_cache_and_bsp_hooks_remain_pending`.
