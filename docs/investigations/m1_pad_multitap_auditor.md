# m1_pad_multitap_auditor

## Mission

Audit the 1–4 player PlayStation 2 pad and multitap sampling path in the parent engine (`pad.h` / `pad.c`), the HCU DualShock→XInput semantic adapter (`halo_ps2_input.h` / `ps2_input.c`), and whether `ps2_input_publish_state` is wired into any machine or simulation tick. Relate findings to local co-op input needs described in `docs/hcu-local-coop-audit.md`. Report-only; no implementation claims.

## Inputs examined

| Area | Path |
|------|------|
| Prompt contract | `docs/investigations/_prompt_contract.md` |
| Local co-op closure | `docs/hcu-local-coop-audit.md` |
| HCU PS2 input adapter | `submodules/halo-ce-universal/port/ps2/include/halo_ps2_input.h`, `submodules/halo-ce-universal/port/ps2/src/ps2_input.c` |
| HCU manifest / entry | `submodules/halo-ce-universal/port/ps2/port.json`, `submodules/halo-ce-universal/port/ps2/src/ps2_main.c` |
| CE input consumer | `submodules/halo-ce-universal/source/input/input_xbox.c`, `submodules/halo-ce-universal/source/input/input.h` (`MAXIMUM_GAMEPADS = 4`) |
| Parent pad service | `submodules/halo-ps2/engine/src/platform/pad.h`, `submodules/halo-ps2/engine/src/platform/pad.c` |
| Parent runtime use | `submodules/halo-ps2/engine/src/main.c`, hybrid fixture `src/platform/main.c` |
| Host semantic test | `tests/hcu_ps2_input_main.c`, `tests/test_hcu_ps2_input.py` |
| Closure / placeholder docs | `docs/hcu-ps2-closure.md`, `docs/hcu-ps2-platform-placeholder-audit.md`, `plans/5.hcu-remake.md` |
| Generated platform stubs | `build/hcu-ps2-closure/all/ps2_platform.c` (sampled for `CreateThread`, `XInitDevices`) |
| Evidence baseline SHAs | `_prompt_contract.md` (parent `a2575e9…`, HCU `c406a41…`) |

## Findings

### Executive answer: is `ps2_input_publish_state` wired?

**No — not to hardware, not to the parent pad service, and not to the CE main loop.**

- **Internal wiring only:** `ps2_input_publish_state` is implemented in `ps2_input.c:35–54` and called exclusively from `ps2_input_publish_dualshock` at `ps2_input.c:64` (disconnect) and `ps2_input.c:80` (connected sample). A repository-wide search shows no other call sites; the parent never includes `halo_ps2_input.h`.
- **Public contract vs runtime:** `halo_ps2_input.h:6–8` documents tick-boundary publication by the “PS2 pad service.” That service exists in the parent (`pad.c`) but does not call either publish entry point.
- **CE consumption path is live in `halo-local.elf`:** `input_xbox.c` drives gamepads through `XGetDeviceChanges` → `XInputOpen` → per-frame `XInputGetState` inside `input_get_device_states` (`input_xbox.c:765–985`), invoked from `input_frame_begin` (`input_xbox.c:701–705`), which the in-game main loop calls before `input_abstraction_update` (`main.c:3514–3516`). Without prior publication, `s_connected` in `ps2_input.c` stays zero, so **no insertions, no handles, and `input_has_gamepad` is always false** (`input_xbox.c:516–524`).
- **Host test wiring:** `tests/hcu_ps2_input_main.c` calls `ps2_input_publish_dualshock` directly (not the parent sampler). That validates adapter semantics in isolation; it is not a machine bridge.

### Parent pad / multitap path (1–4 players)

**Initialization (`pad_init`, `pad.c:17–44`)**

- Loads IOP ROM modules `XSIO2MAN`, `XMTAPMAN`, `XPADMAN`; calls `mtapInit()` and `padInit(0)`.
- Opens multitap per physical port with `mtapPortOpen(port)` when successful (`pad.c:30–32`).
- Treats missing controllers as non-fatal (`pad.c:33`); optional bounded wait for port 0 slot 0 stability (`pad.c:34–40`).

**Raw sampling (`pad_read_sample` / `read_sample`, `pad.c:60–114`)**

- Two physical ports (`PAD_MAX_PORTS 2`), four slots per port (`PAD_MAX_SLOTS 4`) — `pad.h:16–17`.
- Slots 1–3 require `pad_multitap_connected(port)` (`pad.c:109–112`); slot 0 does not.
- DualShock mode + pressure mode when supported (`pad.c:78–81`).
- Active-high `buttons` via `0xFFFF ^ b.btns` (`pad.c:84–86`); sticks and eight pressure bytes mapped to Xbox analog-button order in `sample->analog[8]` (`pad.h:25–26`, `pad.c:91–98`).

