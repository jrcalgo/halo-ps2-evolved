# Step 8 diagnostic: candidate map/texture region adjacency and provider bind

## Result

The aligned diagnostic candidate passes an actual native host ILP32 bind against HCU's PS2 physical-memory provider, and the same aligned profile passes the preceding 13-stock-multiplayer-map CE load/query/unload plus PS2 section-texture test. This is a feasibility result only. It does not change production memory budgets, binders, or map admission, and it is not an EE address-placement or rendered-game pass.

The critical interface finding is that the *existing production v2 layout* does not present `current_bsp` and `texture_cache` as one contiguous owner. It inserts a 16-byte canary between them. With the candidate map/BSP + texture split, a single 10 MiB map/texture extent starting at `current_bsp.base` crosses that guard and borrows 179,360 bytes from the texture region; its end is 16 bytes before the current texture region end. Thus, simply passing the proposed slices to the production binder would violate the current guard/region ownership model even though the combined nominal capacity sums to 10 MiB. A production implementation needs an explicit recarve or unified-store ownership design and a reviewed guard policy.

## Exact candidate profile and alignment correction

The earlier unpadded split was:

| Owner | Bytes |
|---|---:|
| Tag cache | 4,477,120 |
| BSP cache | 1,993,704 |
| Tag + BSP | 6,470,824 |
| Texture cache | 4,014,936 |
| Combined | 10,485,760 |

Although all nominal sizes sum correctly, `4,477,120 + 1,993,704 = 6,470,824`, which is 8 modulo 16. Since the CE provider requires each bound base to be 16-byte aligned, texture placed immediately after this BSP extent would be misaligned. The tested pad/repartition moves exactly 8 bytes from texture capacity to BSP capacity, preserving the same total:

| Owner | Tested bytes | Alignment/result |
|---|---:|---|
| Tag cache | 4,477,120 | aligned |
| BSP cache | 1,993,712 | aligned; includes the 8-byte pad |
| Tag + BSP | 6,470,832 | divisible by 16 |
| Texture cache | 4,014,928 | divisible by 16 |
| Map + texture | 10,485,760 | exact 10 MiB |
| Validation claims | 808,856 | disjoint diagnostic store |

The 8-byte correction is not a production sizing recommendation. It tests the real binder's alignment contract against the candidate profile. The runtime section test with this variant loaded all 13 maps for two cycles; maximum decoded texture-owner peak was 2,144,672 / 4,014,928 bytes, maximum intentional CRC-failure transient peak was 2,550,720 bytes, and shared section scratch high-water was 98,352 / 524,288 bytes. These peaks are host fixture observations, not EE render-frame residency or proof that all runtime consumers share these lifetimes.

## Production-layout inspection

`mem_layout_v2_init_charged_guarded` carves the fixed regions in declared order and allocates a guard-sized tail after each region; the v2 region sizes include `current_bsp = 6,291,456` and `texture_cache = 4,194,304` (`submodules/halo-ps2/engine/src/core/mem.c:68-76`, `:110-143`). It uses 16-byte alignment for these regions and records each post-region guard (`:125-140`). The target test initializes this exact function with the recorded 2,114,532-byte charged BSS and measures actual addresses/offsets rather than estimating from JSON.

The measured layout offsets relative to the test backing were:

```text
current_bsp:  offset 4,701,248, capacity 6,291,456
post-BSP guard: offset 10,992,704, length 16
texture_cache: offset 10,992,720, capacity 4,194,304
guard gap between regions: 16 bytes
candidate map end: 179,360 bytes into texture_cache
candidate 10 MiB end: 16 bytes before stock texture_cache end
```

`hcu_memory_bind_parent_v2` presently allocates the tag cache from the beginning of `current_bsp`, then binds the remaining portion as the BSP cache, while texture cache is bound independently from its named region (`src/stream/hcu_memory_bind.c:41-62`). The test does not modify this code. HCU's provider rejects non-16-aligned bases and all overlapping configured regions (`submodules/halo-ce-universal/port/ps2/src/ps2_memory.c:77-110`), then exposes independent tag, BSP, and texture bind APIs (`:141-162`). The existing production budgets remain 6 MiB for current BSP and 4 MiB for texture cache (`config/memory-budget.json`, regions entries).

## Reproduction

The region/binder diagnostic builds the real `mem_layout_v2_init_charged_guarded` implementation and HCU `ps2_memory.c` provider as a host ILP32 binary. Sandbox execution gets SIGSYS on this host, so execute the Python runner in an environment permitted to run the retained 32-bit binary:

