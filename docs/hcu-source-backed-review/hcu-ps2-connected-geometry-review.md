# M0 source review: connected geometry used by structure lens flares

## Scope and disposition

Four rooted helpers remain pending: `connected_geometry_new`, `connected_geometry_add_triangle`, `connected_geometry_group_coplanar`, and `connected_geometry_delete`. Although classified as an excluded tool feature, their only rooted caller is CE's structure-lens-flare builder and that routine mutates BSP tag data. The classification alone does not establish an offline-only boundary.

## Source trace

`source/structures/structure_lens_flares.c:321-343` creates a connected-geometry accumulator per material, adds each BSP surface triangle from the material's uncompressed vertex data, then groups coplanar triangles. The returned group count controls the subsequent loop that derives projected convex hulls and flare-marker placements. The builder clears and repopulates `structure_bsp->lens_flares` and `lens_flare_markers` using tag-block mutation, and it finally deletes temporary geometry (`structure_lens_flares.c:565`). Therefore `add_triangle`/`group_coplanar` are not ignorable drawing helpers: they participate in material/BSP-derived lens-flare data.

`source/tool/connected_geometry.c:117-149` initializes and releases dynamic arrays for vertices, edges, and triangles. `connected_geometry_add_triangle` (346-405) adds/deduplicates vertices and edges, updates triangle adjacency, and can report failure. `connected_geometry_group_coplanar` (546 onward) classifies/groups triangles through recursive edge traversal; its return count is consumed by the BSP-building loop. A no-op constructor/add/group can leave invalid/empty state, while a no-op delete can retain temporary storage.

The checked-out CE source only shows `structure_lens_flares_place` calling `build_structure_lens_flares`; no other in-tree caller was found. The root closure nevertheless includes the path. The migration audit must establish whether the PS2 runtime invokes it after a cache load, whether lens-flare markers are instead baked by the offline HP2 conversion, and who owns scratch allocation. This is also a PS2 memory-budget concern: the function allocates large projected-point/point/hull scratch arrays and connected-geometry dynamic arrays. Do not let the Xbox heap behavior cross the map-load boundary unchecked.

## Required follow-up

Keep all four rows pending until the integrated owner is located and one of these is evidenced: (a) the PS2 pack builder bakes equivalent lens-flare markers and runtime never calls the CE builder, or (b) the builder is ported to bounded PS2 scratch/arena memory and produces CE-equivalent flare groups/markers. Add an input fixture with coplanar and non-coplanar triangles, adjacency cases, allocation failure, and resulting marker order/count. The source-integrity test below intentionally does not claim those behavior fixtures are implemented.
