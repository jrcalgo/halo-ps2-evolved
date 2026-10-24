# M2 Step 7.1 — complete declared BSP member inventory

Date: 2026-10-21. Report-only inventory of the current source checkout. The authoritative plan is [Step 7](../../plans/7.hcu-remake-m2-m4.md). Source trace and retained bytes establish data ownership; individual runtime consumers still need the plan's semantic and target-sized qualification.

## Reading the ledger

**P** means preserve the scalar, inline array, padding, or opaque record bytes. **B** means preserve block count and element bytes, recursively relocate its address according to its schema and preserve/normalize its schema-definition metadata according to the loader contract. **D** means preserve data size/content with its data-address relocation. **T** means process a tag reference through the tag-reference schema; retain group/datum identity and apply the loader's string-pointer convention. **R** means an explicit runtime reset, never evidence of payload removal. These are desired ownership dispositions derived from the schema, not a statement that every loader implementation has passed a whole-image test.

Every named top-level member in the current [structure_bsp declaration](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h:178) is listed below. All nested record members declared there and in its actual BSP schema are enumerated in the next section. Arrays are one declared member with every element retained. Primitive `real_point3d`, plane, rectangle, color, and vector components retain their complete typed byte extent. `tag_block`, `tag_data`, and `tag_reference` metadata require the loader's shared schema rules; their pointer slots are not ordinary scalar bytes.

The shared descriptor members are explicitly: `tag_block` = `count`, `address`, `definition`; `tag_reference` = `group_tag`, `name`, `name_length`, `index`; `tag_data` = `size`, `pad`, `file_offset`, `address`, `definition` ([tag_groups.h:87](../../submodules/halo-ce-universal/source/tag_files/tag_groups.h:87)). Preserve scalar identity/count/extent and opaque padding; address/name/definition slots require their individually specified relocation/reset rule. In particular, a `definition` pointer must not accidentally remain an Xbox address simply because the data address was relocated.

The BSP schema is in [tag_schema_collision.c](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:936), **not** `tag_schema_scenario.c`; the latter registers the scenario's BSP references at [1267](../../submodules/halo-ce-universal/port/linux/game/tag_schema_scenario.c:1267). This distinction matters when checking recursive coverage.

## Every top-level member