**Logical four-player mapping (`pad_poll_players`, `pad.c:116–134`)**

| Condition | Player 0 | Player 1 | Player 2 | Player 3 |
|-----------|----------|----------|----------|----------|
| Multitap on port 0 | port 0 slot 0 | port 0 slot 1 | port 0 slot 2 | port 0 slot 3 |
| No multitap on port 0 | port 0 slot 0 | port 1 slot 0 | port 1 slot 1 | port 1 slot 2 |

- Slot &gt; 0 on a port requires multitap on that port (`pad.c:130–131`). So **four players without a port-0 multitap need a multitap on port 1** for players 2–3 (slots 1–2). Player 3 never maps to port 1 slot 3 in the no–port-0-tap table (`pad.c:118–120`).
- Return value is a count of successful `read_sample` calls, not “players present” (`pad.c:131–133`).

**Runtime usage in parent tree**

- `pad_poll_players` has **zero call sites** outside `pad.c` (only defined in `pad.h` / `pad.c`).
- Parent `engine/src/main.c` uses legacy `pad_poll(fly_input *)` for fly-camera input (`main.c:242` area per grep).
- Hybrid repo fixture `src/platform/main.c` uses `pad_init` + `pad_poll` only (`src/platform/main.c:147–158`), not `pad_poll_players`.
- Parent engine links `-lpad -lmtap` (`submodules/halo-ps2/engine/Makefile:41`).

**Conclusion (parent):** Multitap-aware sampling and a stable four-player selector are **implemented but not integrated** into any gameplay or HCU bridge. Only single-pad fly-camera polling runs in known parent entry points.

### HCU DualShock → XInput adapter (`ps2_input.c`)

**Port model**

- `PS2_INPUT_PORTS` = 4 (`ps2_input.c:5`), aligned with CE `MAXIMUM_GAMEPADS` (`input.h:17`).
- Static state: per-port `XINPUT_GAMEPAD`, connection bitmask `s_connected`, edge-reporting `s_reported`, open handles `s_devices[]` (`ps2_input.c:14–17`).

**`ps2_input_publish_state` (`ps2_input.c:35–54`)**

- Clamps `port >= 4`.
- Disconnect or null state: clears connection bit and zeroes cached gamepad (does **not** increment packet number on disconnect).
- Connect: sets bit; `memcmp` on full `XINPUT_GAMEPAD`; increments `packet_number` only when payload changes (`ps2_input.c:49–52`).

**`ps2_input_publish_dualshock` (`ps2_input.c:56–81`)**

- Maps low-byte libpad-style digital bits to `wButtons` (D-pad, Start, Back, thumb clicks) — `ps2_input.c:67–74`.
- Does **not** map face buttons (Cross/Circle/Square/Triangle) or shoulder digital bits into `wButtons`; CE expects those through `bAnalogButtons[0..7]` (`input_xbox.c:271–281`, `xdk_xbox.h:31–38`).
- Sticks: `stick_axis` centers at 128, scales ×256, optional Y invert (`ps2_input.c:19–27`, `75–78`).
- Copies `analog[8]` when non-NULL (`ps2_input.c:79`). Parent `pad_sample.analog` order matches Xbox indices (`pad.h:25–26`, `pad.c:91–98`).

**CE-facing XInput API (`ps2_input.c:83–151`)**

- `XGetDeviceChanges`: one-shot insert/remove masks vs `s_reported` (`ps2_input.c:93–96`).
- `XInputOpen`: requires `s_connected` bit, `slot == XDEVICE_NO_SLOT`, valid gamepad type (`ps2_input.c:106–107`) — matches CE `XInputOpen(..., port, 0, NULL)` (`xdk_xbox.h:43–50`).
- `XInputGetState`: returns cached state and `dwPacketNumber` from device struct (`ps2_input.c:145–147`).

**Manifest:** `ps2_input.c` is a listed port source (`port.json:20`). `ps2_main.c` does not reference pad APIs (`ps2_main.c:14–20`).

**Downstream CE behavior (when wired)**

- Dead-zone on sticks applied in `input_get_device_states` via `fix_dead_zone` (`input_xbox.c:964–975`), not in the adapter — consistent with M1 plan text (`plans/5.hcu-remake.md:145`).
- Analog button thresholds updated per frame (`input_xbox.c:937–948`).
- `input_initialize` calls `input_get_device_states` once (`input_xbox.c:1226`); ongoing polling is on the main thread via `input_frame_begin`, not the keyboard worker thread (`input_keyboard_thread` only flushes rumble, `input_xbox.c:1164–1173`).

