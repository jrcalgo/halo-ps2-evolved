# Step 7 multiplayer path consumer slice

This fixture exercises CE's real BSP edge consumer on the 13 stock multiplayer maps. It calls the unchanged bodies of `build_path_edges_for_surface` from `source/ai/path.c` and `collision_bsp_valid_surface_index` / `collision_surface_edge_ring_continues` from `source/physics/collision_bsp.c`. The test extracts those bodies from the checked out CE sources and compiles them into an isolated native host harness with compatibility data structures. The harness has no AI actor or game-runtime bootstrap.

CE defines a path edge as an adjacent collision surface, its pathfinding flags, a base vertex, and a directed edge vector ([`path.c`](../../submodules/halo-ce-universal/source/ai/path.c#L187)). The path search calls this builder for each expanded surface ([`path.c`](../../submodules/halo-ce-universal/source/ai/path.c#L1538)). The builder traverses the surface's collision-edge ring, bounds ring traversal, resolves adjacent pathfinding bytes, and constructs vertex vectors ([`path.c`](../../submodules/halo-ce-universal/source/ai/path.c#L1200), [`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L352)).

The independent Python oracle reads the original decompressed Xbox map, follows its scenario BSP reference, and parses the collision surfaces, edges, vertices, and pathfinding byte block directly. It does not read the CE harness payload to compute expected results. For every collision surface, CE and the oracle agree on the number and sequence of edges, adjacent surface index, adjacent pathfinding byte, vertex base point, and vector. The fixture also checks representative first, middle, and last surface edge records. Two 64-bit FNV-1a digests provide compact whole-map comparisons: `flags_fnv` covers each collision surface's corresponding pathfinding byte (or zero if absent); `edges_fnv` covers each surface index and edge count, followed by each edge's adjacent index, adjacent flag, and six IEEE-754 binary32 point/vector components in little-endian order. The exact selected samples are compared separately as printed numeric records.

## Results

All rows passed the CE-versus-raw comparison. Each stock multiplayer map has one BSP, and every map's pathfinding-surface count equals its collision-surface count.

| Map | Raw map SHA-256 | Raw BSP SHA-256 | Surfaces | Walkable flags | CE edges | Flags FNV-1a64 | Edge records FNV-1a64 |
|---|---|---|---:|---:|---:|---|---|
| beavercreek | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` | `1fb6efe09129d9c477cac22e0462138b368e1b7e8228062110f2e3e52849c7c4` | 2476 | 639 | 8212 | `a12829da5cc9db55` | `4ee496f39a00f7e5` |
| bloodgulch | `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1` | `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf` | 4916 | 2807 | 15300 | `eeb9d47f1355fb75` | `c5fb219290211c23` |
| boardingaction | `34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522` | `2b1397a58285f6e6157c6591590a0df21c7b44ed488116599ac89534efa3a54d` | 3693 | 548 | 13570 | `14a0cdb4f8955faf` | `defc46099b9e1eab` |
| carousel | `3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1` | `40a8324d3d9a8a5d238ecf9caa15a2b634a316d3552762c2be34adf06622b0cf` | 1117 | 282 | 3998 | `bef0097aa3a7cb6f` | `37c1db5a15343f26` |
| chillout | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` | `2f8e7f85c0e52bf4a25bede449d1499068f629959bead6feb25574a47e8ad733` | 1545 | 297 | 5880 | `58454c326b2b547f` | `65b0ad1a0f408502` |
| damnation | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` | 4053 | 745 | 15342 | `fe78ec8e9493f4cf` | `1dccb5521bf1e64c` |
| hangemhigh | `e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f` | `4828fcc280c2c364e1e469dcf4626d2656ff6ca188cdcbdf3659f82992a3f4c3` | 1695 | 509 | 6264 | `d8b7bf1a5c39cc07` | `b46b0fe6904413f0` |
| longest | `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` | `d2583ce3f53d5ff9f04ecaf163fed8f801e355d858c5254e954929f2c425530f` | 1227 | 242 | 4626 | `72af177f4fef9a17` | `ccdaecc137e6ce3a` |
| prisoner | `85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307` | `ea4000f883893868aa01df913f9dd9d239942e84d8f4a498f3017e87574d4f13` | 2840 | 371 | 10788 | `d26207829e142145` | `6064cd3d4a60487a` |
| putput | `efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243` | `273326a59e3d13678ebad96704eb690e6dd79f2ad3c752d96f82de9de2fd49ca` | 5429 | 664 | 20992 | `1550cf0f9b7a7c0f` | `da92354dd0433e13` |
| ratrace | `577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e` | `060d953d098539f9247185ca342c47485dfd31942e1f2f98607dae9380fcfbce` | 1474 | 299 | 5160 | `a234ec4fda8fc0ad` | `0a599bcf54aa607a` |
| sidewinder | `995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc` | `9e861ddb861fbaaf5b09a1431fa2acfa3f0f6c6bfee3a4fc4d64f90e75cb5a13` | 6774 | 2362 | 23692 | `7f7c4f0ad85fb27d` | `bde186b2003a9f65` |
| wizard | `978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb` | `c75e808bb3496a62e1c65fd01eade6b84ee38a2fdb72daade8fb18be6a155fdf` | 1559 | 331 | 5962 | `b4e19fc4753e0b27` | `8007c76ed5c68b5b` |

## Reproduction and source hashes

Run from the workspace root:

```sh
python3 tests/test_hcu_mp_path_consumer.py -v
```

Result: `Ran 1 test`, `OK`; the test contains 13 per-map subtests. The runner uses temporary generated C and binary input files and leaves no generated fixture data behind.

SHA-256 of the exact checked out sources and fixture:

| File | SHA-256 |
|---|---|
| `submodules/halo-ce-universal/source/ai/path.c` | `626755d212abc247d1a5a37ec48231d9058eeea668f973425beade991fd53c41` |
| `submodules/halo-ce-universal/source/physics/collision_bsp.c` | `096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86` |
| `tests/hcu_mp_path_consumer_main.c` | `5fbc89fc770337a4738709efb8ebaca0ca06f6f80749002805ad528d8dd27109` |
| `tests/test_hcu_mp_path_consumer.py` | `fbc77e87fbc789952028de112a19cd7b52c7bf47886e79b0d8a83405daeb48d7` |

## Scope limit

This proves CE's source edge-ring consumer and pathfinding-byte interpretation against source-derived stock BSP data on a host. The harness mirrors only the relevant CE record layouts and provides a vector helper and minimal error/assert support; it does not link the full CE runtime, load BSPs through the game's tag cache, build an actor path state, run the A* traversal, or validate a selected destination/path result. It is one Step 7 semantic consumer slice and does not establish Step 7 completion or change gameplay behavior or memory budgets.