| Member | Disposition and exact source consumer/ownership |
|---|---|
| `lightmap_group` | T; bitmap identity for structure materials/lightmaps; [structures.c:523](../../submodules/halo-ce-universal/source/structures/structures.c:523). GS textures belong to the parent pack renderer; CE reference identity remains CE-owned. |
| `vehicle_floor` | P; vehicle vertical constraint, [vehicles.c:2681](../../submodules/halo-ce-universal/source/units/vehicles.c:2681). |
| `vehicle_ceiling` | P; same constraint, [vehicles.c:2682](../../submodules/halo-ce-universal/source/units/vehicles.c:2682). |
| `sad_unused[5]` | P opaque; no semantic reader identified. No removal permission. |
| `default_lighting` | P typed lighting; object fallback copies it, [object_lights.c:2411](../../submodules/halo-ce-universal/source/objects/object_lights.c:2411). |
| `lonely_unused` | P opaque; no reader identified. |
| `collision_materials` | B; shader and material response identity, [collisions.c:290](../../submodules/halo-ce-universal/source/physics/collisions.c:290). |
| `collision_bsp` | B; authoritative CE collision tree, [collisions.c:478](../../submodules/halo-ce-universal/source/physics/collisions.c:478). |
| `nodes` | B byte_rectangle3d records; node bounds used by CPU visibility, [structure_visibility.c:1362](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1362). |
| `world_bounds` | P; CPU visibility bounds, [structure_visibility.c:1588](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1588). |
| `leaves` | B; leaf-to-cluster and surface-reference ranges, [collisions.c:260](../../submodules/halo-ce-universal/source/physics/collisions.c:260), [structure_visibility.c:1362](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1362). |
| `surface_references` | B; CPU visibility surface/node mapping, [structure_visibility.c:1362](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1362). |
| `surfaces` | B; environment triangle indices, distinct from collision surfaces; [structure_bsp_definitions.c:70](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c:70), [structures.c:523](../../submodules/halo-ce-universal/source/structures/structures.c:523). |
| `lightmaps` | B; material lists and bitmap indices, [structures.c:523](../../submodules/halo-ce-universal/source/structures/structures.c:523). |
| `render_unused[3]` | P opaque; no reader identified. |
| `lens_flares` | B; lens tag palette, [structure_lens_flares.c:274](../../submodules/halo-ce-universal/source/structures/structure_lens_flares.c:274); Xbox drawing consumer [rasterizer_lights.c:806](../../submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c:806) is a separate backend. |
| `lens_flare_markers` | B; position/direction/palette byte, [structure_lens_flares.c:577](../../submodules/halo-ce-universal/source/structures/structure_lens_flares.c:577), [rasterizer_lights.c:799](../../submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c:799). |
| `clusters` | B; see expanded cluster record below. |
| `cluster_data` | D; PVS rows, [structure_bsp_definitions.c:20](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c:20), [players.c:1789](../../submodules/halo-ce-universal/source/game/players.c:1789). |
| `cluster_portals` | B; graph/portal geometry for CPU visibility, [structures.c:448](../../submodules/halo-ce-universal/source/structures/structures.c:448), [structure_visibility.c:1072](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1072). |
| `cluster_unused[3]` | P opaque; no reader identified. |
| `breakable_surfaces` | B; breakable lifecycle uses geometry/collision association, [breakable_surfaces.c:287](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.c:287). |
| `fog_planes` | B; region/material/plane and nested vertices, [scenario.c:619](../../submodules/halo-ce-universal/source/scenario/scenario.c:619), [collisions.c:322](../../submodules/halo-ce-universal/source/physics/collisions.c:322). |
| `fog_regions` | B; region palette choices, [scenario.c:619](../../submodules/halo-ce-universal/source/scenario/scenario.c:619). |
| `fog_palette` | B; fog tag identity, [scenario.c:694](../../submodules/halo-ce-universal/source/scenario/scenario.c:694). |
| `fog_unused[6]` | P opaque; no reader identified. |
| `weather_palette` | B; particle/wind references and runtime function indices, [wind.c:350](../../submodules/halo-ce-universal/source/scenario/wind.c:350), [weather_particle_systems.c:457](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c:457). |
| `weather_polyhedra` | B; exclusion bounds/planes, [weather_particle_systems.c:457](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c:457), [weather_particle_systems.c:698](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c:698). |
| `weather_unused[6]` | P opaque; no reader identified. |
| `pathfinding_surfaces` | B bytes indexed by collision surface; [path.c:1205](../../submodules/halo-ce-universal/source/ai/path.c:1205), [path_structure_bsp.c:757](../../submodules/halo-ce-universal/source/ai/path_structure_bsp.c:757), [path_smoothing.c:380](../../submodules/halo-ce-universal/source/ai/path_smoothing.c:380). |
| `pathfinding_edges` | B bytes; schema preserves and validates extent; no direct runtime dereference found by the member search. Retain; do not infer unused from that search. [Schema:967](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:967). |
| `background_sound_palette` | B; loop identity and flags, [scenario.c:515](../../submodules/halo-ce-universal/source/scenario/scenario.c:515), [scenario.c:1310](../../submodules/halo-ce-universal/source/scenario/scenario.c:1310). |
| `sound_environment_palette` | B; listener environment selection, [scenario.c:1310](../../submodules/halo-ce-universal/source/scenario/scenario.c:1310). |
| `sound_cluster_data` | D; packed pair-distance table, [structure_bsp_definitions.c:207](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c:207), [game_sound.c:1054](../../submodules/halo-ce-universal/source/sound/game_sound.c:1054). |
| `sound_unused[6]` | P opaque; no reader identified. |
| `markers` | **P opaque legacy block, special case.** Declared in the header but omitted from the recursive schema. Schema comment explicitly says never read [tag_schema_collision.c:933](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:933). No typed record or runtime dereference owner identified. Preserve its original block/payload bytes; do not claim its raw address is a relocated usable pointer. Any future marker access requires a typed schema and bounds proof first. |
| `detail_object_data` | B; cells/instances/counts/z-reference vectors, [structure_detail_objects.c:426](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c:426), [structure_detail_objects.c:604](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c:604). |
| `runtime_decals` | B; permanent decal reconnect/update, [structure_runtime_decals.c:99](../../submodules/halo-ce-universal/source/structures/structure_runtime_decals.c:99), [structure_runtime_decals.c:151](../../submodules/halo-ce-universal/source/structures/structure_runtime_decals.c:151). |
| `diminishing_misc_unused[2]` | P opaque; no reader identified. |
| `leaf_map` | Inline record: `bsp` R to zero; `leaves`, `portals` B. [Schema:922](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:922). Debug functions that need `bsp` must not run without an explicit owner binding it. |

