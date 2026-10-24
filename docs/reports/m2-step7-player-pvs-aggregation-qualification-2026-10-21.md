# M2 Step 7 — CE player combined-PVS aggregation qualification

## Result and scope

The package-backed host ILP32 fixture now executes CE's actual static
`players_compute_combined_pvs()` against each currently published `a30` and
`a50` BSP. It compares all 16 output words for both the ordinary all-player
vector and CE's local-player-only vector against an independently decoded
oracle from each original Xbox map. The test passed **1 test, 1 deselected,
and 2 package subtests in 132.07 seconds** using the approved native ILP32
route. Sandbox execution reaches the test but blocks the native executable
with SIGSYS; that skipped run is not counted as evidence.

This closes only player-cluster PVS aggregation and local-player filtering
for the listed synthetic player records and six hash-bound published BSPs. It
does not qualify player spawning/positions, live object-root cluster refresh,
the editor-camera branch, activating-object/cluster behavior, portal/frustum
visibility, target capacity, PCSX2 gameplay, rendering, or Step 7/M2 overall.

## CE behavior under test

The source function is [`players_compute_combined_pvs()` in
players.c:1789-1877](../../submodules/halo-ce-universal/source/game/players.c#L1789).
It clears exactly 64 bytes, iterates CE player datums, filters records with
`local_player_index == NONE` when requested, ORs each valid player cluster's
PVS, and finally adds an activating-cluster row when one exists. The fixture
includes pinned CE `players.c` only in a dedicated test translation unit and
exports a wrapper for the static helper
([`hcu_player_pvs_host32.c`](../../tests/hcu_player_pvs_host32.c)).
Function/data section garbage collection retains the requested helper and
its real CE dependencies, not the rest of player gameplay.

The retained link map confirms the live closure includes:

- `players_compute_combined_pvs()` and `hcu_test_players_compute_combined_pvs()`;
- CE `data_iterator_new()` / `data_iterator_next()` from
  [`memory/data.c:399-447`](../../submodules/halo-ce-universal/source/memory/data.c#L399);
- CE `structure_bsp_get_cluster_pvs()` from
  [`structure_bsp_definitions.c:45-68`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L45);
- CE `bit_vector_or()` from
  [`integer_math.c:346-363`](../../submodules/halo-ce-universal/source/math/integer_math.c#L346).

The test uses CE's actual player datum layout (`sizeof == 0xD4`, enforced by
[`players.h:170-181`](../../submodules/halo-ce-universal/source/game/players.h#L170))
and actual iterator implementation. It sets every `unit_index` to `NONE`, so
CE does not enter object lookup or mutate `cluster_index` from a live object.
The environment is explicitly constrained to ordinary game mode
(`game_in_editor() == FALSE`) and no activating cluster (`NONE`); those two
environment inputs are test adapters, not substitutes for aggregation.
Object lookup adapters abort if the excluded live-object branch is reached.

## Independent raw-map oracle and checks

[`retail_source_player_pvs_oracle()`](../../tests/test_hcu_scenario_bsp_switch.py#L172)
reads the original Xbox BSP extents by resolving the source scenario's BSP
records. It reads each serialized `cluster_data` row directly, forms three
source-derived cluster inputs (two local, one non-local, plus an active
clusterless local player), and selects a non-local row that contributes at
least one bit absent from the two-local-player union. The oracle pads both
expected vectors to the CE helper's full 16-word/64-byte output and writes the
temporary C golden header. The fixture requires a visible difference between
all-player and local-only results, compares every word, checks the synthetic
player records remain byte-identical, and confirms BSP publication identity,
scenario BSP index, collision-user depth, and the materialized PVS span do not
change. The Python runner requires a CE query marker for every BSP so an
unreached wrapper cannot pass
([`hcu_scenario_bsp_switch_main.c:781-860`](../../tests/hcu_scenario_bsp_switch_main.c#L781),
[`test_hcu_scenario_bsp_switch.py:1028-1044`](../../tests/test_hcu_scenario_bsp_switch.py#L1028)).

The selected cluster inputs and the distinguishing leading output words are:

| BSP | Clusters | Player clusters (slot 0..3; `-1` means no PVS) | All-player words | Local-only words |
|---|---:|---|---|---|
| a30 B000 | 38 | 0, 3, 1, -1 | `C02D49FF`, `0000003F` | `C00D49FF`, `0000003F` |
| a30 B001 | 39 | 0, 2, 1, -1 | `E5FDEE67`, `0000007F` | `61FDEE67`, `00000018` |
| a50 B000 | 12 | 0, 1, 4, -1 | `00000FFF` | `000009BF` |
| a50 B001 | 72 | 0, 2, 1, -1 | `000403FF`, `0000026A` | `000403DB`, `00000200` |
| a50 B002 | 82 | 0, 2, 1, -1 | `6E1DDF7F`, `F340F73F`, `0003FC17` | `0E1DC37F`, `F340F73F`, `0003FC17` |
| a50 B003 | 64 | 0, 2, 1, -1 | `000045FF` | `000045BF` |

Unlisted words in each 16-word result are zero. The generated golden header
used by the final run is retained at
[`build/m2-group-d-file-backed-transaction/hcu_player_pvs_golden.h`](../../build/m2-group-d-file-backed-transaction/hcu_player_pvs_golden.h).

## Reproduction and exact identities

Approved native ILP32 command:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Final run: **1 passed, 1 deselected, 2 package subtests passed in 132.07 s**.

| Input/artifact | SHA-256 |
|---|---|
| Parent source revision | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| HCU source revision | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 source revision | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| CE `players.c` | `837b39a3b24997ea7619356cf080d004dfa4b3810950ddce0f298244c1a6eb09` |
| CE `players.h` | `8093f9d480f0dcbb278fe2758598facaaeb41ceeb0536d314e8a7774e4bb892d` |
| CE `memory/data.c` | `db97ad491207a513f6d6015f9c2fbd2c2bd7a83e2d5698be4ab8a8bf3ea773e9` |
| CE `structure_bsp_definitions.c` | `00bbb359e4cf9129f8cf0076e7754584a31060836be0460a17cbaef24f8e51eb` |
| CE `integer_math.c` | `739c66201acfe18423305ec9a5a1a9b51aba61cfafdc36148af389eb219574d5` |
| CE `scenario.c` (dirty worktree file compiled for `global_structure_bsp_get`) | `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0` |
| Package audit manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| a30 decompressed Xbox map | `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` |
| a50 decompressed Xbox map | `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` |
| a30 HP2 package | `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` |
| a50 HP2 package | `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` |
| Fixture executable | `d8745a7d30c9b6607a7758eca77246422fb9ee905d6ad66416f2a33cda7ea6ad` |
| Fixture link map | `46f5c6b63171cc75f35c3fa6e7d52c5a2823e89da74e20ba2ceb71837ba4b233` |
| Generated player-PVS oracle header | `b8714f296bfaf95b0bb206bfd85e68a1fe07f02daaadca413a254cdb0ffb1145` |
| `hcu_player_pvs_host32.c` | `2f6b83b1018f99921232300b0bba22851214d18c5df96e9c72bdd839fe98fcc1` |
| `hcu_scenario_bsp_switch_main.c` | `27909145c29dfc418a7ff198146df59f1ec297aa8f17aca37baaed0c6a5970fc` |
| `test_hcu_scenario_bsp_switch.py` | `1857e98cfaf1c3a215e795580806cab49e665e75a990c9e8e5db0fcb4eeba2ad` |

The exact map confirms the CE function, its wrapper, both CE iterator entry
points, cluster-PVS accessor, and bit-vector OR implementation are retained.
The full integrated transaction remains an overprovisioned host fixture: it
does not create PS2 resident-memory, performance, PCSX2, or rendered-scene
evidence. Halo-64 is used only for the simulation/presentation ownership
boundary noted in [`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33);
its N64 player limits and optimizations are not adopted. REA is not applicable
because this test targets inspectable CE source and decompressed raw map data.

## Relationship to Step 4 and remaining gates

Step 4 remains **complete as a decision record only**: retain the in-image
`TAG_SCHEMA_DATA` representation, make no budget/region change, spend none of
the reserve, and defer externalization until identity/lifetime/parity/I/O and
target high-water evidence exists. This was independently rechecked after the
user asked that Step 4 be included; see
[`m2-step4-animation-data-decision-current-audit-2026-10-21.md`](m2-step4-animation-data-decision-current-audit-2026-10-21.md)
and [`plans/7.hcu-remake-m2-m4.md:557-563`](../../plans/7.hcu-remake-m2-m4.md#L557).
That status does not imply a map-fit/capacity result.

Step 7 remains partial. The independent raw collision review identifies
uncovered exact edge/grazing and flagged-surface cases
([`m2-step7-miss-backface-crossreview-2026-10-21.md`](m2-step7-miss-backface-crossreview-2026-10-21.md));
live object collision, full transaction rollback/arena failure coverage, and
a capacity-qualified target collision query are also outstanding. Step 8
still owns the lawful residency/capacity prerequisite for target query. This
host player-PVS result does not bypass that dependency or close M2.
