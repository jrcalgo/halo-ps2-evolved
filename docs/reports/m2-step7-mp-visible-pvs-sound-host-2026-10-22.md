# Step 7 — Visible-PVS multiplayer sound obstruction branch

**Disposition:** CE's visible-PVS branch in `compute_sound_obstruction()` is now exercised against a package-loaded Blood Gulch BSP in a host ILP32 fixture. The collision result is supplied by a test-only spy that returns a controlled miss. This verifies CE's branch selection and miss policy, not collision geometry or audible output.

## Evidence

The independent raw-source oracle selects Blood Gulch clusters `0 → 1`. It reads the original Xbox BSP extent, confirms the PVS bit for cluster 1 in cluster 0's row, and decodes the packed upper-triangle sound table from `sound_cluster_data`. With 30 clusters, pair `(0, 1)` has triangular index 0 and raw distance byte `0`; the pair is therefore acoustically reachable. Raw map SHA-256 is `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`; source BSP image SHA-256 is `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf`.

The fixture package-loads the stock multiplayer BSPs through the existing CE scenario/cache lifecycle. It runs two cycles for each of the 13 maps (26 lifecycle rows total); the new visible-PVS assertions run only for Blood Gulch, once per cycle. In both cases, CE's actual `compute_sound_obstruction()` reads the published BSP PVS and sound-distance accessors, invokes the interposed collision site once, receives the controlled miss, returns obstruction/occlusion `0/0`, and leaves collision-user depth and the published BSP/index unchanged. Exact markers:

```text
mp-sound-obstruction-visible map=102 from=0 to=1 encoded=0 pvs=1 collision_calls=1 spy=controlled-miss obstruction=0 occlusion=0 status=passed
```

CE source contract: [`game_sound.c:950-1034`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L950) initializes defaults, reads the encoded sound distance at lines 989-996, gates on PVS at 998-1002, and requests geometry at 1004-1024. The BSP accessors are [`structure_bsp_definitions.c:45-68`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L45) and [`:207-268`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L207). The exact raw oracle and injected assertions are in [`test_hcu_mp_visible_pvs_sound.py`](../../tools/test_hcu_mp_visible_pvs_sound.py) and its generated fixture source; no production semantics or plan file changed.

## Reproduction and artifact identities

The focused runner is `python3 tools/test_hcu_mp_visible_pvs_sound.py`. Its sandbox invocation compiled the fixture and skipped native execution because this sandbox blocks ILP32 with SIGSYS. The approved native invocation passed with exit code 0:

```sh
build/mp-vps-sound/mp-weather-wind-location build/mp-vps-sound/assets/ \
  > build/mp-vps-sound/native-run-visible.log 2>&1
```

The output contains two visible-PVS rows and 26 lifecycle rows. It remains host-only evidence, with the fixture's existing host-sized arenas; it does not qualify target memory, PCSX2 behavior, geometry collision, PAS combination, SPU2 playback, or all-map visible-PVS runtime coverage.

| Artifact | SHA-256 |
|---|---|
| Runner `tools/test_hcu_mp_visible_pvs_sound.py` | `8f04ea4dae53fb55b266f6692904ae947d02f22526cacb7192a28a45e3239f00` |
| Generated test source | `e20688b1a23acb1d1674a25317d1f108ce6c215baac92505edd1a3c0bc855357` |
| Raw-source golden header | `b63a17744b9676226666a218c842fa5e8699f4a283c6dc871638b0c1afe0bdd4` |
| ILP32 executable `build/mp-vps-sound/mp-weather-wind-location` | `3c7698d06ceedb3d5bf2f3b1377fa462047197665f84b9f7198684a7e50ddafa` |
| Link map | `bbcc67aff0e5d342ff42733607d96a4190320298be1a5be44ff1fac4b8530d37` |
| Native run log | `09dde4e5bdedae0bb4f1b6d1834d3700143038ad91d6d789c3d904697c2ffc08` |
| Blood Gulch package | `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011` |

Inspected source pins: halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