## Complete nested declared record member lists

All members in each list have P disposition except explicitly annotated B, D, T, or R. Typed overlays are listed because an `unused` byte span in the public header often contains live nested blocks under another CE translation unit's layout.

### Public structure header records

Declarations: [structure_bsp_definitions.h:35](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h:35).

- `structure_leaf`: `bounds`, `pad`, `cluster_index`, `surface_reference_count`, `first_surface_reference_index`. CPU visibility and leaf/cluster collision references above own the meaningful members.
- `structure_surface`: `vertex_indices[NUMBER_OF_VERTICES_PER_TRIANGLE]`. Environment triangles; not interchangeable with `collision_surface`.
- `structure_material`: `shader` T; `permutation_index`, `flags`, `first_surface_index`, `surface_count`, `centroid`, `lighting` (expanded below), `plane`, `breakable_surface_index`, `copious_unused_space`; `vertices`, `lightmap_vertices` (expanded buffer records below); `uncompressed_vertex_data` D; `compressed_vertex_data` D. [Material checks:1340](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1340), [material lookup:70](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c:70), [object lighting:2411](../../submodules/halo-ce-universal/source/objects/object_lights.c:2411). Shader/reference/permutation and source surface intervals remain CE identities; the GS/VU pack is their drawing adapter.
- `structure_lightmap`: `bitmap_index`, `pad`, `unused[4]`, `materials` B. `unused` retains all bytes.
- `structure_cluster_runtime_decals`: `unused[0xC]`, `first_decal_index`, `decal_count`, `unused2[0x58]`. This is an alias of the cluster stride, **not an additional allocation**. [Runtime decals:99](../../submodules/halo-ce-universal/source/structures/structure_runtime_decals.c:99).
- Public `structure_cluster`: `sky_index`, `fog_reference`, `background_sound_palette_index`, `sound_environment_palette_index`, `weather_palette_index`, `unusedA[0x1E]`, `predicted_resources` B, `unused34[0x34]`. The two opaque spans overlap live fields in the complete cluster schema below: they must not be stripped or treated as relocation-free.
- `structure_background_sound_palette_entry`: `unused0[0x20]`, `background_sound` T, `unused30[0x44]`. No additional typed semantics claimed for opaque bytes.
- `structure_sound_environment_palette_entry`: `unused0[0x20]`, `sound_environment` T, `unused30[0x20]`.
- `structure_runtime_decal`: `position`, `palette_index`, `unused`, `yaw`, `pitch`. Palette is the scenario decal palette; angles are packed bytes, not floats. [Update:151](../../submodules/halo-ce-universal/source/structures/structure_runtime_decals.c:151).
- `structure_fog_region`: `unused[0x24]`, `fog_palette_index`, `weather_palette_index`. Opaque bytes retained; palette fields read by [scenario.c:619](../../submodules/halo-ce-universal/source/scenario/scenario.c:619).
- Public `structure_fog_plane`: `region_index`, `runtime_material_type`, `plane`, `unused14[0xC]`. The opaque span is actually the schema's B `vertices` descriptor below; **requires relocation**.
- `structure_fog_palette_entry`: `unused[0x20]`, `fog` T, `unused2[0x58]`.
- `structure_collision_material`: `shader` T, `pad`, `runtime_physics_material_type`. Collision response owns the runtime material; [schema:604](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:604).

