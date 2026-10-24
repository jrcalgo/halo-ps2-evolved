# D20 real-game initialization closure: blocker inventory

Date: 2026-10-21
Status: **blocked before host execution; no CE subsystem was stubbed**
Scope: first separate D20 gameplay-oracle slice, rooted at real CE
`game_initialize()` → `game_load()` → `game_unload()`.

## Outcome

I did not produce a host executable or claim a D20 gameplay pass. Before adding
any adapters, I linked the existing full HCU PS2-compiled object set with the
real CE initialization/load/unload roots and `--gc-sections`. This retained
gameplay closure has **279 distinct unresolved symbols with live relocations**
(512 undefined names in the relocatable object's symbol table, including names
without live relocations). That is too broad to safely answer with generated
success stubs. The unresolved references cross thread synchronization, file
and save services, audio, render/state, memory/cache, input, runtime helpers,
and CE/game services. The report therefore records a staged blocker, not a
substitute smaller gameplay workload.

The diagnostic regression test passed because it successfully reproduced and
classified this blocking closure, and asserted that no unresolved symbols
were hidden. It **does not** mean `game_initialize`, `game_load`, or
`game_unload` executed. The artifact is an R5900 relocatable link, not a
host-ILP32 executable, PS2 ELF, PCSX2 run, D20 load, or rendered scene.

## Exact closure evidence

The build used `build/hcu-ps2-closure/all-no-bootstrap-memory/objects.rsp`,
the exact full PS2 source-object set from the existing closure result, and roots
`game_initialize`, `game_load`, `game_unload`, and `game_map_loaded`. The test
relinks these objects without generating stubs and records the exact caller
sections, owning source candidates, and triage class for each live unresolved
symbol in the machine-readable inventory.