### Split between parent ELF and `halo-local.elf`

- Parent `halo-ps2.elf` compiles `pad.c` but has no HCU symbols.
- `halo-local.elf` compiles `ps2_input.c` via HCU PS2 closure (`tools/hcu_ps2_link.py:35–36` exempts XInput symbols from generated stubs) but **does not compile parent `pad.c`**.
- There is **no shared object or documented IPC** in-tree that copies `pad_sample` across that boundary. `port.json` `machine_entry` is CE-only (`ps2_main.c`).

### Relation to `docs/hcu-local-coop-audit.md`

- Local co-op simulation hooks are adapted in `ps2_coop.c` (25 symbols, per audit doc), but **M5/M22 acceptance** requires two local command streams and split-screen / vehicle / checkpoint behaviors (`hcu-local-coop-audit.md:24–26`).
- Without the pad→XInput bridge, **player 2 (and 3–4) have no physical command stream into CE**, regardless of `network_coop_*` / `coop_scripts_*` simulation closure. Input is a **prerequisite** for co-op gameplay verification; the co-op audit does not claim pad wiring is done (`hcu-local-coop-audit.md:28–30`).

### Semantic / mapping risks (for future bridge)

1. **Intended bridge shape:** For each `player` in `0..3`, call `ps2_input_publish_dualshock(player, samples[player].connected, samples[player].buttons, lx, ly, rx, ry, samples[player].analog)` after `pad_poll_players(samples)` — logical player index maps 1:1 to CE `gamepad_index` / XInput port.
2. **`pad_sample.buttons` vs converter:** Parent uses `pad.h` constants (e.g. `PAD_BTN_CROSS 0x4000`); converter digital path uses libpad low-byte masks (`0x0010` D-pad up, etc.). After `0xFFFF ^ b.btns`, low-byte layout matches libpad; face buttons are carried via `analog[]`, which matches CE’s analog-button path.
3. **Host test scope:** `hcu_ps2_input_main.c` exercises D-pad / Start / Back / thumbs and analog bytes, not face-button bitmask→`wButtons` (face buttons are not mapped there by design).
4. **Hotplug ordering:** CE opens handles on insertion edges (`input_xbox.c:794–804`). Bridge must publish disconnect (`connected=0`) so `XGetDeviceChanges` reports removals before handles go stale.
5. **Keyboard / memory units:** PS2 edge stubs empty keyboard queue (`ps2_edge.c:74–78`); memory-unit `XGetDeviceChanges` still runs in CE but has no PS2-specific adapter — likely inert for campaign, unknown for UI prompts that expect MU.

### M1 gate status (this slice only)

| Check | Status |
|-------|--------|
| Parent multitap + 4-player sample API | Implemented (`pad.c`) |
| Parent 4-player API used at runtime | **Not wired** |
| HCU XInput semantic adapter in link | Yes (`port.json`, closure) |
| `ps2_input_publish_state` machine wiring | **Not wired** (internal + host test only) |
| Physical / guest input verified | **Open** (docs and plans agree) |
| Local co-op input for M22 | **Blocked** on bridge + verification |

## Interface contracts for the main agent

1. **Bridge function (to be owned by machine integration, not yet present):** Once per simulation tick, before CE `input_frame_begin`:
   - `pad_poll_players(pad_sample samples[4])` (parent side, or equivalent samples if pad code is linked into the combined image).
   - For `port` in `0..3`: `ps2_input_publish_dualshock(port, samples[port].connected, …)` **or** build `XINPUT_GAMEPAD` and call `ps2_input_publish_state(port, connected, &gamepad)`.
2. **Index contract:** CE port `n` = logical player `n` from `pad_poll_players` output array index, not raw PS2 `(physical_port, slot)` unless a deliberate remapping table is added.
3. **Do not bypass `ps2_input_publish_state` for normal pads** unless supplying a fully formed `XINPUT_GAMEPAD`; `publish_dualshock` is the supported mapping from `pad_sample`.
4. **CE already polls XInput on the main thread** via `input_frame_begin` → `input_get_device_states`; the bridge must publish **before** that call in the same frame/tick.
5. **Parent-only renderer paths** may continue using `pad_poll` for flycam; that does not satisfy CE player control.

## Recommended tests / fixtures