### Schema's full cluster, visibility, weather, and effect records

Declarations are together at [tag_schema_collision.c:163](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:163); recursive registrations begin at [686](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:686).

- `structure_cluster_schema` (same 0x68 bytes as public cluster): `sky_index`, `fog_designator`, `background_sound_palette_index`, `sound_environment_palette_index`, `weather_palette_index`, `transition_structure_bsp_index`, `first_runtime_decal_index`, `runtime_decal_count`, `unused[6]`; `predicted_resources` B, `subclusters` B; `first_lens_flare_marker_index`, `lens_flare_marker_count`; `surface_indices` B, `mirrors` B, `portal_indices` B. `fog_designator` aliases `fog_reference`; decal indices alias the runtime-decal overlay. [structures.c:114](../../submodules/halo-ce-universal/source/structures/structures.c:114) independently declares the same full layout. Visibility consumes subclusters/surface/portal/mirror data [structure_visibility.c:455](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:455). Observer precache consumes prediction [observer.c:1215](../../submodules/halo-ce-universal/source/camera/observer.c:1215). No direct runtime consumer of `transition_structure_bsp_index` was established here; preserve it.
- `structure_subcluster`: `world_bounds`, `surface_indices` B. Frustum/box filtering [structure_visibility.c:467](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:467), [1240](../../submodules/halo-ce-universal/source/structures/structure_visibility.c:1240).
- `structure_mirror`: `plane`, `unused[5]`, `shader` T, `points` B (`real_point3d`). CPU visibility mirror geometry retains source plane and polygon identity; renderer replacement alone does not remove this.
- `structure_portal_index`: `portal_index`; short array indexes global cluster portals.
- `structure_cluster_portal`: `cluster_indices[2]`, `plane_index`, `centroid`, `bounding_radius`, `flags`, `unused[6]`, `vertices` B (`real_point3d`). [structures.c:134](../../submodules/halo-ce-universal/source/structures/structures.c:134) confirms layout; visibility graph owns endpoint/plane data.
- `structure_surface_reference`: `surface_index`, `bsp3d_node_index`. CPU visibility and schema's cross-block validation own both.
- `structure_fog_plane_schema`: `region_index`, `runtime_material_type`, `plane`, `vertices` B. Exactly replaces the public header's trailing opaque span.
- `structure_lens_flare`: `lens_flare` T.
- `structure_lens_flare_marker`: `position`, `direction[3]`, `lens_flare_index`; packed direction and byte index retained. CE build/placement can update marker order and cluster ranges [structure_lens_flares.c:622](../../submodules/halo-ce-universal/source/structures/structure_lens_flares.c:622).
- `structure_weather_palette_entry`: `name[32]`, `particle_system` T, `pad30`, `runtime_particle_system_global_function_index`, `particle_system_global_function_name[32]`, `particle_system_unused[11]`, `wind` T, `wind_direction`, `wind_magnitude`, `padA0`, `wind_global_function_index`, `wind_global_function_name[32]`, `wind_unused[11]`. Wind and particle logic own global function resolution and values; opaque arrays retained. [wind.c:350](../../submodules/halo-ce-universal/source/scenario/wind.c:350).
- `structure_weather_polyhedron`: `bounding_sphere_center`, `bounding_sphere_radius`, `unused`, `planes` B (`real_plane3d`). Particle placement/exclusion owns bounds/plane tests [weather_particle_systems.c:457](../../submodules/halo-ce-universal/source/effects/weather_particle_systems.c:457).
- `predicted_resource`: shared schema checks `type`, `tag_index`; its complete declaration also contains `resource_index` ([predicted_resources.h](../../submodules/halo-ce-universal/source/cache/predicted_resources.h:23)); preserve all three, process tag index by schema. Streaming/cache prediction owns resource selection. Do not count it as a duplicate resident resource payload.

### Detail objects and leaf map

