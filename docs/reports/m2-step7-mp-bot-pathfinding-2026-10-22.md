# M2 Step 7 — multiplayer actor pathfinding source and runtime fixture

## Finding

The retail multiplayer BSPs contain usable pathfinding inputs. They do not need a
precomputed `pathfinding_edges` block: CE derives each surface's adjacency from
the collision-edge rings when a bot query expands that surface. In all 13 stock
MP maps, the pathfinding-surface flag array has one byte per collision surface
and contains walkable sectors. The independent raw-map walk derives thousands
of actual adjacent-surface edges per map (table below).

The prior `tests/test_hcu_mp_path_consumer.py` fixture proved the unchanged CE
`build_path_edges_for_surface()` agrees with an independent raw-Xbox-BSP edge
walk for all 13 maps. This report adds two checks beyond that coverage:

1. Run the unchanged CE A* initialization, heap, edge builder, and traversal on
   a small synthetic three-surface BSP. It reaches surface 2 through surface 1;
   marking surface 1 non-walkable makes the destination unreachable.
2. Feed source-derived BSP payloads from **all 13** stock MP maps to those same
   CE functions. A raw collision-ring/path-flag BFS independently chooses a
   deterministic two-edge walkable route in each map; actual CE A* reaches each
   selected destination. The fixture emits CE's parent chain and checks every
   consecutive route pair against the independent raw adjacency oracle, checks
   every selected surface is walkable, and bounds CE depth to its 1,024-node
   workspace.

This is not an actor/bot match run. The test does not instantiate actors, run
`actor_moving`, validate path smoothing/obstacle avoidance/steering, model
breakable surfaces, call path perception or danger-zone attractors, or run on
PCSX2/EE. The retail query uses CE's path search and collision edge routines.
Its host adapter uses face-vertex centroids and centroid projection, not CE's
full collision surface projection/closest-point implementation; this keeps the
A* and edge builder real while limiting geometric realism. The previous shim
returned zero for any candidate surface near the goal and has been corrected to
return the centroid distance, preventing close non-goal surfaces from
satisfying a zero-radius destination.
The test therefore closes a source-data feasibility question and improves the
Step 7 path-consumer evidence, while leaving integrated bot acceptance open.

## CE path ownership and dataflow

- `source/ai/actors.c:1437-1467` resolves a grounded actor's pathfinding
  location to a BSP surface using the biped or ground-vehicle query. Flying
  actors do not select a surface here.
- `source/ai/actor_moving.c:2047-2085` builds a `path_input`, creates a
  `path_state`, sets the destination surface and point, then invokes
  `path_state_find()` followed by `path_state_build_path()`.
- `source/ai/path.c:1062-1160` seeds the start node from the actor's start
  point/surface. `source/ai/path.c:1200-1316` walks the surface's collision-edge
  ring and materializes neighboring surfaces and edge geometry. The A* loop at
  `source/ai/path.c:1479-1804` discards non-walkable neighboring flags, inserts
  eligible surfaces into the heap/hash, and succeeds when the destination
  surface is popped.
- `source/structures/structure_bsp_definitions.h:209-210` declares both
  pathfinding-surface and pathfinding-edge tag blocks. CE's active edge builder
  derives the route edges from `collision_bsp.edges`; it does not consume the
  top-level pathfinding-edge block.
- `source/ai/path_structure_bsp.c:748-774` bounds pathfinding-surface lookups;
  an invalid surface index is treated as non-walkable. `path_smoothing.c:109-146`
  similarly rejects an absent/out-of-range map surface before reading flags.

The raw map evidence is bound to the source map SHA-256 values already pinned in
`tests/test_hcu_mp_path_consumer.py:20-32`; the test checks these before decoding
the BSP. The derived BSP SHA-256 values are included below to identify the exact
decoded BSP images used by the independent oracle.

