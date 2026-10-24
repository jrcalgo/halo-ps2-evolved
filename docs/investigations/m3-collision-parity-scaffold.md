# M3 collision/movement oracle scaffold

**Result: partial fixture preparation; no HCU-versus-parent parity is claimed.**

This report supports Remake M3 steps 15–16 without promoting a parent-only result to CE parity. The machine-readable fixture pins and test assertions are in [`m3-collision-parity-scaffold.json`](m3-collision-parity-scaffold.json); the executable test is [`tests/test_m3_collision_oracle.py`](../../tests/test_m3_collision_oracle.py).

## Frozen parent reference

The test builds a temporary HP2 `COLL` pack from retail Blood Gulch (`data/retail/convert/bloodgulch/decompressed/bloodgulch.map`, SHA-256 `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`) using `tools/convert_collision.py::build_pack`, then compiles [`tests/player_main.c`](../../tests/player_main.c) with the parent `move.c`, `pill.c`, `collide.c`, and `collpack.c`. The resulting pack SHA-256 is `28a747bec4f29bde74a2c86847d539d6faf95a78f86c42f40606862669e7e999`. The normalized trace (excluding only the variable wall-clock `bench` row) hashes to `e0a0a1628098b23914f3d4701c311c89c3ccd1dcbfefa70af03c19ed9f30ba70` on the pinned source set.

This reference covers floor settle, jump/land, walk, crouch, out-of-world recovery, render-schedule invariance, fast sweeps, and slope/ceiling/corner probes. Pill scratch measures 47,644 bytes versus the 393,216-byte `frame_scratch` budget. The existing player harness exercises render-schedule parity by simulating equal inputs with three presentation schedules ([`player_main.c:256–266`](../../tests/player_main.c)). The parent pill implementation explicitly describes itself as structure-only and excludes dynamic objects ([`pill.c:1–5`](../../src/game/pill.c)); its scratch size is derived from the caller-owned structure ([`pill.c:706–709`](../../src/game/pill.c)).

The test reruns the same retail-derived trace twice and compares the canonical output byte-for-byte as well as to the pinned hash. This is a baseline/regression test, **not** a CE comparison.

## Why CE comparison is blocked

The CE BSP-pill authority is `collision_bsp_test_pill_new` ([`collision_bsp.c:1130–1157`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c)). The higher-level CE collision path obtains its BSP through `global_collision_bsp_get()` before calling that function ([`collisions.c:1139–1166`](../../submodules/halo-ce-universal/source/physics/collisions.c)). Its input is a CE `collision_bsp` tag-block graph, not the parent converter’s HP2 `COLL` byte layout. Reinterpreting the parent pack as CE tag blocks would fabricate a comparison and could hide format/ownership errors.

At the observed M2 boundary, the guest has not reached `m2-ui-map-loaded` (the marker is emitted only after successful `scenario_load`, [`game.c:633–640`](../../submodules/halo-ce-universal/source/game/game.c)). More importantly, no gameplay map has been materialized and bound to CE’s resident collision globals. Even the diagnostic UI BSP package does not establish that prerequisite for a campaign/MP BSP. The fixture therefore records all five requested comparisons—player pill sweep, static BSP hit, dynamic object hit, actor hit, projectile hit—as `blocked-awaiting-m2-resident-gameplay-bsp`, with explicit blockers in JSON.

Dynamic-object, actor, and projectile rows additionally need equivalent live CE object/actor/projectile datums and collision filters. Existing `tests/test_actor_collision.py` checks extracted static cyborg collision mesh metadata; it does not run an actor collision query. The parent structure-only pill sweep has no corresponding dynamic object authority, so those cases cannot be labeled “matched” even if a static BSP test later passes.

## Unblock sequence

1. Complete M2 BSP residency for one selected gameplay map. Record the exact map/package/BSP hashes, CBIX selection, materialized bytes, arena owner, and `global_collision_bsp_get()` target.
2. Build a CE-side harness around the real `collision_bsp_test_pill_new` / `collision_test_pill_new` call path using the resident CE tag-block graph. Do not feed it the parent `COLL` pack.
3. Replay identical positions, vectors, radii, breakable flags, timestep/input sequence, and collision filters. Serialize hit/miss, fraction, normal, surface/material, final position/velocity, and grounded/sliding state. Establish tolerances from the tagged geometry and scalar precision, then report every mismatch.
4. Add object/actor/projectile cases only when both implementations expose semantically equivalent entities, generation-safe identities, ownership, and filters. Where the parent oracle does not implement a case, record the gap and use CE source/tag expected behavior as a separate implementation reference—not as a parity result.
5. Repeat CE traces for determinism and later run the same integrated guest fixture under PCSX2 interpreter and recompiler. Only after step 15’s relevant rows match and M2’s resident-BSP gate passes may step 16 change production collision ownership.

Focused verification on this source snapshot:

```sh
python3 tests/test_m3_collision_oracle.py -v
python3 tests/test_player.py -v
python3 tests/test_collide.py -v
python3 tests/test_actor_collision.py -v
```

All four commands pass. The first runs two tests: deterministic retail-derived parent trace/budget checks and a guard that prevents blocked HCU rows from being counted as parity. None invokes HCU collision at runtime; step 15 remains open, and step 16 is intentionally untouched.