Declarations: [tag_schema_collision.c:287](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:287); [leaf_map.h:25](../../submodules/halo-ce-universal/source/structures/leaf_map.h:25).

- `detail_object_cell_definition`: `cell_x`, `cell_y`, `cell_z`, `offset_z`, `valid_layers`, `start_index`, `count_index`, `unused14[3]`. Detail-object cell iteration/instance reconstruction owns meaningful fields [structure_detail_objects.c:604](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c:604).
- `structure_detail_object_data`: `cells` B, `detail_objects` B, `counts` B (`word`), `z_reference_vectors` B (`real_vector4d`), `valid`, `pad31[3]`, `unused34[3]`. Validity remains an authored/runtime field; schema does not reset it. Payload count/range consistency checked at [tag_schema_collision.c:1532](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1532).
- `detail_object`: `position[3]`, `data`, `color`. Packed instance bytes preserved; do not expand them into resident float records without measured capacity.
- `leaf_map`: `bsp` R=0; `leaves` B, `portals` B.
- `map_leaf`: `faces` B, `portal_designators` B (`long`).
- `map_leaf_face`: `node_index`, `vertices` B (`real_point2d`).
- `leaf_portal`: `plane_index`, `leaf_indices[2]`, `vertices` B (`real_point3d`).
- CPU debug consumers: [leaf_map.c:575](../../submodules/halo-ce-universal/source/structures/leaf_map.c:575), [643](../../submodules/halo-ce-universal/source/structures/leaf_map.c:643), [697](../../submodules/halo-ce-universal/source/structures/leaf_map.c:697); drawing entry points [structure_render.c:665](../../submodules/halo-ce-universal/source/structures/structure_render.c:665). A null `leaf_map.bsp` means routines requiring its tree cannot be called merely because leaves/portals exist. This is an explicit runtime-binding prerequisite, not proof these payloads may be removed.

### Collision tree and breakable records

Declarations: [collision_bsp_definitions.h:35](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.h:35), [bsp3d.h:32](../../submodules/halo-ce-universal/source/physics/bsp3d.h:32), [bsp2d.h:30](../../submodules/halo-ce-universal/source/physics/bsp2d.h:30), [schema-local collision records:109](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:109).

- `collision_bsp`: `bsp3d` inline, `leaves` B, `bsp2d_references` B, `bsp2d` inline, `surfaces` B, `edges` B, `vertices` B.
- `bsp3d`: `nodes` B, `planes` B (`real_plane3d`). `bsp3d_node`: `plane_designator`, `children[2]`.
- `collision_leaf`: `flags`, `bsp2d_reference_count`, `first_bsp2d_reference_index`.
- `bsp2d_reference`: `plane_designator`, `root_index`.
- `bsp2d`: `nodes` B. `bsp2d_node`: `plane`, `child_indices[2]`.
- `collision_surface`: `plane_designator`, `first_edge_index`, `flags`, `breakable_surface_index`, `material_index`.
- `collision_edge`: `vertex_indices[2]`, `edge_indices[2]`, `surface_indices[2]`.
- `collision_vertex`: `point`, `first_edge_index`.
- `structure_breakable_surface`: `centroid`, `bounding_radius`, `collision_surface_index`, `unused[7]`; declaration [breakable_surfaces.h:46](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.h:46). Lifecycle/particle emission uses this [breakable_surfaces.c:287](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.c:287), [311](../../submodules/halo-ce-universal/source/physics/breakable_surfaces.c:311).
- Collision traversal owns topology/plane designators and adjacency, [collision_bsp.c](../../submodules/halo-ce-universal/source/physics/collision_bsp.c:1); public query results and material mapping [collisions.c:478](../../submodules/halo-ce-universal/source/physics/collisions.c:478). AI path smoothing independently consumes edge/vertex adjacency [path_smoothing.c:380](../../submodules/halo-ce-universal/source/ai/path_smoothing.c:380). Preserve flags/sign bits and every tree record; renderer topology is a different store.

### Lighting and vertex-buffer inline records