```sh
python3 tools/test_hcu_mp_candidate_region_bind.py
```

The runner checks exact production region caps, measured offset/gap/guard placement, all candidate arithmetic, provider alignment and overlap checks, provider readiness, rejected deliberately misaligned rebind, and outer canaries. Successful output:

```text
candidate-v2-regions bsp_off=4701248 bsp_cap=6291456 guard_after_bsp=10992704 texture_off=10992720 texture_cap=4194304 gap=16 candidate_map_end_in_texture=179360 candidate_end_before_texture_end=16 aligned=1
candidate-provider-bind tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760 claims=808856 align=16 disjoint=1 ready=1 canaries=1 status=passed
```

The combined map/query/section test was run with:

```sh
python3 tools/test_hcu_mp_candidate_topology.py \
  --include-relocation-tail --pad-texture-boundary-8 \
  --with-textures build/mp-texture-runtime/1792684440364070518/assets
build/hcu-mpct-tail-pad8-1792685467702906005/retained/mp-weather-wind-location \
  build/hcu-mpct-tail-pad8-1792685467702906005/retained/assets/ textures \
  > build/hcu-mpct-tail-pad8-1792685467702906005/retained/combined-texture-run.log 2>&1
python3 tools/verify_hcu_mp_candidate_combined_textures.py \
  build/hcu-mpct-tail-pad8-1792685467702906005/retained --pad-texture-boundary-8
```

Verifier result: `validated 26/26 CE map+texture rows; max texture peak=2144672/4014928; max CRC rollback peak=2550720; max shared section scratch high-water=98352/524288`.

## Evidence identity

Parent/HCU/halo-ps2 source pins used for the combined map/texture run were `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and `71183bb0a9adc586cd267b2780c82bbc12cfd95b` respectively. The source worktree was dirty; these are HEAD identities, not a claim that every measured byte was produced from a clean checkout. Runner/test and binary hashes bind the actual artifacts below.

| Artifact | SHA-256 |
|---|---|
| Region/binder native ILP32 ELF | `64a5d48829e2a62530abb4bec85100c43df7f7b225db49491b878a0f7d321e9f` |
| Region/binder link map | `34e63a6e3b84b1bcb6237e0ff76cfcdddc1761abb1a943043325e3ad269cbcf1` |
| Region/binder run log | `5270ca605ba66f1c2f9e12501f0d13177d5749df566a76468657540f97db346b` |
| Region/binder manifest | `44528eac0e25e383544d60fcd34372a33f1bdd3dc7a5642b87f140512fbe1afe` |
| Region/binder C fixture | `585f9ef37738be7c5b6424c6437c4a2512742e9cfadef7aec7282bab00198320` |
| Region/binder Python runner | `595afd4470f53103c7e8c1f42359f07dd5b063756691808360825fcb674a301d` |
| Combined aligned candidate ELF | `3587b9b7313471bcbcc5ac82c4c4a8c2e86a662f452bdc31d55c31e8d7a37274` |
| Combined aligned candidate link map | `4fee4facb914362c55fc8a3263b987e130027c32e9e0738f630c67bb20d5f3d7` |
| Combined 26-row log | `e07d4674c42c31555cc1073e1c5a81971d42a35e18e59a084f98484d19429905` |
| Combined manifest | `cee281799eba3a522a424880bb4e7f0d588ce378886db202e2a80e134062e38d` |

Other relevant source hashes and exact run manifests are preserved in `build/mp-candidate-region-bind-1792685580895985160/manifest.json` and `build/hcu-mpct-tail-pad8-1792685467702906005/retained/combined-texture-manifest.json`.

## Follow-up: one-guard combined-owner layout variant

A second test-only layout now constructs the candidate as one guarded owner in the *same sequence* as the v2 carve. It preserves the full resident, dynamic, DMA, streaming, checkpoint, audio, and frame-scratch allocations; replaces `current_bsp` + `texture_cache` with a single 10,485,760-byte span; places one 16-byte canary after that combined span; and builds tag/BSP/texture arena views at the aligned pad8 offsets. It allocates game-state and claims buffers from the variant's resident region, binds the exact tag/BSP/texture/audio/dynamic/claims spans to the real HCU PS2 provider, checks readiness and the provider's rejection of a misaligned texture bind, and verifies arena marks plus all nine outer canaries.

Native ILP32 command (requires execution outside this sandbox's SIGSYS restriction):

```sh
python3 tools/test_hcu_mp_candidate_region_bind.py
```

Result:

```text
candidate-v2-regions bsp_off=4701248 bsp_cap=6291456 guard_after_bsp=10992704 texture_off=10992720 texture_cap=4194304 gap=16 candidate_map_end_in_texture=179360 candidate_end_before_texture_end=16 aligned=1
candidate-guarded-layout combined_off=4701248 combined_bytes=10485760 tag=4477120 bsp=1993712 texture=4014928 guards=9 marks=zero aligned=16 status=passed
candidate-provider-bind tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760 claims=808856 align=16 disjoint=1 ready=1 canaries=1 status=passed
```

The retained manifest is `build/mp-candidate-region-bind-1792685818243704429/manifest.json` (SHA-256 `d9f8cf7d756f9398029151d68a080bc46e342080801a9842765fd0b1bff56183`); the ILP32 ELF is `f0a5fb31fd4ad780e3afb4e479025bf4c3e8e279d3cc93e0dca6ad9509f6ebf0`, link map `2b255a9d7afbb1a64d8c36adbec6da17307ab97cc0cefed18291f993e9aff5a9`, and run log `49c35be181447ce156293b872dcb30e35601a8eb31b7626cf8db770817610926`. Fixture source hash is `55246d703fe2bf5f633a501cce4b8200225796cc8d75b3c88e96915637922f17`; runner hash `f11309d4f39c4a605eef9fa1474a788a6d817cd7b99c9f498fb3826a44ff863f`.

The all-13 CE lifecycle + section-loader fixture now also binds the candidate spans through the real HCU PS2 provider in that same execution. Run it with:

```sh
python3 tools/test_hcu_mp_candidate_topology.py \
  --include-relocation-tail --pad-texture-boundary-8 \
  --with-textures build/mp-texture-runtime/1792684440364070518/assets \
  --bind-provider-layout
