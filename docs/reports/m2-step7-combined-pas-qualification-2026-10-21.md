# M2 Step 7 — CE combined sound PAS qualification

**Result: a package-backed host ILP32 consumer subcheck passed; Step 7 remains
open.** The test invokes Halo CE's actual private `compute_combined_pas()` and
`location_potentially_audible()` over each BSP after its real package-backed CE
publication. It compares the active cluster bitvector against an independent
oracle derived from the original Xbox BSP bytes. It does not exercise the
looping-sound mixer, sound asset decode, SPU2 playback, target-sized residency,
or a PCSX2 gameplay map.

## CE behavior exercised

`compute_combined_pas()` clears the active bitvector, visits the four local
player slots, ignores disconnected players and cameras whose cluster is
`NONE`, then ORs clusters whose encoded distance maps to a value strictly
below 256 ([`game_sound.c:1054-1098`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L1054)).
The test-only bridge includes this CE translation unit unchanged and exposes
only narrow call wrappers ([`hcu_game_sound_host32.c:1-105`](../../tests/hcu_game_sound_host32.c#L1)).
`location_potentially_audible()` is called for each valid cluster and for
`NONE`; out-of-range locations are intentionally not passed because CE's
`match_assert` contract rejects them ([`game_sound.c:1099-1108`](../../submodules/halo-ce-universal/source/sound/game_sound.c#L1099)).

The fixture configures two real local-player slots with raw-source-selected
camera clusters, a third active player with camera cluster `NONE`, and a fourth
disconnected slot whose camera would otherwise contribute. For each published
BSP it checks the exact CE bitvector words and every cluster's audibility
result, then checks that active players with `NONE` cameras yield an empty
active PAS. It also snapshots `sound_cluster_data` before and after the CE
queries and checks byte identity ([`hcu_scenario_bsp_switch_main.c:1185-1265`](../../tests/hcu_scenario_bsp_switch_main.c#L1185)).
Only words containing active clusters are compared because CE clears only the
active byte extent; unused trailing global bitvector words are not part of this
query's contract.

## Independent raw-map oracle

The Python oracle reads each source map's original BSP extent, bounds the
`sound_cluster_data` span, and derives each unordered-pair byte using CE's
triangular index rule. It calculates each candidate listener PAS and requires
two listeners with exclusive contributions in both directions when the BSP
contains such a pair. It falls back to one effective listener only for a BSP
whose rows cannot prove a union; the package-level test still requires at
least one true two-listener union in each map. See
[`test_hcu_scenario_bsp_switch.py:250-357`](../../tests/test_hcu_scenario_bsp_switch.py#L250)
and the generated CE golden writer at
[`test_hcu_scenario_bsp_switch.py:1268-1293`](../../tests/test_hcu_scenario_bsp_switch.py#L1268).

Source-derived listener selections and number of audible clusters:

| Source BSP | Listener clusters | Two-listener union proven | Audible clusters |
|---|---:|---:|---:|
| `a30_a` | 0, 1 | yes | 28 |
| `a30_b` | 0, 6 | yes | 37 |
| `a50_exterior` | 0, 0 | no distinct contribution exists | 12 |
| `a50_muster` | 0, 2 | yes | 55 |
| `a50_hangar` | 0, 1 | yes | 80 |
| `a50_control` | 0, 23 | yes | 44 |

The CE source names bit 7 as an unreachable marker, but the actual PAS
expression masks that bit and then compares the low seven bits against 127;
thus `0x7f` and `0xff` are excluded by the strict threshold, while another
high-bit value would be treated according to its low seven bits. The source
oracle deliberately follows the expression rather than inferring semantics
from the enum name. The audited six BSP payloads contain no high-bit values
other than `0xff`, so this test does not claim that unusual encoding is
present in retail data.

## Verification and identities

Exact native command (the ordinary sandbox run cannot execute the ILP32 binary
and reports `SIGSYS`; this pass used the approved native execution path):

```sh
APPIMAGE_EXTRACT_AND_RUN=1 PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Result: **1 passed, 1 deselected, 2 package subtests passed in 137.15 s**.
The test runner also verifies every emitted per-BSP PAS row against the
raw-source oracle.

- Parent commit: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (worktree dirty).
- HCU / halo-ps2 / Halo-64 pins: `6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
  `71183bb0a9adc586cd267b2780c82bbc12cfd95b` /
  `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.
- `game_sound.c` SHA-256: `c57cd2ea070b7b249c87c1b8a18647c9afbd2895df3cd4a92eab76ab4a3b5c83`.
- CE BSP accessor implementation/header SHA-256:
  `00bbb359e4cf9129f8cf0076e7754584a31060836be0460a17cbaef24f8e51eb` /
  `dde75cddffc975c95395f525b60e5d125b5904beb106a3916dccbc295c26afe2`.
- C bridge / C scenario fixture / Python runner SHA-256:
  `7f6661593aba96ce5874de9531a0ed12371743deb3e003a82fa550202f5aa1a9` /
  `e775a31b2db1cf9fd7f2e6b3483ecf5cefabda93af2aa4ded2df9a82ad02a382` /
  `822d67b6c7d815c1b06f2ae13cb01ecbe2d3f0b36c6d4704dde57ab5d6352e01`.
- Retained ILP32 fixture / link map SHA-256:
  `6585633e7f3406fce37732defcfa063577bf9ee8297c2f759b790c3d0e0e203f` /
  `9b96016558e41d31980a91f0cc0eea636caa80f61f97c046b8d8fff4c60a786a`.
- Manifest SHA-256: `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.
- Source map / HP2 package hashes: `a30` map `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`, package `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`; `a50` map `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`, package `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`.

## Limits / remaining Step 7 and 8 gates

This closes only the `game_sound.c` combined-PAS and audibility host subcheck
for these six package-published BSPs. It does not establish listener-camera
placement in gameplay, looping-sound scheduling/selection, sample/ADPCM decode,
SPU2 output, sound-environment priority/ties, fog-priority/valid fog-region
queries, wind, weather simulation, geometry/visibility consumers, or the
remaining collision topologies and independent expectations. It does not
prove target-sized allocation: the current package transaction uses
overprovisioned host owners, including an 8 MiB BSP cache and 16 MiB owner/cache
arrays. Step 8's all-map capacity and binding design still blocks production-
sized BSP query evidence. Keep Steps 7 and 8 open.

Halo-64 is relevant only as a boundary comparator: its notes retain CPU camera,
frame, and first-person state even where drawing is excluded
([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)); it is
not evidence for CE sound behavior, PS2 capacity, or mixer equivalence. REA was
not applicable: this test executes known CE source against hash-bound source
maps, packages, and a host fixture rather than reverse-engineering an opaque
binary.
