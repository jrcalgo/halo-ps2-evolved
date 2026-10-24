# M2 Step 7 — Retail-backed CE collision wrapper qualification

**Result: one additive host ILP32 integration subcheck now passes.** The retail package transaction calls CE's public `collision_test_vector()` on a segment that already produced a hit through CE's real relocated collision-BSP traversal. The test checks the CE wrapper's structure result and field composition, and makes its unrequested dynamic-object branch fail closed. This is not an independent collision golden, a wrapper miss test, production-capacity evidence, or target/PCSX2 gameplay evidence. Step 7 remains partial.

## Scope and source boundary

The fixture runs CE `scenario_switch_structure_bsp()` over hash-verified `a30` and `a50` retail-derived HP2 packages, then tests each currently published/materialized BSP. It retains the actual HCU `source/physics/collisions.c::collision_test_vector()`, `collision_bsp.c::collision_bsp_test_vector()`, `bsp3d.c`, and `bsp2d.c`; the runner builds an ILP32 executable and retains the linker map. The wrapper contract is source-visible at [`collisions.c:478-735`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478); result layout is asserted in [`collisions.h:86-116`](../../submodules/halo-ce-universal/source/physics/collisions.h#L86). The call and composition assertions are in [`hcu_scenario_bsp_switch_main.c:870-1002`](../../tests/hcu_scenario_bsp_switch_main.c#L870); source selection and map retention are in [`test_hcu_scenario_bsp_switch.py:228-290`](../../tests/test_hcu_scenario_bsp_switch.py#L228).

For each BSP, the fixture continues to find a material-bearing candidate by crossing a polygon from CE's relocated collision BSP, and submits that exact segment to both the low-level traversal and public wrapper. The wrapper uses only `_collision_test_structure_bit | _collision_test_front_facing_surfaces_bit`; media and object flags remain clear. Assertions require:

- `TRUE`, `_collision_result_structure`, and finite in-range `t`;
- wrapper `t`, surface ID, material ID, and plane designator equal the real CE low-level result;
- `material_type` maps through the active structure BSP's collision-material record;
- oriented plane components match CE's plane-designator sign rule;
- hit point equals `point + t * vector` within `1e-4`;
- first/last leaf and mapped cluster fields correspond to the active CE structure leaves;
- the fail-closed object adapters remain uncalled;
- the entire published structure-BSP image is byte-identical before and after the wrapper call, and CE scenario/BSP publication indices and pointers are unchanged.

The test fixture supplies 256 “all intact” breakable bits because the wrapper always asks for breakable state, while this map-load fixture does not initialize gameplay breakable state or damage surfaces. This adapter means only “fresh map, no breakable transitions”; it does not qualify damage, breakable persistence, or the production `breakable_surface_flags_get()` owner. The retained wrapper statically references object-query routines even when object flags are clear; minimal fixture adapters abort if entered. They do not fabricate a collision, object, BSP, or material.

Two small host-build seams are also explicit. The test links real CE BSP3D traversal through [`hcu_bsp3d_host32.c`](../../tests/hcu_bsp3d_host32.c), adjusting only the host spelling of `__inline` because the common prefix otherwise expands CE's `static __inline` into duplicate `static`. [`hcu_real_math_host32.c`](../../tests/hcu_real_math_host32.c) emits the exact `point_from_line3d` and `plane3d_distance_to_point` expressions from CE's `real_math.h` for cross-translation-unit host linkage. Neither changes the R5900 production build.

## Verification and exact artifact identity

Command (approved native ILP32 execution outside the seccomp-restricted test sandbox):

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Result: **1 passed, 1 deselected, 2 retail package subtests passed in 139.28 s**. The ordinary sandbox attempt skipped the native ILP32 subtests with SIGSYS; that skip was not counted as runtime success. A focused host regression afterward passed **30 tests, 2 expected sandbox SIGSYS skips, 4 deselected, and 2 subtests** across CBSP, CTAG schema walk, synthetic CE collision, and non-retail scenario-switch tests.

Exact passing-run artifacts after the final assertions:

| Artifact | SHA-256 |
|---|---|
| Retained ILP32 executable | `12f02519b25e9cdff65e2b9a3dcb05f10bf6e9b5b9fe4318e2d8243be7d3b3fa` |
| Retained linker map | `8ccf5b3cf1eaab2bf0cb1ba02f3b72c6be34e0f891e7d81d83f64babcf819069` |
| C transaction fixture | `6f56fa2f39dfb3d17851c4f96d7e06f5152716f8c47510ca1a64bcd58a454bec` |
| Python package runner | `71adf319697826f7d0953d10f5643f253418ced88792db4987f7839f4b757397` |
| BSP3D host TU | `ed51f15ac9fe2b5bf16a9483f41ec17f7e32941e750003e4be25a18a6e75514c` |
| real-math host TU | `12933c77a71e346fe26c7fba39bea8efca900de9e14aade22e0c49b03c80a559` |
| Package-audit manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| CE `collisions.c` | `16581f812393db63428fcf426acaad33bebe0687393db4a7fc4febccc7ca45c3` |
| CE `collision_bsp.c` | `096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86` |

Repository source pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The compiled map retains `collision_test_vector`, `collision_bsp_test_vector`, `object_test_vector`, and the fail-closed adapter, proving the fixture did not silently link a replacement wrapper or dead-code away the object branch. Test and parent/submodule `git diff --check` passed.

Package/source identities are the frozen audit pair already used by the transaction: `a30` HP2 `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` and decompressed source `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`; `a50` HP2 `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` and decompressed source `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`.

## Limits and remaining Step 7 work

The expected hit is a **CE composition invariant**: candidate surface and low-level result are produced by CE over relocated retail data, then the public CE wrapper is checked against that result plus the real structure material and leaf tables. The new full-image snapshot proves the wrapper query did not mutate the active BSP or publication pointers. This does not provide a source-derived independent literal golden for collision `t`/plane/leaf, nor does it compare against a retail executable. It does not yet qualify a wrapper miss, front/back arbitration over a known single-sided surface, object/media/fog/weather paths, breakable-surface transitions, or scenario/global/arena failure atomicity.

The large host fixture arrays are intentionally overprovisioned. In particular, `a50` includes a 7,159,808-byte BSP against the 6,291,456-byte `current_bsp` region before accounting for tag/claims and other resident owners. The host test is therefore only a package-backed consumer test. No 32 MiB fit, PCSX2 gameplay load, or rendered scene follows. Step 8 remains the prerequisite for any target query; Step 10 remains the gameplay-map guest gate. The plan's separate PVS-pair source oracle remains independent and is documented in [`m2-step7-retail-consumer-query-qualification-2026-10-21.md`](m2-step7-retail-consumer-query-qualification-2026-10-21.md).

Halo-64 is referenced only as an architecture comparison: `port/n64/NOTES.md:33-55` separates CPU-side state from the renderer, and `n64_golden.c:213` shows its game calls CE collision APIs. It is not used as a collision golden, PS2 budget source, or reason to copy N64 cuts. REA is not applicable: this test investigates known CE source and data, not unexplained shipped-binary behavior.

The independent report-only feasibility and implementation reviews are [`m2-step7-full-ce-collision-wrapper-feasibility-2026-10-21.md`](m2-step7-full-ce-collision-wrapper-feasibility-2026-10-21.md) and [`m2-step7-full-ce-collision-wrapper-implementation-review-2026-10-21.md`](m2-step7-full-ce-collision-wrapper-implementation-review-2026-10-21.md). The implementation review's initial omissions (miss, independent golden, complete-plane comparison, and BSP-byte purity) have been addressed except for the independent golden/miss and are reflected in the final hashes above. Its note about overwriting an earlier artifact was followed by a new, final exact rerun; no hashes from the prior executable are used here.
