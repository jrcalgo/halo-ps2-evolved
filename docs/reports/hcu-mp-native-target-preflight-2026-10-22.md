# Native ILP32 MP preflight at fixed PS2 capacities

## Outcome

The real HCU map-service preflight was exercised against all thirteen pinned
stock multiplayer packages, twice per map, using native ILP32 and the exact
fixed profile: 2 MiB CTAG/tag cache, 4 MiB BSP cache, 1 MiB map-owner,
512 KiB streaming scratch, and a 786,432-byte claims bitmap. All 26 requests
reached the CTAG stream validator and rejected with status 3
(`PS2_CTAG_ERR_BOUNDS`: package image exceeds the configured image bound).
No tag or BSP pointers were published, the source descriptor closed, staged
map state cleared, and both arena cursors returned to zero on every attempt.
This proves safe rejection and retry/cleanup at the current capacity gate; it
does not prove a map load, relocation into a live CE world, or a BSP query.

The fixture is isolated in [`hcu_mp_target_preflight_main.c`](../../tests/hcu_mp_target_preflight_main.c)
and built/run by [`test_hcu_mp_target_preflight.py`](../../tools/test_hcu_mp_target_preflight.py).
The C driver asserts the exact array/claims sizes and contiguous streaming
ownership, then calls CE's `ps2_cache_preflight_map()` for every map twice
([driver setup and capacity assertions](../../tests/hcu_mp_target_preflight_main.c#L26),
[retry and rollback assertions](../../tests/hcu_mp_target_preflight_main.c#L71)).
The runner verifies each source map/package hash before compiling, rewrites
only a temporary test copy of the MP map-admission oracle to permit all
thirteen names, and compiles the HCU/PS2 lifecycle and map-service sources in
ILP32 mode ([runner compile and source setup](../../tools/test_hcu_mp_target_preflight.py#L48)).
No production source file was edited for this test.

The source's CTAG validator checks `image_size > maximum_image_size` as a
bounds error ([`ps2_ctag.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c#L286)).
The visitor callback currently causes the production preflight wrapper to
surface its outer I/O status when that callback returns false. To make the
negative test prove the *inner* capacity reason rather than a generic visitor
failure, the runner adds a small status-capture field only to its generated
temporary `hcu_map_service.c` copy; its generated source hash is recorded in
the manifest. The test then requires status 3 exactly 26 times. This is
test-only observability, not a behavior change to production.

## Runtime evidence

The successful native run's saved log records each map/attempt and reports
`owner_used=0`, `scratch_used=0`, `tags_published=0`,
`bsp_published=0`. Peak arena usage observed in the attempted preflight was:

- map-owner: 89,164 bytes of 1,048,576 bytes (largest observed; Blood Gulch
  and most packages); Beaver Creek peaked at 87,000 bytes;
- streaming scratch: 98,304 bytes of 524,288 bytes for every map;
- claims: exactly 786,432 bytes, bound before the attempts.

Each request was immediately retried in the same process after cleanup. All
26 checks passed; the final log line is
`mp-target-capacity-preflight 13-map x2 CTAG rejection/cleanup passed; no map
loaded or queried`.

Reproduce on a host that permits native ILP32 execution:

```sh
python3 tools/test_hcu_mp_target_preflight.py
```

The script compiles the binary and runs it. In a sandbox where native ILP32 is
blocked with SIGSYS, it returns 77 after compilation and preserves the exact
binary and assets. The runner was executed successfully outside that sandbox.
The standalone persisted-binary command is:

```sh
build/hcu-mp-target-preflight/mp-target-preflight build/hcu-mp-target-preflight/assets/
```

## Evidence identity

The test manifest records all thirteen package and source-map hashes, all
linked fixture-source hashes, generated source hashes, and the repository and
submodule pins. Main artifact hashes:

- `build/hcu-mp-target-preflight/manifest.json` SHA-256:
  `ecd91d2adccffb30b721df1adab37aca792255b59ba901e4670d04bd00df68ec`
- `build/hcu-mp-target-preflight/mp-target-preflight` (ILP32 ELF) SHA-256:
  `fa515d542ea5512e4907fbec8ac58d1854095786a5675c5c62315b4570b3d07a`
- `build/hcu-mp-target-preflight/mp-target-preflight.map` SHA-256:
  `a904d29eabb3fe801b5cffdf24b82343c810fc98ef0ed4d7a55159abf7ccccbe`
- `build/hcu-mp-target-preflight/run.log` SHA-256:
  `e27254b98f2b4a44082f14356631ad13e75518833909dfdb3ccd3c9d7a962dcb`
- `tools/test_hcu_mp_target_preflight.py` SHA-256:
  `682322e0bd77f5c266140389e6808a410200084eebf78a79bcf70ddda8340ebd`
- `tests/hcu_mp_target_preflight_main.c` SHA-256:
  `0dce81d4ff484ae965c9a9cc4b6afcce395b0de1bdf721b41a3509e03837b6d1`

Pinned revisions: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`.

## Limits

The all-map diagnostic uses `HCU_M2_MP_HOST_ORACLE` and an expanded allowlist
in the generated test copy only; it does not change production map admission.
All tested maps are rejected before CTAG materialization and CBSP loading, so
the run makes no claim about decoded tag relocation, BSP relocation, collision
queries, rendered maps, gameplay, PCSX2, or physical EE memory timing. It
demonstrates native ILP32 allocation/rollback behavior for the fixed-capacity
preflight path and confirms the current 2 MiB tag-cache limit is the first
blocking gate for every stock multiplayer map.
