# M1 physical placement evidence (2026-10-20)

## Result

The M3 physical-memory gate in `/home/ai/Desktop/HCU plan` passes for the current
combined parent-entry image in both PCSX2 interpreter and recompiler modes. The
image reaches `HALO_PS2_LOCAL memory-ready canaries=10`. This is a current-hash
emulator result; it is not evidence from a physical console, does not exercise
OPL/optical storage, and does not establish a rendered scene or retail-map fit.

## Frozen inputs

| Input | Value |
|---|---|
| Parent commit | `e671ce625a81301da110ad9b64ccf87397b45d2f` |
| halo-ce-universal commit | `d9ca6d07b7378e04b88199978b1cf5f7011cd6de` |
| halo-ps2 commit | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Combined ELF | `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` |
| ELF SHA-256 | `c813542d890d797c94c0db23a367b6bf54afe4e1cf97d3cfbd4e5dde0e4b4d3d` |
| Link map SHA-256 | `1fe429f1215dd908f5072145f048e86ae1cba8c2783cbbba3c032f738d081484` |
| BIOS SHA-256 | `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b` |
| PCSX2 SHA-256 | `0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea` |

The source of these measurements is the matching `source_inputs`, `physical_placement`,
and ELF records in `build/hcu-parent-link-probe/result.json`, joined to both guest
`result.json` records by the physical gate. Do not pair these measurements with
other historical ELF hashes.

## Address proof

The link report and both guest observations agree on the following EE intervals:

| Allocation | Start | End (exclusive) | Evidence |
|---|---:|---:|---|
| ELF PT_LOAD | `0x00100000` | `0x004fcc64` | Guest-loaded ELF range; one PT_LOAD, file end `0x002f8a04` |
| CRT NOBITS (`_fbss.._end`) | `0x002f8ac0` | `0x004fcc64` | 2,114,532 bytes, zeroed by startup before `main` |
| Startup `boot_malloc` result | `0x004fd080` | `0x019f8dd2` | 22,002,706 bytes measured from returned pointer to actual end |
| Untouched reserve | `0x01a00000` | `0x01f80000` | 5,767,168 bytes; begins after 29,230 bytes of alignment/allocator gap |
| High kernel/stack reservation | `0x01f80000` | `0x02000000` | 524,288 bytes |
| PCSX2-observed EE thread stack | `0x01fdf000` | `0x01fff000` | 131,072 bytes; entirely within high reservation |

The low `0x00000000..0x00100000` kernel/communication reservation is below the
ELF. The probe accounts for one PT_LOAD with `p_filesz=2,066,948` and
`p_memsz=4,181,604`; the PT_LOAD memory end is `_end=0x004fcc64`. Runtime malloc
starts at `0x004fd080`, leaving the observed 540-byte CRT/allocator gap after
`_end`. The exact boot request includes 310 bytes for guard/alignment overhead.
`tools/hcu_parent_link_probe.py` rejects overlapping PT_LOAD, NOBITS, startup
allocation, reserve, and kernel regions; `tools/test_hcu_boot.py` independently
compares runtime addresses and capacities to that hash-bound report.

### Arena observations

The guarded allocator carved nine non-overlapping arenas from the single backing
allocation. Capacities remain unchanged; resident gameplay is reduced by the
charged CRT BSS amount. Bootstrap consumption and observed high-water values are:

| Region | Base | Capacity | Used / high-water |
|---|---:|---:|---:|
| `resident_gameplay` | `0x004fd090` | 4,701,212 | 4,214,784 |
| `current_bsp` | `0x00978cc0` | 6,291,456 | 2,097,152 |
| `texture_cache` | `0x00f78cd0` | 4,194,304 | 0 |
| `dynamic_simulation` | `0x01378ce0` | 2,621,440 | 0 |
| `dma_commands` | `0x015f8cf0` | 1,179,648 | 0 |
| `streaming` | `0x01718d00` | 1,572,864 | 0 |
| `checkpoint` | `0x01898d10` | 524,288 | 0 |
| `audio` | `0x01918d20` | 524,288 | 0 |
| `frame_scratch` | `0x01998d30` | 393,216 | 0 |

Each arena has 16-byte boundary guards before and after it (ten guard pairs,
310 bytes maximum total alignment slack). The guest printed the expected
`memory-ready canaries=10`; the host tests separately prove that guard damage,
short backing, exhaustion, and reinitialization are detected/handled.

## Guest runs

| Mode | Result file | Settings SHA-256 | Outcome |
|---|---|---|---|
| Interpreter | `build/hcu-ps2-closure/emulator-m1-interpreter-7001e61468c94020996b5ba338104ce2/result.json` | `ced91fd90abcd2f8d588e7f23c7beeefefa6668dc7e50d489a32816f658edbb7` | Passed `m3-memory-ready`; physical checks all true |
| Recompiler | `build/hcu-ps2-closure/emulator-m1-recompiler-24ad9e54518f4a479274dae04dffc29a/result.json` | `0c1b600b76ee41dca499d73154dea3c846c0e48c7f6192698be1c2b007dc7210` | Passed `m3-memory-ready`; physical checks all true |

Both runs identify the same parent/HCU/halo-ps2 commits and ELF hash. Neither is
expected to reach game initialization: this is an early memory-ready checkpoint.

## Verification

- `python3 tools/hcu_ps2_m0_gate.py`: closed, 9 checks, 0 errors.
- `python3 tools/hcu_ps2_m1_physical_gate.py --run <interpreter result> --run <recompiler result>`: closed, 2 guest runs, 0 errors.
- `PYTHONPATH=. pytest -q tests/test_hcu_v2_guard.py tests/test_hcu_parent_link_probe.py tests/test_hcu_boot_physical.py tests/test_hcu_m1_physical_gate.py tests/test_resource_accounting.py tests/test_hcu_allocation_ownership.py`: 22 passed, 1 skipped, 549 subtests passed.

The M1 physical-placement gate deliberately establishes only placement,
non-overlap, exact-image provenance, and canary integrity. OPL USB/SMB/HDD,
optical-disc reads, real-PS2 stack/reservation confirmation, M1 startup services,
and any map/render acceptance remain separate requirements.