- `render_lighting`: `ambient_color`, `distant_light_count`, `pad`, `distant_lights[MAXIMUM_RENDERED_DISTANT_LIGHTS]`, `point_light_count`, `pad1`, `point_light_indices[MAXIMUM_RENDERED_POINT_LIGHTS]`, `reflection_tint_color`, `shadow_vector`, `shadow_color`. `render_distant_light`: `color`, `direction`. Declarations [render.h:38](../../submodules/halo-ce-universal/source/render/render.h:38); schema bounds checks counts [tag_schema_collision.c:594](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:594). Runtime point-light indices cannot be accepted as serialized valid pointers or a new pool owner.
- `vertex_buffer`: `type`, `pad`, `count`, `offset`, `base_address`, `hardware_format`. Declaration [rasterizer_geometry.h:36](../../submodules/halo-ce-universal/source/rasterizer/rasterizer_geometry.h:36). `hardware_format` is validated through BSP cache buffer tables [tag_schema_collision.c:1272](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1272); Custom Edition input can clear it. `base_address` and `hardware_format` are pointer-shaped backend descriptors; retaining their source bytes does not make them valid EE/GS addresses. Real shader/lightmap CPU sampling and PS2 drawing adapter must provide their own validated source view/pack mapping. No blanket stripping of material vertex data is established by excluding Xbox draw calls.

## Required allowances and unresolved ownership, explicitly bounded

1. `leaf_map.bsp` is the schema's explicit reset. It must be on the byte-preservation verifier's exact slot allowance, with a zero postcondition.
2. `markers` is intentionally schema-opaque. Keep bytes and label the pointer unusable rather than silently adding it to a generic relocation claim. No runtime marker consumer was established.
3. `pathfinding_edges`, top-level unused arrays, and opaque nested padding have preserved-byte ownership but no established runtime semantic reader. Their absence from a search is not evidence of safe removal.
4. Schema validation may normalize malformed input rather than preserve it literally: cluster invalid decal ranges become NONE/zero [tag_schema_collision.c:1464](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1464); Custom Edition material hardware descriptors can be cleared [1298](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1298). The all-retail byte-equivalence audit must report actual corrections, with exact offsets, rather than use broad whole-record mutation allowances.
5. The Xbox BSP cache header's four vertex/index count/pointer fields are a separate adapter normalization. They are outside the `structure_bsp` declaration and must have their own precise allowance. Their clearing does not authorize clearing material buffer records or vertex payloads.
6. Declaration aliases are one store: public cluster, full schema cluster, and runtime decal overlay share bytes; public fog plane and schema fog plane share bytes. Charge and compare once using the richest schema.
7. PS2 owns ingress memory and GS/VU render packs; CE owns gameplay object/collision identity and its BSP query state. Byte preservation does not itself qualify visibility, weather progression, sound playback, or target execution. Those remain separate Step 7/8 gates.

## Comparative sources and evidence limits

[Halo-64 NOTES:33](../../submodules/halo-64/port/n64/NOTES.md:33) preserves CPU camera/frame/first-person/HUD state despite a different drawing backend and keeps geometry sampling for unit illumination. This supports tracing CPU consumers before dropping render-related data; it does not authorize PS2 cuts or establish capacity.

[halo-ps2 BSP format:49](../../submodules/halo-ps2/docs/08-bsp-section.md:49) labels fog bit15 as unknown in its renderer pack and [56](../../submodules/halo-ps2/docs/08-bsp-section.md:56) leaves portal-plane boundary equivalence uncertain. CE source resolves its own fog designator through scenario logic; do not let an uncertain renderer-pack interpretation replace that logic. [PS2 specs:99](../../submodules/halo-ps2/docs/02-specs.md:99) identifies unmeasured GS cost and [125](../../submodules/halo-ps2/docs/02-specs.md:125) requires measurement/rebalancing rather than treating paper totals as evidence. These uncertainty checks remain relevant to Step 8 target evidence.

REA is not needed for this declaration/schema inventory. Shipped executable differences or opaque artifact behavior can warrant REA later; the current source and retained retail bytes directly establish the field-preservation obligation.