1. **Existing (keep):** `tests/test_hcu_ps2_input.py` — connection masks, packet stability, stick scaling, analog copy.
2. **Bridge unit test (host):** Mock four `pad_sample` structures through `publish_dualshock` → assert `input_get_device_states` would see four insertions and correct `bAnalogButtons` for face/shoulder/trigger (extend `hcu_ps2_input_main.c` or harness).
3. **Mapping table test:** Documented multitap topologies from `pad_poll_players` (port-0 tap vs port-1 tap) → expected connected bits on CE ports 0–3.
4. **Hotplug sequence:** Connect P0 only → publish → `XGetDeviceChanges`; add P1–P3 → per-port insertions; remove P2 → removal bit and `XInputGetState` failure while handle non-null until CE closes.
5. **Integration (M1/M5):** Combined EE image or agreed IPC: one frame with `pad_poll_players` + publish + `input_frame_begin`; assert `input_has_gamepad(0)` and, with two pads, `input_has_gamepad(1)` for split co-op fixture from `hcu-local-coop-audit.md`.
6. **Hardware (deferred per parent ADR policy unless requested):** PCSX2 pad plugin / physical multitap matrix for four logical players.

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m1_startup_guest_path_auditor` | Where tick boundary runs relative to `input_frame_begin` in the combined machine; whether parent and HCU share an address space or need RPC. |
| `m1_platform_callsite_auditor` | `CreateThread` / `WaitForSingleObject` stubs vs `input_initialize` (`ps2_platform.c`); `XInitDevices` no-op impact. |
| `m0_runtime_ownership_auditor` | Single owner for “machine services” vs CE shell in final ELF layout. |
| Co-op / M22 track | `hcu-local-coop-audit.md` scenarios assume working per-player input abstraction after bridge. |

## Open questions

1. **Final link model:** Will parent `pad.c` be linked into `halo-local.elf`, or will a thin EE shim duplicate sampling? No in-tree decision file found.
2. **Tick rate alignment:** Parent targets 30 Hz; CE tick vs `input_frame_begin` rate in PS2 shell — unverified without guest boot.
3. **Player 3/4 without multitap:** `pad_poll_players` cannot populate slots 1–3 on a port without multitap — is four-player campaign in scope for PS2 SKU or only 2-player co-op? `ps2_coop.c` comment mentions “at most two players” for vehicle seats (`ps2_coop.c:107` area per grep) — may limit required ports to 2 even though APIs are four-wide.
4. **Rumble:** `input_keyboard_thread` / `input_flush_rumble` path — no `XInputSetState` implementation audit in this pass (likely generated stub).
5. **Direct `ps2_input_publish_state` callers:** None today; confirm whether any future path bypasses DualShock mapping (e.g. test automation injecting raw `XINPUT_GAMEPAD`).

## Handoff summary

The **HCU side of the contract is implemented and link-closed**: four-port XInput semantics, `ps2_input_publish_state` as the single writer of adapter state, and `ps2_input_publish_dualshock` as the intended `pad_sample` translator. **`ps2_input_publish_state` is not wired to the parent pad sampler or any tick** — only to `ps2_input_publish_dualshock` and the host test. The **parent multitap path is real** (`pad_init`, `pad_read_sample`, `pad_poll_players`) but **`pad_poll_players` is unused**; runtime pad traffic is **`pad_poll` on port 0 slot 0 only**. Closing M1 physical input requires an explicit **machine bridge** at the tick boundary plus integration tests; local co-op M5/M22 work in `hcu-local-coop-audit.md` depends on that bridge for per-player CE input, independent of `ps2_coop.c` simulation symbol closure.

## Corroboration

### Agreements

- **m1_startup_guest_path:** Tick boundary for `input_frame_begin` must sit after machine pad sample in combined image — startup chain reaches `main_loop` before map load; bridge belongs at sim tick, not shell-only init.
- **m1_platform_callsite:** `XInitDevices` / thread stubs may affect `input_initialize` ordering; quad XInput is **`SKIP`** (real `ps2_input.c`) — not among **562** generated bodies.
- **m3_player_movement:** CE player control requires published XInput before `input_frame_begin`; parent `pad_poll` flycam does not satisfy gameplay input.
- **m0_runtime_ownership:** Single writer for adapter state (`ps2_input_publish_state`) matches single sim owner (HCU).

### Conflicts

- None on four-port API shape; **scope** question (2 vs 4 players on PS2 SKU) remains open in Round 1 — does not block M1 bridge for P0–P1.

### Updated handoff

1. Implement tick bridge: `pad_poll_players` → `ps2_input_publish_dualshock` per port **before** CE `input_frame_begin` (**m3_player_movement** tier-A fixture).
2. Extend `tests/test_hcu_ps2_input.py` with multitap topology cases; defer PCSX2 hardware matrix unless M1 gate demands it.
3. Co-op: `network_coop_active()==FALSE` path is closed in link; bridge is still required for local campaign control.