```

The sandboxed Python runner compiles the ILP32 image and retains it, but the image itself must run outside the SIGSYS sandbox. Exact retained command:

```sh
build/hcu-mpct-tail-pad8-1792686105053657413/retained/mp-weather-wind-location \
  build/hcu-mpct-tail-pad8-1792686105053657413/retained/assets/ textures \
  > build/hcu-mpct-tail-pad8-1792686105053657413/retained/combined-texture-run.log 2>&1
python3 tools/verify_hcu_mp_candidate_combined_textures.py \
  build/hcu-mpct-tail-pad8-1792686105053657413/retained --pad-texture-boundary-8
```

Verifier passed: `validated 26/26 CE map+texture rows; max texture peak=2144672/4014928; max CRC rollback peak=2550720`. The CE completion marker confirms the 13-map hit/PVS/reload matrix. The provider-bound integrated log SHA-256 is `e07d4674c42c31555cc1073e1c5a81971d42a35e18e59a084f98484d19429905`; aligned combined manifest SHA-256 is `e6188332fcb438fa03aa6c8461e03a2d09e0b92254529f2fee4c926b0ecea2d3`; run/candidate manifest SHA-256 is `44a291669a58fbae8fa443ab2777a6e6ec8e82de873a88dfdacfd4210a8f203c`. The test-only extension removes the fixture's fake tag/BSP getter bodies, calls the provider bind/readiness setup before CE map initialization, and leaves production sources untouched. It uses the same exact aligned profile and owner slices as the standalone guarded-layout test. This closes the earlier integration seam at host ILP32 level, not EE/runtime-render qualification.

## Limits and next engineering seam

This diagnostic variant validates a test-only recarve with one contiguous map+texture owner, the real CE provider API, and all-13 map/query/section-loading in one host ILP32 process. It does **not** alter or prove the production `mem_layout_v2_init_charged_guarded` layout or parent binder. The measured existing inter-region canary proves the stock guarded carve cannot be treated as contiguous without explicit redesign. The tests also do not demonstrate texture safety under a live renderer, GS residency/pinning/eviction, two-player rendering, object packs beyond selected OTEX sections, custom weapon asset closure, EE CPU cost, or PCSX2/console placement. The stock production capacities and map admission remain untouched; Step 8 remains open.

The next valid implementation work is an explicitly reviewed production recarve/binder design, followed by measured renderer texture pins/eviction and target/PCSX2 high-water evidence. Do not paper over the existing 16-byte production guard with a candidate bind that crosses it.
