# M2 Step 7: MP fog-side sound-environment selector fixture

Status: implemented and native fixture run passed. This closes the previously
uncovered *selector path* for the three stock MP BSPs with valid fog-plane
chains; it does not close Step 7 as a whole, prove target RAM capacity, or test
sound playback.

## What changed

`tests/test_hcu_mp_capacity.py` now derives a fog-side sound-environment case
from each raw Xbox source map for Beaver Creek, Chill Out, and Damnation. It
validates the source BSP fog-plane/region/palette chain, resolves the fog and
sound-environment tags in the source tag index, reads the source-selected
cluster palette and background reference, and derives a camera position on the
selected side of the raw plane equation. It rejects malformed source extents,
unexpected fog overrides, missing sound-environment tags, and degenerate
planes rather than weakening assertions.

The resulting goldens are passed through the existing package-backed CE
fixture. `tests/hcu_mp_sound_environment_host32.c` now checks the real CE
`scenario_get_sound_environment()` selector while the observer camera has the
source-derived position. For fog cases it additionally calls
`scenario_get_fog_region_index()` and requires the expected region before
checking the cluster sound-environment palette, selected environment priority,
background index, interpolation, water-boundary state, and unchanged BSP / CE
collision-user state. Existing fog-free map cases retain their prior behavior.

## Source-derived findings

All three source fog definitions are `fog ` tags in their corresponding map
tag indexes. Their flags are `0`, plane distance is `0`, background override
is `NONE`, and sound-environment override is `NONE`. Therefore CE's
position-dependent fog lookup finds region 0 at the derived camera point, but
the fog candidate does not compete for sound-environment priority. CE then
selects the cluster's sound-environment palette entry; its source definition
has priority `0` in all three cases. This follows the source control flow in
`submodules/halo-ce-universal/source/scenario/scenario.c:1310-1384` and the
field layout in `source/scenario/fog_definitions.h:29-46` and
`source/sound/sound_environment_definitions.h:31-52`.

| Map | BSP / cluster | Fog datum | Derived point `(x,y,z)` | Region | Selected environment datum | Priority | Background datum |
|---|---:|---:|---|---:|---:|---:|---:|
| Beaver Creek | 0 / 0 | -397670698 | `(0, 0, -1000.6204)` | 0 | -397408550 | 0 | -397539624 |
| Chill Out | 0 / 0 | -401209696 | `(0, 0, -1000.3167)` | 0 | -400882011 | 0 | -401078622 |
| Damnation | 0 / 0 | -397539624 | `(0, 0, -1003.9309)` | 0 | -397211939 | 0 | -397408550 |

The raw map source hashes are Beaver Creek
`eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a`, Chill Out
`52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb`, and
Damnation `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c`.
The selected package hashes are respectively
`4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc`,
`727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0`, and
`ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d`.

## Execution and artifacts

`python3 -m pytest -q -rs tests/test_hcu_mp_capacity.py` compiled successfully,
then skipped the native ILP32 launch because the sandbox returned SIGSYS. The
exact generated native executable was therefore run outside that sandbox:

```text
build/m2-mp-weather-wind-13/mp-weather-wind-location \
  build/m2-mp-weather-wind-13/assets/
```

It exited successfully and printed the fixture's terminal summary:
`mp-host-collision 13-map CE hit/PVS/reload matrix passed`. The fixture itself
asserts two reload cycles for each of the 13 maps; the new sound-selector
rows for map IDs 103 (Beaver Creek), 107 (Chill Out), and 108 (Damnation)
reported the expected region 0 and priority 0. The run was a native host
ILP32 execution, not an R5900/PCSX2 or retail-PS2 test. The CE map-loading
fixture reports its established 16 MiB tag and 8 MiB BSP arrays; those are
host test capacities, not target RAM evidence.

The executable's stdout was not retained by the direct invocation, so no log
hash is claimed. Artifact/source hashes for this run are:

| Artifact | SHA-256 |
|---|---|
| `tests/test_hcu_mp_capacity.py` | `3631fa38434725759efc6c9979feab9370d109faccf0360f07f91c4d9edeca14` |
| `tests/hcu_mp_capacity_main.c` | `f95da967d258e1cdc98140d6f982d09f53177134a6d86801a2ace469cdc97354` |
| `tests/hcu_mp_sound_environment_host32.c` | `886a94875d108becafa0d0570ea2bf21d69a3c2906e7312e3e2f4edd1dfece73` |
| `tests/hcu_game_sound_host32.c` | `831975ee03b24e8e29dc185619cf028443e75488fb3b2f7f1703026538e0b40f` |
| Native fixture `mp-weather-wind-location` | `6384890a0adce6195bc150a78609be2de9b606899c017770a62b8321ebc4e392` |
| Fixture link map | `940bea8a574d1635733edde428e91aa151af4db825cf35752cf53f46ada2cc5a` |
| Generated sound-environment golden | `b1fcbc14bcc5bc341059636f52a3624d9034e7c85748231518c43c80a5ffbaf0` |
| Generated source inventory | `73ab20b7ecf5b0c78cf87ee41aad5f8103ab51694453f7b08c30488ed1324716` |

The checked source pins at test time were halo-ce-universal
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` and Halo-64
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

## Halo-64 comparison and limits

Halo-64's `source/scenario/scenario.c:1187-1270` uses the same ordering relevant
to this fixture: inspect the camera's fog-derived environment first, then
compare the cluster palette candidate by priority. This is a comparative
source check only; its N64 port and memory limits are not PS2 evidence. HCU's
current CE-derived selector additionally bounds-checks the cluster palette
index before dereferencing it (`scenario.c:1358-1364`), while the compared
Halo-64 code checks only against `NONE`. The fixture deliberately invokes the
HCU implementation and does not import that N64 behavior.

This case validates the selected fog-region side for the supplied cluster
location. It does not prove the synthetic point is an interior point found by
world point-to-leaf traversal, nor does it exercise competing non-NONE fog
sound-environment priorities: the three retail fog definitions have no such
override. It also does not test Xbox audio playback, SPU2/IOP services, target
capacity, or target timing.
