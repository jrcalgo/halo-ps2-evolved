# Step 8 diagnostic: co-resident MP render sections in the section loader

## Result

Added an isolated probe that converts the pinned 13 stock multiplayer maps,
then loads decoded `TEXS`, every emitted `LMn`, scenario-selected `MODL`, and
scenario-selected `OTEX` into one arena with halo-ps2's real HP2 section
loader. The parsers validate every texture/lightmap section and the model
section. Each map is measured independently, matching a one-active-map
working set; no campaign maps are included.

All 13 rows fit the aligned 4,014,928-byte candidate texture/render owner. The
largest is Blood Gulch at **3,954,720 bytes**, leaving **60,208 bytes** in that
owner. Sidewinder reaches 3,697,632 bytes. Section decode scratch peaks at
98,304 / 524,288 bytes for every map. The owner value includes actual
64-byte-aligned section allocations and their padding, not just raw pack
lengths.

This isolates and measures co-resident section ownership that the earlier
texture-only probe omitted. It does not establish that all these sections are
retained simultaneously by the shipping renderer, nor that 60,208 bytes is
sufficient for omitted owners or runtime state. The observation uses a 16 MiB
host arena to avoid truncating the measurement at the candidate limit, then
compares the measured high-water to the candidate. It is not R5900/PCSX2 or
physical EE placement evidence, and it changes no production budget or map
admission.

## Reproduction and identity

```sh
python3 tools/test_halo_ps2_mp_render_owner.py
```

Retained output: `build/mp-render-owner/1792686351606957297/`.

| Artifact | SHA-256 |
|---|---|
| Runner `tools/test_halo_ps2_mp_render_owner.py` | `4e82f99e7056cb3cf726fb01db57dd9e3e142a0cbe92a0d17611e332a083ddf8` |
| C fixture `tests/mp_render_owner_main.c` | `a81d25b51060cdf9e6926cc8edce7727919b708406b43b81d5e9960483d24a26` |
| Host executable | `bcdacdc64aa5ca54d572cfa91a916ae1e28eb1aaaeee43da13883b05ca5c659b` |
| Link map | `cc4b1d3a81a9b879d5a4a5e611da98e4ad6ef422cf5d9c12f79d7618971a74ee` |
| 13-row run log | `ae5a65e6984b5cdb523a23f7c948a47f77a58f85c26b952465bdf2ddbaea2ded` |
| Manifest | `437e5a241ff5184d9ba99ae51062005afe337e5af8a13e4a853122863476e72c` |

The manifest records each map input and generated-section hash, source pins,
per-map output and limitations. `git diff --check --
tools/test_halo_ps2_mp_render_owner.py tests/mp_render_owner_main.c` passed.

## Remaining target gap

The probe gives a useful next target test: bind the same owner through the
diagnostic EE layout and load these exact sections under PCSX2 while measuring
the arena high-water and frame/streaming overlap. Before using it as a
production owner, Step 8 still needs proof for `SCEN`, `ANIM`, `SKY`, complete
object closure, weapon/effect/HUD assets, live texture pinning and eviction,
renderer/DMA overlap, and supported player/bot workloads. The existing
provider-bound all-13 candidate remains host ILP32 evidence; this new result
does not upgrade it to guest or target capacity evidence.
