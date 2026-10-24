# Step 7 stock-MP late CBSP failure atomicity and retry

## Result

The package-backed native ILP32 fixture now injects one late `B000` visitor
failure for every one of the 13 supported stock multiplayer maps. In each case,
the test sink first forwards a decoded prefix into the actual CE BSP destination,
then returns failure. CE rejects the initial `scenario_load`, publishes no
scenario/BSP/collision/game or tag-cache state, and the parent service releases
the mount, source descriptor, map-owner allocation, and section-scratch lease.
The same process then preflights, remounts, and successfully retries that same
map. This is a host semantic/failure-atomicity result; it is not PS2 capacity,
PCSX2, or retail-hardware evidence.

## Implementation and checks

The existing source seam was already present in
[`hcu_ce_map_lifecycle_main.c:145-203`](../../tests/hcu_ce_map_lifecycle_main.c#L145):
`__wrap_world_visit_section_with_scratch()` delegates into the real bounded HP2
visitor, passes its first decoded chunk through the real cache sink, verifies
that bytes landed in `bsp_cache`, and then reports a visitor failure. The CE
rollback behavior is in
[`scenario.c:1129,1154-1182`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1129).

The bug was only the loop guard in
[`hcu_mp_capacity_main.c:396-432`](../../tests/hcu_mp_capacity_main.c#L396):
it had restricted this scenario to the first map (`map == 0`) and first cycle.
The guard now runs on cycle zero for every row in the pinned 13-map matrix.
[`test_hcu_mp_capacity.py:634-641`](../../tests/test_hcu_mp_capacity.py#L634)
requires the exact ordered map set, so a future return to one-map coverage fails
the test. The emitted manifest records the fault boundary and required cleanup
and retry checks.

The native executable was run outside the sandbox because the sandbox blocks
native ILP32 execution with SIGSYS. It emitted all 13 rows, in matrix order:
Longest, Blood Gulch, Beaver Creek, Prisoner, Boarding Action, Carousel, Chill
Out, Damnation, Hang 'em High, Putput, Rat Race, Sidewinder, Wizard. Each row
has `cycle=0`; the full executable completed both lifecycle cycles for each map
and ended with `mp-host-collision 13-map CE hit/PVS/reload matrix passed`.

Reproduce the compile/wrapper check with:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py -v
```

In the current sandbox this reports a SIGSYS skip after building the ILP32
binary. Run that binary natively/unsandboxed from the repository root with:

```sh
build/m2-step7-late-b000-failure-atomicity-20261022/mp-weather-wind-location \
  build/m2-step7-late-b000-failure-atomicity-20261022/assets/
```

The captured native output is
[`native-ilp32-run.log`](../../build/m2-step7-late-b000-failure-atomicity-20261022/native-ilp32-run.log).

## Artifact identities

- Parent `HEAD`: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal `HEAD`: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2 `HEAD`: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Fixture ELF SHA-256: `a535571a352979ebe59f5aa46e14d2380cc17c5b7baca615ab5a6388caee9645`
- Link-map SHA-256: `b867bcc9ec5dd53c13447b9462c30c150f0955b26b199c562591ce120c2adb59`
- Native run-log SHA-256: `b4c525ef2b5a797ccc423c99d6dd1fd96e740974a4eb60bf515b28eabce69dcf`
- `tests/hcu_mp_capacity_main.c` SHA-256: `62581d84b8ca072b8dc559a46af43bfb405e71de9a83cc7dfb71b56f2395f3de`
- `tests/test_hcu_mp_capacity.py` SHA-256: `bdfd010037ee56e07634042eccc019397954327427de70c3bfe9a73b215a4687`

The fixture's tag/BSP backing arrays are 16 MiB and 8 MiB respectively, and
claims are also host-sized; see
[`hcu_mp_capacity_main.c:4-6`](../../tests/hcu_mp_capacity_main.c#L4). Therefore
this test establishes all-map rollback/retry semantics only. It does not show
that any stock MP map fits the PS2 32 MiB memory layout, nor does it establish
object/breakable collision parity, complete BSP-consumer coverage, target query
capacity, frame-time performance, or rendering. Step 7 and Step 8 remain open.
