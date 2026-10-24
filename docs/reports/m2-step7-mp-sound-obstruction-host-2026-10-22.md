# Step 7 MP BSP-consumer audit: sound obstruction

Date: 2026-10-22. This closes one package-backed, native-ILP32 semantic
subcheck for stock multiplayer Blood Gulch. It is not SPU2 playback evidence,
EE/PCSX2 evidence, a Step 7 closure, or Step 8 capacity evidence.

## Consumer coverage audit and selected gap

The MP BSP consumer work already has separate evidence for: relocated fog
plane/location/water/weather selection on Beaver Creek
(`m2-step7-mp-beavercreek-fog-plane-host-2026-10-22.md`); sound-environment
palette selection on a qualifying subset of MP maps
(`m2-step7-mp-sound-environment-host-2026-10-21.md`); and CE wind
initialization/update/current lookup on Damnation
(`m2-step7-mp-wind-package-runtime-2026-10-22.md`). The 13-map fixture
checks package load/unload, collision, and raw PVS-related records. The
all-map weather/palette inventory is raw-data evidence, not all-map runtime
simulation. Existing PAS, obstruction, and sound-distance integration
coverage is principally from campaign fixtures, so the MP sound consumer was
an actionable missing package-backed path.

I added a Blood Gulch test of CE `compute_sound_obstruction()` for a
source-derived pair that is reachable according to encoded sound distance,
but hidden in the listener cluster's PVS. It specifically exercises CE's
non-visible-but-audible occlusion branch, which computes distance-based
occlusion without invoking collision. This is narrower and more precise than
claiming sound playback or testing an ordinary visible sound source.

Source chain:

- `tests/test_hcu_scenario_bsp_switch.py:31-159` parses the retail BSP PVS and
  sound-distance values and independently chooses `hidden_reachable`; the
  selected Blood Gulch tuple is `(from=0, to=17, encoded=53)`.
- `tests/test_hcu_mp_capacity.py:156-187` derives a golden from that raw map,
  computes expected occlusion from CE's documented encoded-distance scaling,
  and emits a generated header. The fixture requires the pair to exist; it
  does not silently skip a missing candidate.
- `submodules/halo-ce-universal/source/sound/game_sound.c:985-1034` obtains
  sound distance and PVS. For a hidden PVS pair under max range it leaves
  obstruction at `0.6`, avoids the visible-PVS collision query, then applies
  `PIN((1 - distance / (cluster_distance + distance)) * 1.4, 0, 1)`.
- `tests/hcu_game_sound_host32.c:62-86` provides test-only CE globals and calls
  the actual included CE consumer. It does not replace its calculation.
- `tests/hcu_mp_capacity_main.c:11-51` first asserts the relocated PVS bit is
  clear and the CE relocated sound-distance accessor returns the independent
  raw encoded byte. It then asserts expected obstruction/occlusion, zero
  collision calls, balanced collision-user state, and unchanged BSP
  publication.
- `tests/test_hcu_mp_capacity.py:327-355` retains and requires two success
  markers—one per package load cycle. The generated golden is copied into the
  artifact directory and its SHA is included in the manifest and source
  ledger (`:339-342`, `:399-402`, `:418-420`).

With distance `80`, encoded distance `53` gives a CE cluster-distance value
of `53 * 256 / 127`; the independently evaluated pinned formula gives
occlusion `0.800539` (tolerance `0.0001`). Both reloads emitted:

```text
mp-sound-obstruction map=102 bsp=0 from=0 to=17 encoded=53 distance=80 obstruction=0.6 occlusion=0.800539 collision_calls=0 status=passed
```

## Verification and artifact identity

Run from repository root, outside the sandbox because native ILP32 execution
is blocked inside it by SIGSYS:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py -v
```

Result: `Ran 1 test in 64.657s — OK`. Additional checks passed:
`python3 -m py_compile tests/test_hcu_mp_capacity.py` and
`git diff --check -- tests/test_hcu_mp_capacity.py tests/hcu_mp_capacity_main.c`.

Retained evidence in `build/m2-mp-host-13-collision/`:

- Native ILP32 executable SHA-256: `22265563c2f2f4b939c01d21308315aeeae778a89cabe004fd25b7e95e2758dd`
- Link map SHA-256: `991215b7bb76809e1333a16f994847e75db2fb489140239c722e1170b5b4ccd4`
- Manifest SHA-256: `3408615bae66118c2e7302f376341120a9c808a51eef6a597047932b6c775d13`
- Run log SHA-256: `6f40272cca6bf53683dbf5deae4cbe577a675ab087339bf9f0f7c4b497dcb45b`
- Retained generated sound-obstruction golden SHA-256:
  `4a390e78803fe521de453725cf06499099d68e494646b9b99220148372db510b`
- Blood Gulch source map SHA-256:
  `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`
- Blood Gulch all-BSP HP2 package SHA-256:
  `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011`
- Schema ELF SHA-256:
  `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`

Pinned revisions in the manifest: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`,
halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The manifest records
`native_ilp32: true`, `ee_evidence: false`, and explicitly labels the arrays
as host semantic capacities, not PS2 RAM proof.

## Exact scope and remaining gates

No production CE or PS2 engine source changed. The update is confined to the
existing MP host fixture/golden and this report. It proves the CE BSP sound
distance/PVS accessors feed the real CE sound-obstruction algorithm correctly
for one reachable-but-PVS-hidden Blood Gulch pair across two relocations.

It does not test SPU2 playback, PAS combination with this MP path, sound
source lifecycle, visible-PVS obstruction collision, multi-listener behavior,
all 13 maps' sound consumers, or target query timing/memory. Fog perception,
weather particle execution/drawing, geometry/lightmap/visibility consumers,
and remaining collision edge/topology cases also remain distinct. Step 7
target-sized query acceptance still depends on Step 8 capacity and EE evidence;
this host fixture must not be presented as closing that dependency.
