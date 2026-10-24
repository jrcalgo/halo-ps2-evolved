# M2 Step 7 current target BSP consumer probe

## Result

PCSX2 interpreter passed and PCSX2 recompiler passed the deterministic 13-map CE BSP query on the same exact ELF. Each map emitted one positive CE collision hit with the expected retail surface/material, queried every cluster PVS row, completed its retained A* route, unloaded its scenario, and passed guard checks. These are diagnostic runs using the opt-in MP capacity profile.

ELF SHA-256: `3f8efe1407f44a1f74d3a5f0d8c7c8941173d19f54ef17ffef258ce320ff93e3`. The machine-readable evidence with run, emulator, BIOS, settings, result, guest-log, and validator hashes is `docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json`.

| Backend | Result SHA-256 | Guest log SHA-256 | Query rows | Unload/guard rows | Path rows |
|---|---|---|---:|---:|---:|
| PCSX2 interpreter passed | `da7748c43a7490fef6e3f11b4542008fc9a6300d05a182ab92d2201ff6ca558e` | `c76264f7ede2b243c7709b260bdea488a7d87f5bf681a32e0b4fc552f7b8f2e9` | 13/13 | 13/13 | 13/13 |
| PCSX2 recompiler passed | `cd4ed9507c23dfee917ba1dd96ed378a3b043ab06408ebec3b01d566e56127c5` | `d3a24b7168e5e74db6dcccb9d5127a377d89b23b2a05c61f6a998a4d84fc736a` | 13/13 | 13/13 | 13/13 |

## Exact BSP members exercised

The loaded retail CBSP is published by `scenario_load()` before these real CE calls execute. `structure_bsp_get_cluster_pvs()` reads `structure_bsp.clusters` and `structure_bsp.cluster_data` for every cluster index. `collision_test_vector()` calls `collision_bsp_test_vector()` and checks the selected `structure_bsp.collision_materials` result against the source oracle. The positive hit executes the 3D BSP traversal and selected 2D/surface route.

| Exact inventory member | Executed consumer / evidence |
|---|---|
| `structure_bsp.clusters` | `structure_bsp_get_cluster_pvs; loop bound and cluster indices`; `submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c` |
| `structure_bsp.cluster_data` | `structure_bsp_get_cluster_pvs; cluster visibility bitvectors`; `submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c` |
| `structure_bsp.collision_bsp` | `collision_test_vector -> collision_bsp_test_vector`; `submodules/halo-ce-universal/source/physics/collisions.c` |
| `collision_bsp.bsp3d.nodes` | `3D collision tree traversal`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `collision_bsp.bsp3d.planes` | `collision plane lookup during 3D tree traversal`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `collision_bsp.leaves` | `collision leaf lookup in vector collision traversal`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `collision_bsp.bsp2d_references` | `2D collision routing from leaves`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `collision_bsp.bsp2d.nodes` | `2D collision tree traversal`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `collision_bsp.surfaces` | `vector collision surface selection`; `submodules/halo-ce-universal/source/physics/collision_bsp.c` |
| `structure_bsp.collision_materials` | `collision_structure_material_type; returned material checked against source oracle`; `submodules/halo-ce-universal/source/physics/collisions.c` |
| `structure_bsp.pathfinding_surfaces` | `CE A* path search over retained retail routes`; `submodules/halo-ce-universal/source/ai/path.c; submodules/halo-ce-universal/source/ai/path_structure_bsp.c` |
| `structure_bsp.pathfinding_edges` | `CE A* route adjacency traversal`; `submodules/halo-ce-universal/source/ai/path.c; submodules/halo-ce-universal/source/ai/path_structure_bsp.c` |

## Limits

- The query executes real CE consumers after scenario_load publishes each retail CBSP. One deterministic hit per map does not visit every collision record or prove malformed-data handling for every member.
- The PVS loop invokes CE for every cluster index and requires every returned row to be non-null. It does not establish visual submission or pixel correctness.
- A* uses one predetermined successful route per map; it is not an AI actor steering workload.
- The diagnostic ELF uses the opt-in MP capacity path and does not qualify ordinary production admission, renderer residency, 5,767,168-byte reserve, or physical hardware behavior.
- This report covers only the explicitly listed members and tested call paths. Other BSP consumers, opaque ranges, and open dispositions remain governed by the current generated crosswalk and inventory; no whole-inventory closure is claimed.

The original test ELF source prints `step8-mp-capacity-query`, `step8-mp-capacity-unloaded`, and the completion marker only after its assertions. The capture and acceptance parser are `tools/test_hcu_step7_path_guest.py`; this summary validator is `tools/record_step7_bsp_target_probe.py`.