| Stock multiplayer map | Collision surfaces | Walkable flags | Derived adjacency records | Source `.map` SHA-256 | Raw BSP SHA-256 |
|---|---:|---:|---:|---|---|
| Beaver Creek | 2,476 | 639 | 8,212 | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` | `1fb6efe09129d9c477cac22e0462138b368e1b7e8228062110f2e3e52849c7c4` |
| Blood Gulch | 4,916 | 2,807 | 15,300 | `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1` | `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf` |
| Boarding Action | 3,693 | 548 | 13,570 | `34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522` | `2b1397a58285f6e6157c6591590a0df21c7b44ed488116599ac89534efa3a54d` |
| Carousel | 1,117 | 282 | 3,998 | `3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1` | `40a8324d3d9a8a5d238ecf9caa15a2b634a316d3552762c2be34adf06622b0cf` |
| Chill Out | 1,545 | 297 | 5,880 | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` | `2f8e7f85c0e52bf4a25bede449d1499068f629959bead6feb25574a47e8ad733` |
| Damnation | 4,053 | 745 | 15,342 | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` |
| Hang 'em High | 1,695 | 509 | 6,264 | `e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f` | `4828fcc280c2c364e1e469dcf4626d2656ff6ca188cdcbdf3659f82992a3f4c3` |
| Longest | 1,227 | 242 | 4,626 | `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` | `d2583ce3f53d5ff9f04ecaf163fed8f801e355d858c5254e954929f2c425530f` |
| Prisoner | 2,840 | 371 | 10,788 | `85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307` | `ea4000f883893868aa01df913f9dd9d239942e84d8f4a498f3017e87574d4f13` |
| Putput | 5,429 | 664 | 20,992 | `efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243` | `273326a59e3d13678ebad96704eb690e6dd79f2ad3c752d96f82de9de2fd49ca` |
| Rat Race | 1,474 | 299 | 5,160 | `577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e` | `060d953d098539f9247185ca342c47485dfd31942e1f2f98607dae9380fcfbce` |
| Sidewinder | 6,774 | 2,362 | 23,692 | `995561a68c8c5b142f13f1967730ce8c8d4f0db9574db8e987d915f2b118dcc` | `9e861ddb861fbaaf5b09a1431fa2acfa3f0f6c6bfee3a4fc4d64f90e75cb5a13` |
| Wizard | 1,559 | 331 | 5,962 | `978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb` | `c75e808bb3496a62e1c65fd01eade6b84ee38a2fdb72daade8fb18be6a155fdf` |

Counts are deterministic output from `raw_fixture()` in
`tests/test_hcu_mp_path_consumer.py`; “derived adjacency records” are the total
edge-ring entries returned by the same independent raw walk, not distinct
undirected graph edges.

## Comparative sources and PS2 implications

The checked source pins are HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`,
Halo-64 `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Halo-64 is a comparison only:
its README says the shipping N64 game retains Halo pathfinding for its bots
(`submodules/halo-64/README.md:43-48`, `:292-299`), and its `source/ai/path.c`
has the same walkable-bit-6 rule and on-demand collision-edge builder. HCU adds
bounds handling around malformed neighbor/path-surface indices; do not replace
the current HCU behavior with Halo-64's less-guarded direct lookup or treat its
N64 limits as PS2 limits.

The CE `path_state` is 0x1408C bytes (82,060 bytes), with 1,024 nodes and a
4,096-entry hash table (`source/ai/path.h:139-155,284-291`). `actor_moving.c`
places one such state in the path-refresh stack frame for uncached ground
routes (`:2047-2083`); several AI search paths also declare local path workspaces.
The PS2 has 32 MiB EE RAM (`submodules/halo-ps2/docs/01-ps2-architecture.md:46-48`)
and its project budget assigns 2.5 MiB to dynamic simulation
(`docs/02-specs.md:111-120`). Those facts make real bot concurrency/stack and
per-tick CPU measurements necessary: this fixture does not establish that many
simultaneous full CE path states fit the intended PS2 thread stacks or meet the
EE tick budget. The state is local scratch, not a BSP allocation; do not charge
it to the BSP path-edge block or infer it is free of memory/performance cost.

REA was not used: the relevant path selection and traversal behavior is present
in the checked-in CE-derived source and can be exercised directly. There was no
opaque binary behavior left that required a reverse-engineering claim.

## Reproduction and results

```sh
python3 -m pytest -q tests/test_hcu_mp_bot_pathfinding.py
```

Result after the all-map extension: `2 passed, 26 subtests passed`. The retail-data test verifies all 13
source-map hashes, equal collision/pathfinding-surface counts, at least one
walkable surface per map, and collision-derived adjacency records. The runtime
test compiles unchanged CE functions into a host harness and passes both the
synthetic reachable/unreachable cases plus actual CE A* traversal and
parent-chain adjacency checks on every stock MP BSP. Deterministic two-edge
test pairs are Beaver Creek 47→201, Blood Gulch 101→108, Boarding Action
393→486, Carousel 17→74, Chill Out 20→195, Damnation 131→476, Hang 'Em High
39→65, Longest 0→29, Prisoner 0→94, Putput 267→268, Rat Race 0→33, Sidewinder
69→121, and Wizard 25→46. They are fixture-selected examples, not curated
retail bot spawn/destination anchors. This is host execution, not target ABI or
emulator evidence.

SHA-256 after all-map extension: `tests/test_hcu_mp_bot_pathfinding.py`
`853b6fbc9ecf11411435f5316aa7d7827ffab8799e5b306792b1f93b01d894eb`;
`tests/hcu_mp_bot_pathfinding_host.c`
`07abae4349e4fb18419fab418358170d5293ab152fb1b7d9a86d837269354525`;
`tests/test_hcu_mp_path_consumer.py`
`affed33b5325b301876322b9c97c7de60473f09368d97bfc09a4e9ba8a18c73e`;
HCU `source/ai/path.c`
`626755d212abc247d1a5a37ec48231d9058eeea668f973425beade991fd53c41`;
HCU `source/ai/actor_moving.c`
`b8855ca311e2260bff14d8a438a9d08c2f9aaba1284c1d77c5347dca93fd9468`;
HCU `source/ai/actors.c`
`e5268ce59d8e67dcc573ead661a24c0f0dd4fcf334451f465701217da3cc5829`;
HCU `source/physics/collision_bsp.c`
`096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86`.

## Step 7 handoff

The blocker “stock MP BSPs might not contain bot path graph data” is resolved:
retail path flags plus collision edge rings are present and actual CE A* reaches
an oracle-checked route on all 13 stock MP BSPs. Do not close the broader
bot-path/runtime requirement from this host fixture. Remaining evidence should
run actual actor bots on retail MP BSPs,
including actor start/destination surface assignment, path refresh/build,
obstacle avoidance, broken-surface rules, steering/progress, bot counts, stack
high-water, and EE tick cost on the PS2-sized workload.
