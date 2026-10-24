# Halo-64’s Halo CE adaptation: evidence and PS2 transfer notes

Investigation date: 2026-10-21  
Source pins inspected: Halo-64 `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`; halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.  
Scope: explain the concrete adaptation model that made the decompiled CE game run on N64, and distinguish reusable architecture from N64-only cuts. This is a source investigation, not an endorsement of copying N64 behavior into PS2.

## Finding in brief

Halo-64 succeeds by compiling substantial CE simulation code essentially in place, while replacing Xbox-specific machine services, renderer, menu, sound playback, and asset loading with a purpose-built N64 platform layer and offline-converted cartridge assets. It makes explicit `HALO_N64` source changes where necessary, supplies stateful adapters for CE call sites, and generates typed stubs only for intentionally excluded subsystems. It also changes simulation cadence and capacity for an N64 with 8 MB Expansion Pak memory and a 93.75 MHz CPU; these are hardware-specific tradeoffs, not generic porting patterns. See [Halo-64 README](../../submodules/halo-64/README.md#how-it-runs-on-an-n64) and [N64 port manifest](../../submodules/halo-64/port/n64/port.json).

For PS2, the transferable lesson is *ownership and adapter discipline*: retain CE gameplay/identity, adapt the machine and presentation seams, convert assets offline, test the complete rooted call closure, and never treat a no-op as safe until the caller’s semantics are known. Do not copy Halo-64’s stubbed campaign systems, single-precision substitutions, particle suppression, or reduced update cadence wholesale. The current HCU PS2 port explicitly targets little-endian R5900 ILP32 and defines larger CE-style capacities; the CE game-state constants are starting constraints, not proof that the total working set fits the parent’s measured 32 MiB memory map ([PS2 prefix](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_prefix.h), [PS2 limits](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h)).

## What Halo-64 actually compiled and replaced

### Build/source boundary

`port/n64/port.json` is an explicit source-selection contract. It excludes CE `ai/`, `hs/`, `networking/`, `sound/`, `rasterizer/`, `render/`, `cutscene/`, editor, and related subsystems, while explicitly adding saved-game state, pure camera math, selected rasterizer math helpers, and the AI pathfinding sources. The same manifest compiles normal CE objects, units, physics, weapons, items, game modes, HUD logic, and first-person weapon logic. The README describes this as CE game sources minus those named systems, with adapters in `port/n64/src/` and game-side glue in `port/n64/game/` ([manifest](../../submodules/halo-64/port/n64/port.json#L11-L68), [architecture overview](../../submodules/halo-64/README.md#how-it-is-put-together)).

The exclusions were product-specific: N64’s multiplayer cartridge supports local split-screen, but it does not ship HaloScript, full campaign AI, the Xbox renderer, Xbox menus, or Halo’s sound engine. The README lists a separate campaign cartridge as a partial level with simplified Firefight-style AI, no Marines or scripts/cutscenes, and incomplete second BSP ([README feature scope](../../submodules/halo-64/README.md#whats-in-it)). Thus “Halo-64 uses CE source” does not mean “all CE subsystems are available.”

### ABI and compiler compatibility

`port/n64/include/halo_n64_prefix.h` is force-included before game units. It checks big-endian MIPS, defines `HALO_N64` and `HALO_LINUX`, establishes the XDK compatibility surface (`_X86_`, 16-bit `wchar_t`, calling-convention and MSVC keyword shims, inline/weak semantics), and includes N64 pool limits ([prefix](../../submodules/halo-64/port/n64/include/halo_n64_prefix.h)). The build generator selects VR4300/o64, `-Os`, function/data sections, link-time optimization, small-data settings, and a custom linker script; these are N64 ABI/build choices, not a template for R5900 ([build flags and link](../../submodules/halo-64/tools/n64_build.py)).

The PS2 analogue is already visibly different: `halo_ps2_prefix.h` checks little-endian MIPS, sets `HALO_PS2` while leaving `HALO_N64`/`HALO_LINUX` unset, and statically asserts 32-bit pointer/long plus 16-bit wide character ([HCU PS2 prefix](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_prefix.h)). Preserve the target-native ABI proof rather than importing N64 endian assumptions or the `HALO_LINUX` define.

### Local-game and input adaptation

Halo-64 retains CE’s `main_loop` and local connection machinery. Before `main_setup_connection`, `n64_game_setup()` chooses a map/game or runs the N64 menu; `main_loop` then calls the original setup and time initialization ([`main_loop`](../../submodules/halo-64/source/main/main.c#L3210-L3240)). The N64 menu is a replacement for the Xbox `ui.map` shell, hooked by `main_menu_load()` ([menu bridge](../../submodules/halo-64/source/main/main.c#L1119-L1142)). During player creation, `main.c` creates CE players with N64-selected controller, color, team, and port data, then adds bots via a separate N64 callback ([local player bridge](../../submodules/halo-64/source/main/main.c#L829-L864)). `input_xbox.c` adapts N64 controller state to CE’s XInput-shaped input contract; the platform layer implements files/time/input calls against libdragon ([manifest/build overview](../../submodules/halo-64/README.md#how-it-is-put-together)).

This is a useful pattern for PS2: keep the CE game loop and its player/input semantics when feasible, and adapt pad data at the platform edge. Do not confuse N64’s bypass of the `ui.map` menus or its bots’ separate action injection with required PS2 architecture; this PS2 product includes campaign and HaloScript scope.

### Render/UI adapters are stateful, not empty drawing stubs

The N64 removes CE’s Xbox renderer, but its `n64_render_game.c` is not just a collection of empty rasterizer functions. It owns CE-facing render globals and defaults, advances `render.frame_index`, prepares per-window cameras/frusta and visible clusters, calls `first_person_weapon_render_update()`, and calls `interface_draw_screen()` so HUD timers, motion sensor state, messages, and pickup prompts continue to evolve; actual geometry drawing is delegated to `n64_render.c` ([render adapter](../../submodules/halo-64/port/n64/game/n64_render_game.c#L1-L20), [frame/view path](../../submodules/halo-64/port/n64/game/n64_render_game.c#L535-L705)). Halo-64’s notes specifically identify frame index, camera/frustum, first-person node matrices, HUD updates, viewport bounds, and vblank/frame advancement as required despite omitting the source renderer ([NOTES: renderer dependencies](../../submodules/halo-64/port/n64/NOTES.md#what-the-game-needs-from-the-excluded-renderer)).

The transferable rule is to classify a graphics-facing call by its state effects before replacing it. A draw-only call can be a backend operation; a call advancing lifecycle, camera, HUD, first-person, or effects state needs a real adapter. PS2 should retain GS/VU1/DMA rendering but still use equivalent stateful CE-facing bridges.

### Sound, files, tags, and converted assets

The N64 does not open retail Xbox caches as-is at runtime. Its tools convert map tags to a compact, relocated big-endian image; render geometry, textures, animations, HUD art, particles/effects, and sound data are converted into target-specific assets or streamed cartridge files ([README conversion architecture](../../submodules/halo-64/README.md#how-it-is-put-together), [NOTES map data](../../submodules/halo-64/port/n64/NOTES.md#map-data-toolsn64)). The platform side supplies an N64 sound mixer and CE-facing sound callbacks; source notes describe soundbank offsets, streamed sound data, and voice selection. This is why the generated sound stubs do not imply that weapon/audio selection is absent: CE-facing selection logic is bridged to a separate N64 mixer.

For PS2, offline conversion and a hardware-facing playback backend are reusable concepts, but target formats, cache sizes, DMA rules, storage paths, and SPU2 scheduling must be PS2-specific. HCU’s PS2 limits currently declare a 2 MiB tag cache and much larger Xbox-like game state/object/effect pools, while the parent manages a separate 32 MiB allocation/arena map; those figures must be reconciled by measured placement rather than by copying N64 counts ([PS2 capacities](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h)).

### Typed stubs and their limits

`tools/n64_stubs.py` generates C stand-ins from the actual declarations for omitted modules, with selected semantic overrides such as null network-server/client accessors, `NONE` for absent sound/rasterizer allocations, and local-only damage/object rules. The generated file explicitly includes AI, HaloScript, networking, render/rasterizer, sound, Bink, and editor declarations; many AI and script entry points return zero/no-op ([stub generator](../../submodules/halo-64/tools/n64_stubs.py), [generated stubs](../../submodules/halo-64/port/n64/game/n64_stubs_generated.c)). `tools/n64_link_check.py` checks for missing inline bodies that could otherwise silently branch to address zero (README build description).

The good transferable practice is generated signatures plus link-closure validation and explicit semantic overrides. The unsafe pattern would be copying N64 no-op stubs into PS2 for required game behavior. Halo-64 can omit actor AI and HaloScript because its multiplayer product and its partial campaign deliberately do not provide the full original campaign; this PS2 remake’s scope includes campaign/AI/scripts. A call returning `NONE` may be safe for an unrendered optional decal, but not for object identity, collision, damage, time, map lifecycle, camera/HUD state, or effects whose gameplay semantics are needed.

## N64-specific changes that made the game fit/run

### Memory and data representation

Halo-64’s documented target has 8 MB with Expansion Pak and a 93.75 MHz CPU versus Xbox’s 64 MB/733 MHz. It uses compact map tags, relocated images, streamed models/textures/animations, CI4/I4 textures, per-frame/per-map heap budgeting, reduced rendering buffers, and a measured game-state trim after initial allocation ([README hardware/memory section](../../submodules/halo-64/README.md#how-it-runs-on-an-n64), [`n64_game_state_trim`](../../submodules/halo-64/port/n64/game/n64_game.c#L790-L830), [CE hook in `game_state.c`](../../submodules/halo-64/source/saved%20games/game_state.c#L271-L278)). `halo_n64_limits.h` includes notably small object/effect pools and token-only particle pools; campaign has separately measured larger ceilings ([N64 limits](../../submodules/halo-64/port/n64/include/halo_n64_limits.h)).

The PS2 has 32 MB, a 294.9 MHz-class R5900 EE, GS/VU1 and DMA rather than N64 RSP/RDP. Therefore map streaming, bounded pools, no-runtime-allocation discipline, cache instrumentation, and target-specific compression are transferable; the N64’s exact pool sizes, cache layout, texture formats, frame-buffer budgets, tick throttling, and “one token” effect capacities are not. PS2 must preserve required campaign AI/HaloScript/effects and still prove they fit, particularly because the PS2’s GS render payloads and IOP/SPU2 stores create different memory boundaries.

### CPU scheduling and altered tick semantics

Halo-64 modifies `game_time.c` to call `n64_game_tick()` around each CE tick, allowing N64 Firefight/bot/effect/audio work to be budgeted, and caps local frame elapsed time differently on slow hardware ([`game_time_update`](../../submodules/halo-64/source/game/game_time.c#L625-L642), [`main_update_time_unthrottled`](../../submodules/halo-64/source/main/main.c#L2287-L2310)). It also has N64-only object update/pose selection: held/attached objects preserve parent timing; holstered weapons still run their weapon-specific update while other object work is deferred; idle scenery and far/unseen AI poses can run at reduced cadence ([object scheduling helpers](../../submodules/halo-64/source/objects/objects.c#L3780-L4096)). README summarizes every-fourth-tick static objects, reduced far poses, half-rate vehicles, staggered AI/pathfinding, and culling effects nobody can see/hear ([performance summary](../../submodules/halo-64/README.md#how-it-runs-on-an-n64)).

These are behavior changes and need N64-specific justification plus parity/acceptance testing. On PS2, start with CE cadence; optimize only after EE profiling, and then prove determinism, collision/damage correctness, replay stability, animation attachments, and campaign/script behavior. R5900 floating-point and GS/VU throughput are not the VR4300/RSP bottlenecks.

### Effects and AI

Halo-64’s N64 `particles.c` and `particle_systems.c` return `NONE` before constructing these objects because their point physics alone would cast roughly 1,500 rays/second in Firefight; no particles, particle systems, or contrails are created by CE in that build ([particle early-out](../../submodules/halo-64/source/effects/particles.c#L829-L850), [particle-system early-outs](../../submodules/halo-64/source/effects/particle_systems.c#L400-L465), [NOTES rationale](../../submodules/halo-64/port/n64/NOTES.md#performance-october-2026)). Actor AI is excluded from the N64 compile closure; it supplies its own Firefight/bot decision code around selected CE movement, weapons, damage, pathfinding, and object/physics primitives ([manifest](../../submodules/halo-64/port/n64/port.json#L11-L24), [N64 glue inventory](../../submodules/halo-64/README.md#how-it-is-put-together)).

For PS2, keep CE AI, script runtime, effect creation, and effect lifecycle in the HCU gameplay owner unless a precisely scoped unsupported effect is proven nonessential. Replace drawing only with GS/VU1 adapters; do not replace effect simulation with a no-op. The PS2 currently declares 1,024 particles, 64 particle systems, 512 system particles, 256 contrails, and 1,024 contrail points—those are merely declared capacities and still require actual RAM/high-water validation ([PS2 limits](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h)).

## Transfer matrix for the PS2 port

| Halo-64 pattern | Transfer to PS2? | PS2 treatment |
|---|---|---|
| Keep CE simulation sources as the authoritative object/weapon/damage engine | Yes | HCU owns authoritative CE identity and simulation; parent/halo-ps2 owns GS/VU/DMA, pack readers, pad/time/storage and playback services. |
| Explicit source manifest, ABI prefix, per-port compile tests, and link-closure gate | Yes | Keep `HALO_PS2`, little-endian R5900 ILP32, and compile/link reports bound to exact pins. Do not define `HALO_N64` or inherit its endianness/o64 ABI. |
| Typed stubs generated from source declarations, with explicit exception list | Yes, cautiously | Stub only proved unreachable or intentionally unsupported platform/drawing calls; stateful and gameplay functions need owners. Make closure + semantic disposition a gate. |
| Stateful renderer/HUD/first-person adapters despite omitting the original renderer | Yes | Preserve CE camera, frame, HUD, first-person and effect time/state; parent bridge emits one stable render snapshot to GS/VU. |
| Offline asset conversion and streaming | Yes, target-specific | Convert Xbox cache/tag/geometry/bitmaps to PS2-native packs; retain source provenance and bounded runtime readers; honor EE DMA alignment and distinct GS/IOP/SPU2 memory. |
| 8 MB pool values, single-token particles, removed AI/HS/sound systems | No | PS2 is 32 MB and campaign scope requires AI/scripts/effects. Derive capacities from ELF + high-water evidence and fixture coverage. |
| Reduced tick cadence and N64 float math substitutions | Not by default | Use only after measured EE hotspots, explicit parity analysis, and replay/collision/weapon/campaign acceptance tests. |
| N64 renderer, RSP/RDP texture formats, libdragon sound mixer, cartridge layout | No | Implement with parent GS/VU1/DMA, PS2 DVD/OPL sources, and SPU2 services. |

## Implications for the active HCU M2–M4 work

1. Treat Halo-64 as a source/architecture comparator, not as the feature specification or a pool-size oracle.
2. For each rooted HCU external, classify it as simulation/state advancement, platform service, presentation state, drawing-only operation, or excluded product feature. The Halo-64 `n64_render_game.c` case demonstrates why call names alone are insufficient.
3. Keep the streaming/relocation approach target-specific and bounded; test exact extents, malformed input, late visitor failure, cleanup, and retry before raising map admission limits.
4. Preserve CE cadence by default. Any PS2 scheduling deviation should have an EE profile, object/weapon/collision test, and render-schedule-invariance evidence.
5. Do not infer that PS2 campaign is solved because the existing N64 campaign cartridge exists. Halo-64 campaign explicitly omits scripts, cutscenes, Marines, and a second structure BSP, and uses separately simplified AI.
6. The PS2’s declared limits currently permit much more behavior than N64, but the integrated parent/HCU memory map and retail map assets must prove these allocations are physically possible. The 32 MiB total includes static ELF/BSS, boot backing, arenas, and kernel reservations; no single HCU header can prove the whole-game budget.

## Source index

- Halo-64 overview and machine limits: [README](../../submodules/halo-64/README.md#how-it-runs-on-an-n64)
- N64 build/source selection: [port.json](../../submodules/halo-64/port/n64/port.json)
- N64 ABI prefix and capacity header: [prefix](../../submodules/halo-64/port/n64/include/halo_n64_prefix.h), [limits](../../submodules/halo-64/port/n64/include/halo_n64_limits.h)
- Main loop/local player/menu adaptation: [`main.c`](../../submodules/halo-64/source/main/main.c)
- Render-state bridge: [`n64_render_game.c`](../../submodules/halo-64/port/n64/game/n64_render_game.c), [N64 notes](../../submodules/halo-64/port/n64/NOTES.md#what-the-game-needs-from-the-excluded-renderer)
- Tick and object cadence: [`game_time.c`](../../submodules/halo-64/source/game/game_time.c), [`objects.c`](../../submodules/halo-64/source/objects/objects.c)
- N64 typed stubs: [`n64_stubs.py`](../../submodules/halo-64/tools/n64_stubs.py), [`n64_stubs_generated.c`](../../submodules/halo-64/port/n64/game/n64_stubs_generated.c)
- PS2 ABI and capacities for contrast: [HCU PS2 prefix](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_prefix.h), [HCU PS2 limits](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h)

