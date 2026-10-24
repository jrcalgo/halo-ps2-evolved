# M2 Step 7 — preflight relocation-owner exhaustion qualification

## Result

Added a real bounded-arena exhaustion case to the host ILP32 CE lifecycle
fixture. It drives the production `hcu_map_service_preflight()` through
HMAP/CRNG/CBIX loads, then makes the exact CTAG relocation-vector allocation
fail because the owner arena is one byte too small. The service rejects the
candidate, rewinds temporary allocations, closes the source, clears private
preflight state, and a subsequent attempt in the same process successfully
loads and unloads the real UI scenario. The approved native ILP32 test passed
**1 test in 10.45 seconds**.

The injected failure is not a budget or capacity estimate. Its 39,831-byte
test arena is deliberately undersized to force one failure path; the test
restores the fixture's normal 16 MiB owner before retrying. This closes only
the preflight relocation-allocation-exhaustion subcheck; it does not show a
production map fits the PS2 memory plan.

## Exact failure construction

The Python test parses the actual audited UI HP2 and derives the failure cap
from the HMAP, CRNG, and CBIX payload sizes, the 64-byte output alignment used
by `world_load_section_with_scratch()`, and the relocation count in the CTAG
header. It establishes that the earlier sections fit and the later relocation
vector does not:

| Quantity | Bytes |
|---|---:|
| Aligned owner offset before CTAG relocation vector | 3,116 |
| CTAG relocation count × 4-byte entry | 36,716 |
| Forced arena capacity (one byte below allocation end) | 39,831 |

The production allocation path logs
`ctag-relocation-allocation-failed bytes=36716 used=3116 cap=39831`, then
reports the CTAG stream rejection. The test checks this exact diagnostic, not
merely a generic preflight failure.

After rejection, the C fixture asserts `map_arena.used` and
`section_scratch.used` returned to zero; no active source, descriptor,
mount, staged entry/map, reload/preflight-ready bit, cache-load marker, or
nonzero CTAG result survives. It restores the original owner cap, retries
preflight, runs CE's normal precache and `scenario_load()` path, checks the
published scenario/BSP/tag state, then calls `scenario_unload()` and verifies
CE publication, mount/source, descriptor, and both arena cursors are cleared.
The actual CE transaction and parent map service are linked by
[`tests/test_hcu_ce_map_lifecycle.py`](../../tests/test_hcu_ce_map_lifecycle.py);
rollback cleanup and state assertions are in
[`tests/hcu_ce_map_lifecycle_main.c`](../../tests/hcu_ce_map_lifecycle_main.c),
and the allocation failure is emitted by
[`src/stream/hcu_map_service.c`](../../src/stream/hcu_map_service.c).

## Reproduction and evidence

```sh
PYTHONPATH=. \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q -rs tests/test_hcu_ce_map_lifecycle.py -x
```

The ordinary sandbox compiles but skips the native ILP32 executable with
SIGSYS. The final test ran via the approved native execution path and passed
**1 test**. `python3 -m py_compile` and `git diff --check` passed.

| Artifact/input | SHA-256 |
|---|---|
| Parent/HCU/halo-ps2 source pins | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| UI HP2 | `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |
| UI source map | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` |
| Native fixture ELF / link map | `f0f6bf633cab5e0b5b1dfc7fd51814a95424038e0fb9cda90ac2d6d76e0149cc` / `178b06eed803d046b5012b7bd652269433f59e78c37268f51a387ef5047d53e8` |
| Main lifecycle log | `5ed20c8dd86debfda1ff2a2c89cc5cf140fda52e81550c6fa29ced0b0cfa2efc` |
| Owner-exhaustion log | `65b5968c27ec109ee3c86d23a3ede605e5c1057b85b225df3b253097242c06f0` |
| Parent map service source | `13c739984bc3d74c2ec2002b8d67a9d7574084b537f9ffdf54547b65f936f0ae` |
| C lifecycle fixture | `ec53fd6f83f5ae1fd85752f16347e4269817023b3b2b9f95433a0df3e898239c` |
| Python test/runner | `8e1616e9c27bb831162c1e1e4eb9e5fb2e2c8d9da2f0ed215a94161810c1d049` |
| Run manifest | [`build/m2-ce-map-lifecycle-host/manifest.json`](../../build/m2-ce-map-lifecycle-host/manifest.json) |

This host test uses the UI/bootstrap identity and POSIX-backed test assets. It
does not qualify FileXio/OPL/optical behavior, campaign map capacity, physical
EE placement, BSP-switch failure modes, player collision, or rendering. Step 7
and M2 remain partial. Halo-64's N64 implementation remains comparison context
only for ownership boundaries, not capacity or behavior evidence; REA is not
applicable because this test directly exercises source-visible logic and a
hash-bound package.
