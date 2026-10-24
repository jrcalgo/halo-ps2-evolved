# Step 8 MP target-sized Sidewinder query probe

**Outcome:** PCSX2 loaded the package-backed stock Sidewinder MP BSP under the
candidate arena capacities, walked all cluster PVS rows, called the CE
collision-vector query, and unloaded the map. This is target-side map/query
evidence only. It does not establish a multiplayer match, co-op/bot behavior,
rendering, texture residency/use, visual correctness, or production admission.

## Reproduction

Build the isolated diagnostic ELF:

```sh
python3 tools/hcu_parent_link_probe.py --step8-mp-capacity-diagnostic
```

Run the gameplay ELF in PCSX2 (the parent-link ELF is not the diagnostic):

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode recompiler --stage m3-memory-ready \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf \
  --success-marker 'HALO_PS2_LOCAL step8-mp-capacity-complete' \
  --timeout 180 --stable-seconds 2
```

The second backend run used the same command with `--mode interpreter`.

PCSX2 runner status was `passed`; its stage outcome remains
`memory-placement-observed-not-playable`. The custom marker was observed after
46.13 seconds, with no guest fault after the marker. Key guest evidence:

```text
HALO_PS2_LOCAL step8-mp-candidate-layout tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760
HALO_PS2_LOCAL map-preflight result=1
HALO_PS2_LOCAL map-mount result=0 active=1
HALO_PS2_LOCAL step8-mp-capacity-query map=sidewinder clusters=35 pvs_rows=35 collision_called=1 collision_hit=0 collision_type=-1
HALO_PS2_LOCAL step8-mp-capacity-unloaded map=sidewinder
HALO_PS2_LOCAL step8-mp-capacity-complete map=sidewinder query_only=1
```

The ray call returned no hit from its test origin; `collision_called=1` proves
the routine was invoked, not a collision-positive oracle. The section visitor's
`raw=1,993,740` includes the 52-byte CBSP transport header. The adapter keeps
that header in a local state buffer and writes only the image plus relocation
table into the BSP destination ([`ps2_cache.c:573-608`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L573)); this resident payload is
1,993,688 bytes, fitting the 1,993,712-byte candidate BSP span by only 24 bytes.
Runtime memory report showed `current_bsp` capacity 6,470,832 bytes with arena
high-water 4,477,120 bytes, and `texture_cache` capacity 4,014,928 bytes. This
does not measure renderer texture residency. The 24-byte BSP margin is extremely
tight and is only qualified for this exact Sidewinder build/input/profile; any
different allocation/alignment or BSP record invalidates the inference.

The same diagnostic ELF was also run in interpreter mode. It reached the same
unique completion marker in 82.47 seconds, with
`failure_after_boundary=false` and identical query output. Interpreter result
SHA-256: `6d3f00c8227e237a267baf191323e6567e58a85ce6e92cd0393e75b9e339b4ce`;
log SHA-256: `d983359454e9e4e502130c35771559f60cf1df274b7f9fd96ceda1b811d3924b`;
run directory:
`build/hcu-ps2-closure/emulator-m1-interpreter-7dde96e2112642078871ea9183d824a8`.

## Inputs and retained evidence

Stock Sidewinder source and package were staged in the ELF's HLE host root:

| Input | Bytes | SHA-256 |
|---|---:|---|
| `build/hcu-parent-link-probe/maps/sidewinder.map` | 48,048,128 | `995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc` |
| `build/hcu-parent-link-probe/maps/sidewinder.hp2` | 3,166,208 | `968ab65ea7ae6fbd15925ed28eb0f8eafc267c78f53150b59b4cc1dea2d017f5` |

The map and package hashes match the pins in `tests/test_hcu_mp_capacity.py`.
The generic boot runner's asset manifest records UI assets only; the explicit
Sidewinder hashes above record the additional diagnostic inputs.

| Artifact | Path | SHA-256 |
|---|---|---|
| Diagnostic ELF | `build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf` | `d94d5d4b2585f6f0ef63e270324b964dc8419a529638f56164c8a3fafa583fec` |
| Link/build report | `build/hcu-parent-link-probe/result-step8-mp-capacity-tagcache-4477120.json` | `9898471274518af8a53e99c02044db44de3e3046c635b663b56602cfeb1c4c7a` |
| PCSX2 result | `build/hcu-ps2-closure/emulator-m1-recompiler-d6f08dd8887b43a4bd28cb450ac60043/result.json` | `371d61b9318ace0028dc162fecaa65f2e8bdd53e5ac13f700c1e6f3b1bea258d` |
| PCSX2 log | `build/hcu-ps2-closure/emulator-m1-recompiler-d6f08dd8887b43a4bd28cb450ac60043/emulog.txt` | `3d1ae67d9ff58e9cecac9967ab2414043fdfc0d948f0e616af31c8c93c074f0e` |
| Interpreter result | `build/hcu-ps2-closure/emulator-m1-interpreter-7dde96e2112642078871ea9183d824a8/result.json` | `6d3f00c8227e237a267baf191323e6567e58a85ce6e92cd0393e75b9e339b4ce` |
| Interpreter log | `build/hcu-ps2-closure/emulator-m1-interpreter-7dde96e2112642078871ea9183d824a8/emulog.txt` | `d983359454e9e4e502130c35771559f60cf1df274b7f9fd96ceda1b811d3924b` |

Source revision pins recorded by the run:

- Parent: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- Halo CE Universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- Halo PS2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`

The opt-in diagnostic source was locally modified at run time; its exact helper
file SHA-256 was `83098414300a51eea726f29be4a34a9db04aeaf8b7de26a1e226fd313132384e`.
All diagnostic behavior is guarded by
`HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` / its dedicated build option. Default
budgets and production map admission were not changed by this probe.
