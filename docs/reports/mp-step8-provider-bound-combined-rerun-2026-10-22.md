# Step 8 provider-bound combined multiplayer rerun

## Result

The existing all-map combined fixture was rebuilt and rerun against the current shared source tree. In one native ILP32 host process it binds the candidate tag, BSP, texture, audio, dynamic, and claims spans through HCU's real PS2 memory provider, then completes two load/query/unload cycles for each of the 13 stock multiplayer maps. Each cycle retains that map's decoded `TEXS`, emitted `LMn`, and scenario-selected `OTEX` while CE collision/PVS/weather/sound queries run. Campaign is excluded.

The verifier passed all 26 map/cycle rows. Maximum normal texture-owner high-water was 2,144,672 / 4,014,928 bytes; the intentional corrupt-CRC attempt peaked at 2,550,720 bytes and rolled back; shared section-scratch high-water was 98,352 / 524,288 bytes. This rerun closes the reproducibility seam between provider-bound owner setup and the combined all-map fixture for the exact source files hashed below. It is diagnostic host evidence, not a production recarve, EE placement, rendered-game, bots/co-op, or Step 8 acceptance result.

## Run

Candidate preparation:

```sh
python3 tools/test_hcu_mp_candidate_topology.py \
  --include-relocation-tail --pad-texture-boundary-8 \
  --with-textures build/mp-texture-runtime/1792684440364070518/assets \
  --bind-provider-layout
```

The sandbox blocked execution of the retained ILP32 binary with SIGSYS, as expected by the runner. The same retained binary was then run outside that restriction, followed by the verifier:

```sh
build/hcu-mpct-tail-pad8-1792688465527390945/retained/mp-weather-wind-location \
  build/hcu-mpct-tail-pad8-1792688465527390945/retained/assets/ textures \
  > build/hcu-mpct-tail-pad8-1792688465527390945/retained/combined-texture-run.log 2>&1
python3 tools/verify_hcu_mp_candidate_combined_textures.py \
  build/hcu-mpct-tail-pad8-1792688465527390945/retained --pad-texture-boundary-8
```

Verifier output: `validated 26/26 CE map+texture rows; max texture peak=2144672/4014928; max CRC rollback peak=2550720`.

## Identity

The parent, CE, and PS2 submodule HEADs were respectively `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The parent and submodule worktrees were dirty; exact fixture/runner hashes below identify the measured local files.

| Artifact | SHA-256 |
|---|---|
| Retained ILP32 executable | `c4659f1da711ac2f5a17e90e479225c848c89ebb2b20ccb3fa903a5d201ae42a` |
| Link map | `eb42ce22542e2031ef7e6b5c03dfab9bc37b6075e999bd1cfd0b7c0670be8992` |
| 26-row run log | `e07d4674c42c31555cc1073e1c5a81971d42a35e18e59a084f98484d19429905` |
| Verified run manifest | `6fa7ed18a7be53bd924ff28a50c5d970ffcd17b39ee561d59db6ac17f5ed2b88` |
| CE fixture `tests/hcu_mp_capacity_main.c` | `6e48d6bcff1743553522cbbab538b002091c70e7e45e1a0ef07a4d435b569d3f` |
| Texture bridge `tests/mp_texture_candidate_owner.c` | `64d043703e37c626b182d0cb83eab35a62a6352324418798a2ad31dcac55aa6d` |
| Candidate runner | `9e3146b61ed644102a6a01d8bb2c4bf6d758febe98c7df59da87d613d821877c` |
| Verifier | `73761d834e293efac7a919e70ab83a5b629578d3119079fafb459946c4970dec` |

Artifacts remain in ignored build output at `build/hcu-mpct-tail-pad8-1792688465527390945/`.

## Limits

The profile is a test-only guarded recarve of one 10 MiB map-plus-texture store. The run does not demonstrate that production's separate `current_bsp` and `texture_cache` regions can be merged without a reviewed ownership/guard change. It also does not upload or render texture pages, measure cache pins/eviction or simultaneous frame DMA, exercise full object packs or the dynamic simulation pool, run bots/co-op, or execute on R5900/PCSX2. The prior combined fixture report's coverage and these limits remain applicable; this report only binds that same fixture result to this rerun's exact local hashes.