| Evidence | SHA-256 / value |
|---|---|
| HCU source pin | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| HCU PS2 manifest | `a64018b2b0de1edf0660ad4e9019d2738216db2ae5352c8a8503899ff9d6f93d` |
| Existing all/no-bootstrap closure result | `58920f92393c15ce177b60dc608cf602b697f1fc0e2f85f34304b1f0b1082c78` |
| Object response file | `6da131e6f1386bd762d8484235e957d86b3ac2ddcd5a04b0ffb64f7ecdc07739` |
| New rooted relocatable object | `2abd8fb372aabd12650e516f078fd58ab0dec0f6d49a1dc8701cdc2a4bfdc0ee` |
| Link map | `48a18502c1a0d8df09dd782551ec0751e853525e7d850480e8e4c74ec3cb8adb` |
| Complete per-symbol JSON inventory | `750fcfa4e97490711204c8e0b48b2536eff45ec3b84ec9d103064a8d0515e1a3` |
| Inventory generator/test | `tests/test_hcu_ce_d20_game_initialize_closure.py`, SHA-256 `56ecee505c075b09f08a3bf19bd80dc3c5ebff2e1d9478145aa34cd752190a75` |
| Compiled HCU source units | 370 (341 selected CE source units plus the closure's port sources) |

The generated files are under `build/hcu-m2-d20-game-init-closure/` and can be
recreated with:

```sh
python3 -m pytest -q -s tests/test_hcu_ce_d20_game_initialize_closure.py
```

The reviewed D20 source inputs remain the host-oracle package SHA-256
`44f96afa5b9fa20efd5c2dcb2d0f1ca436953d436e8b40015c7dce6e759005fe1`
(25,516,032 bytes) and schema manifest SHA-256
`ac06b15e1f0cb9882051b79ef37e127eb13ce37f8218a7d7561afbbf37a1c8c2`.
These are source/package identities only; this closure attempt did not load
them. (The package digest is also recorded by the preceding D20 scenario/BSP
oracle report.)

## Inventory summary

Categories are triage labels, **not approvals**. The JSON records every symbol,
its live relocation caller sections/functions, and candidate source owners.

| Triage class | Count | Representative unresolved calls / implication |
|---|---:|---|
| Thread/synchronization boundary | 8 | `CreateThread`, `CreateMutexA`, `WaitForSingleObject`, `SwitchToThread`; cannot silently report initialized synchronization or make waits succeed. |
| File/storage boundary | 14 | `CreateFileA`, `ReadFile`, `WriteFile`, save-game `XFind*`/`XCreateSaveGame`; file and save call sites need explicit host test ownership and failure semantics. |
| Audio boundary | 39 | DirectSound device/stream creation, playback, spatialization, and `sound_cache_sound_hardware_lock/unlock`; CE sound selection/state cannot be replaced by an empty “audio success” adapter. |
| Render boundary/state | 37 | Rasterizer model/window/widget submissions, `rasterizer_present`, render debug and model metadata; distinguish required CPU camera/frame/model state from drawing. |
| Memory/cache boundary | 8 | `GlobalAlloc`, `GlobalMemoryStatus`, `physical_memory_get_*`; bind real guarded host spans before CE's actual allocator is exercised. |
| Input/platform boundary | 1 | `XInputDebugGetKeystroke`; isolate platform input at the interface and preserve CE input state. |
| Compiler/runtime helper | 15 | Includes double-precision helpers and atomic compare/exchange; resolve through a selected host runtime or measured PS2 implementation, not fake values. |
| Network/co-op behavior | 18 | `network_coop_note_*`, `network_game_get_game`, coop spectator calls; each must be proven non-required for the selected local path before no-op treatment. |
| Other unresolved CE/platform dependency | 139 | Includes debug globals, error/reporting paths, Bink, editor, tag/cache APIs, libc functions and profile/system calls; this class is intentionally broad and requires per-call-site reclassification. |
| **Total** | **279** | Full symbol + relocation + source-candidate inventory: `build/hcu-m2-d20-game-init-closure/inventory.json`. |

Examples of exact caller ownership from that inventory:

| Unresolved symbol | Live caller section | Source candidate | Why it blocks a blanket adapter |
|---|---|---|---|
| `CreateThread` | `.text.create_thread` | `source/bungie_net/common/thread_win32.c` | A CE subsystem may expect a worker to run and later report completion. |
| `DirectSoundCreate` | `.text.dsound_initialize` | `source/sound/sound_dsound_xbox.c` | Sound initialization is part of the real CE init sequence; PS2 playback ownership is a real platform interface, not successful DirectSound. |
| `ReadFile` | `.text.file_read`, `.text.HATRawLoopRead`, `.text.HATRun` | `source/tag_files/files_windows.c`, `source/input/HaloAutoTest.c` | File APIs are mixed across tag loading and optional auto-test paths; callers must be separated before deciding the minimum adapter. |
| `rasterizer_present` | `.text.halt_and_catch_fire` | `source/main/main.c` | Error/panic presentation is a stateful failure path, not ordinary scene drawing. |
| `network_coop_note_hud` | scripted HUD setter/clearer sections | `source/interface/hud_messaging.c` | Local no-op behavior needs an explicit inactive-co-op proof and a regression assertion. |
| `physical_memory_get_tag_cache_base_address` | cache read/tag-load sections | `port/ps2/src/ps2_cache.c`, `source/cache/cache_files.c` | The host fixture must bind the real cache owner; returning null or success-shaped memory would invalidate scenario loading. |
| `bink_playback_initialize` | `.text.game_initialize` | `source/game/game.c` | An initializer explicitly enters a platform/media boundary; it cannot be omitted while claiming the actual initializer ran. |
| `editor_initialize` | `.text.game_initialize` | `source/game/game.c` | The engine's real ordered initializer contains it; whether it is safely inert on the product path remains to be source- and state-verified. |

## Why this is a genuine blocker rather than merely a long symbol list

CE `game_initialize()` allocates the authoritative `game_globals` and invokes
game time, game mode, allegiance, interface, scenario, camera/observer/render,
objects, structures, collision, players, effects, sound, AI, editor, widgets,
HaloScript, recorded animations, cheats, transport/network-packet,
cinematic,
save, event, input, player UI, Bink, and progress initialization in order
([`game.c:281-331`](../../submodules/halo-ce-universal/source/game/game.c#L281)).
`game_load()` validates options, copies the options into those globals, calls
real `scenario_load()`, and changes `map_loaded` only after success
([`game.c:616-657`](../../submodules/halo-ce-universal/source/game/game.c#L616)).
`game_unload()` can enter progress/render/error paths before calling
`scenario_unload()` and clearing `map_loaded`
([`game.c:754-785`](../../submodules/halo-ce-universal/source/game/game.c#L754)).
That source order is why dropping initializer calls or returning success from
their dependencies would not test the requested CE transition.

The retained CE map path also allocates game state through
`game_state_allocate_buffer()` and initializes its header from the real
game-state subsystem ([`game_state.c:1043-1053`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L1043)).
An executable must bind non-overlapping guarded host buffers via the actual
PS2 memory API and observe the real allocation behavior. The prior D20
scenario/BSP oracle did neither: it calls `scenario_load()` directly and
focuses on CTAG/BSP ownership. Its success therefore remains a separate,
useful lower-layer result, not evidence that this closure ran.

The full set's `game_initialize()` references to `editor_initialize`,
`bink_playback_initialize`, `telnet_console_initialize`, and
`initialize_network_game_packets` must be individually traced to the selected
PS2 product behavior. A per-symbol source reference and explicit state-based
test may establish that a particular platform boundary is safely adapted;
this report does not authorize blanket no-ops. In particular, 139 symbols in
the current “other” triage bucket still need finer semantic classification.

## Staged blocker resolution

1. Reclassify the 139 “other” imports and the render/audio categories against
   exact caller functions in the generated JSON; split executable requirements
   from unreachable debug, error-only, or optional feature paths. Require one
   source reference, owner, disposition, and observable assertion per adapter.
2. Audit initialization call-order and side effects in `game.c:281-331`.
   Keep CE simulation/data initialization real. Only replace calls that cross a
   declared machine-service boundary, with bounded behavior, invocation logs,
   and deterministic error results. Do not stub editor/AI/HS/effects/object
   initialization merely to reduce the import count.
3. Recompile the **host ILP32** closure with the R5900 semantic prefix and
   test-only D20 admission. Inspect its exact rooted import inventory before
   adding the reviewed adapters; do not treat this R5900 relocatable artifact
   as a host run.
4. Add a new host harness with disjoint, guard-wrapped spans bound before
   `game_initialize()`. Track allocators and fail on unbound access, exhaustion,
   unlisted adapters, hidden I/O failure, blocking waits, invalid handles, or
   graphics submission. Any first execution must prove only
   `game_initialize()` → one real D20 `game_load()` → `game_unload()` and clean
   CE globals, then deterministic failure/retry in a fresh state.
5. Only after that gate passes, proceed to real
   `game_initialize_for_new_map()` / authored object and actor placement. Add
   player creation, real tick, identity, and CPU pose as later increments; no
   scene-render inference follows from these simulation checks.

## Halo-64 comparison boundary

Halo-64's `n64_render_game.c` is a useful example of placing console-facing
presentation in an adapter and its `NOTES.md` explains state advancement that
must survive when drawing is absent ([`n64_render_game.c`](../../submodules/halo-64/port/n64/game/n64_render_game.c),
[`NOTES.md:14`](../../submodules/halo-64/port/n64/NOTES.md#L14)). Its explicit
generated stubs and gameplay cuts are not suitable for this CE init closure:
the PS2 target keeps real AI, HaloScript, effects, objects, and gameplay. The
comparison justifies keeping platform adaptation separate from the simulation;
it does not justify dropping unresolved CE state.

## Verification

Command run:

```sh
python3 -m pytest -q -s tests/test_hcu_ce_d20_game_initialize_closure.py
```

Result: **1 passed**. The test relinked the production-compiled R5900 object
set, identified 279 live unresolved imports, wrote the machine-readable
inventory, and asserted representative threading/file/audio/render/save and
input dependencies remain unresolved. This is a successful blocker
reproduction only. No host CE initialization, D20 game load, PS2 guest run,
RAM-fit claim, or visible rendering was performed. `game_initialize()` is
still unexecuted in this first slice, and the first gameplay-oracle gate is
open.
