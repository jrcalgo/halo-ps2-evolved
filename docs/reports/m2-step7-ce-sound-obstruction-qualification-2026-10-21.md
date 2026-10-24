# M2 Step 7 — CE sound-obstruction consumer qualification

## Result

The package-backed host ILP32 BSP transaction now calls the actual CE
`compute_sound_obstruction()` over each successfully published `a30` and `a50`
structure BSP. It checks three scoped cases where CE must not request geometry:
missing camera cluster defaults, the retail `0xFF` maximum-distance value, and
reachable-but-PVS-hidden attenuation. A separate Python oracle reads the raw
Xbox BSP bytes and independently identifies the pair, encoded sound byte, and
PVS value. CE's result is compared against that oracle and the attenuation
formula. The collision-user stack and a test-only, translation-unit-local
collision spy are checked after every query.

This closes only those named sound-consumer subchecks. It does not test the
visible-PVS collision branch, real sound selection/playback, SPU2, target memory,
or campaign-map capacity. The `a50` test uses host-overprovisioned buffers and
must not be interpreted as EE/PCSX2 gameplay acceptance.

## Implementation and source contract

- [`tests/hcu_game_sound_host32.c`](../../tests/hcu_game_sound_host32.c)
  includes the pinned CE `game_sound.c` directly so the fixture constructs the
  real private `sound_source` and calls the real function. Only observer camera
  state and the game tick are deterministic test adapters. The source's
  `collision_test_vector` call is macro-interposed in this one test translation
  unit with a counter-only spy; production CE collision sources remain
  unchanged and continue to execute in the surrounding BSP transaction.
- [`tests/hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c)
  runs each query immediately after the materialized BSP has been published.
  The cases require `0.6/1.0` defaults for missing/unreachable clusters and the
  CE attenuation result for a reachable, PVS-hidden pair. They assert no
  collision-spy calls, unchanged collision-user stack depth/base entry, and no
  object-path adapter use.
- [`tests/test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py)
  independently reads the raw Xbox BSP's `sound_cluster_data` and cluster PVS.
  The raw `structure_bsp.sound_cluster_data` member offset is pinned at 532 by
  an ILP32 `offsetof` assertion in the C fixture; the earlier test-only offset
  guess was corrected before acceptance. Pair indexing is independently
  computed as `i*(n-1) - i*(i+1)/2 + j - 1`, then compared with CE's selected
  pair and result. A missing sentinel case in a BSP is represented as absent,
  not fabricated; every BSP still must execute the missing-cluster case.
- CE's source implementation is
  [`game_sound.c:950-1049`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L950),
  with distance scaling/masking and strict maximum-distance comparison at
  lines 985-1034. Its sound-pair accessor and row-major triangular indexing are
  [`structure_bsp_definitions.c:207-267`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L207).
  The fixture preserves CE's actual branches rather than implementing a
  replacement sound algorithm.

The raw-source selections bound by this run are:

| Source BSP | Clusters | Exact `0xFF` pair | Reachable hidden-PVS pair |
|---|---:|---|---|
| a30 B000 `a30_a` | 38 | 0→1 | 0→9, byte 109 |
| a30 B001 `a30_b` | 39 | 0→27 | 0→3, byte 34 |
| a50 B000 `a50_exterior` | 12 | absent | 0→5, byte 9 |
| a50 B001 `a50_muster` | 72 | 0→19 | 0→2, byte 4 |
| a50 B002 `a50_hangar` | 82 | 0→1 | 0→10, byte 6 |
| a50 B003 `a50_control` | 64 | 0→23 | 0→2, byte 7 |

CE masks the high bit and scales the remaining seven bits by `256/127`; hence
the test selects the exact retail `0xFF` sentinel, whose masked value scales to
256 and fails CE's strict `< 256` test. Reachable hidden pairs are selected when
their masked value is below 127. Expected hidden attenuation is calculated
independently as `PIN((1 - 10/(encoded_low7*256/127 + 10))*1.4, 0, 1)`.

## Reproducible evidence

The exact command was:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

**Result:** `1 passed, 1 deselected, 2 subtests passed in 130.34s` through the
approved native ILP32 execution route. The sandboxed invocation itself is
expected to skip native execution on `SIGSYS`; that skip is not counted as a
pass. The final focused related regressions passed **30 tests**, with 2
expected sandbox skips and 2 subtests. Final Python syntax, `git diff --check`,
and both parent/HCU submodule diff checks passed.

Artifact identities for the passing final run:

| Artifact | SHA-256 |
|---|---|
| Retained ILP32 executable | `3fa6e12b2d41ec732a004f82b9506de5c78effe5f36a69591b9a20687db325e4` |
| Link map | `197410fbb65e6cbc9b30bd28baa06f05089976b764ce7302fb165fbcc1c50a38` |
| C transaction fixture | `19c6c1ffe330f46de21069aaf55df21cabfe053619974217aac86f1eb0335392` |
| CE sound bridge | `9ccf586897e681add616e4777968f252b1305a1fe0cdbec6060a4a36fa9af550` |
| Python test/oracle | `7ea4cd2794a1145e36aa5537b6cbe44789b0430ec1ae41da731bbcd5e17567e5` |
| Package audit manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| a30 source map / HP2 | `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` / `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` |
| a50 source map / HP2 | `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` / `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` |
| CE `game_sound.c` | `c57cd2ea070b7b249c87c1b8a18647c9afbd2895df3cd4a92eab76ab4a3b5c83` |
| CE `structure_bsp_definitions.c` | `00bbb359e4cf9129f8cf0076e7754584a31060836be0460a17cbaef24f8e51eb` |

Parent/HCU/halo-ps2 HEADs were `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`,
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The test's compile map retained
both `compute_sound_obstruction` and its test bridge, while the actual CE
collision wrapper and dynamic object routines remain in the wider transaction
link closure. No REA pass was needed: this is direct CE source plus hash-bound
retail-data execution, not an unexplained shipped binary. Halo-64 remains
comparison context only; its sound/backend and memory cuts are not used as PS2
authority ([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)).

## Remaining Step 7 scope

This does not finish Step 7. Still open are the visible-PVS sound branch with
real collision geometry and bounded object/media semantics; an independent
collision hit/miss/material/plane/leaf oracle; CE fog, weather, environment,
and location consumers; runtime failure atomicity across CE globals and arena
owners; and target execution using a capacity-qualified BSP. Step 8 remains a
hard dependency for target-capacity acceptance; the current all-campaign lower
bound rejects whole-resident map storage, so this host result does not unlock
campaign admission.
