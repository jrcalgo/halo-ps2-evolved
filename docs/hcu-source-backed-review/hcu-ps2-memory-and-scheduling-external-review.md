# M0 rooted memory-query and cooperative-scheduling review

This review examined three live rooted externals and deliberately leaves each
unapproved. A source-backed review is not permission to accept the current
generated empty body.

| Symbol | Rooted CE call site | Finding | Disposition |
|---|---|---|---|
| `GlobalMemoryStatus` | `source/cseries/debug_memory.c::check_memory_status`, rooted from `source/scenario/scenario.c::scenario_load` | The caller initializes only a separate `memory_status` accumulator. The local Win32 `MEMORYSTATUS status` is otherwise uninitialized before the call; `dwAvailPhys` is read to maintain min/max and can trigger a diagnostic if the range changes by more than 16 KiB. Returning without writing the structure is undefined/incorrect. Other non-rooted CE callers also consume `dwAvailPhys` and `dwTotalPhys`, so a future adapter must have a coherent PS2 memory-accounting contract. | Pending: implement a truthful, deterministic PS2 memory-status mapping and test it against the memory ledger; do not stub as success. |
| `SwitchToThread` | `source/cache/cache_files.c::scenario_tags_load` and `scenario_structure_bsp_load` | Both rooted loops poll an asynchronous read-completion flag. The BSP loop also calls sound-idle after a time threshold. A no-op can busy-spin and monopolize the EE while the IOP/FileXio operation is pending; an incorrect sleep/yield may change completion visibility or audio servicing. The current guest map path reaches a read but does not establish all pending-read interleavings. | Pending: define bounded EE yield plus completion visibility and preserve sound servicing; validate delayed completion, failure, and audio-timeout cases. |
| `Sleep` | `source/main/main.c::main_loop` and `main_rasterizer_throttle` | The live local-game path uses `Sleep(33 - elapsed)` for the 30 Hz idle throttle and `Sleep(1)` while waiting for the renderer's vblank frame index, with a one-second stuck-vblank escape. A no-op produces EE busy loops, can violate intended power/performance behavior, and interacts with timer/frame advancement. Networking's other Sleep callers are outside this rooted closure. | Pending: provide a PS2 delay with measured tick granularity and demonstrate that VBlank/time still advances; no-op is unacceptable. |

The HCU source pin is in `config/dependencies.json`; the checked-out source is
`submodules/halo-ce-universal`. The current generated `ps2_platform.c` contains
an empty `GlobalMemoryStatus` body, so the missing writes are concrete, not
hypothetical. Exact rooted symbols, caller sections, and source hashes remain
in `docs/hcu-ps2-external-review.json`. The relevant completion flags and loop
conditions are covered by the cited CE functions above.

These entries are source-reviewed but remain pending semantic disposition:
M0 cannot close until the adapter and its targeted tests exist or the rooted
callers are removed from the accepted product closure with proof that behavior
is preserved.
