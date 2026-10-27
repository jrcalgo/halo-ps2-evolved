# M4 C5 integration wiring (for the integrator)

Date: 2026-10-26. Written without editing `src/stream/hcu_main.c` or `tools/ee-world.mk` (Codex owns both
right now). Every line below is for the integrator to apply.

## 1. What the session module does

`src/stream/hcu_c5_session.c` / `.h` is the one entry point for a local setup. `hcu_c5_session_start` runs, in order:

1. `hcu_local_setup_admit` (validate; teardown callback only on acceptance).
2. Stock coop: `hcu_coop_ce_bind` (teams: humans 0, bots 1), then `ops->bots_start` (= `ps2_bots_start`) when the
   binding has bots.
3. Survival: `hcu_survival_init` then `hcu_survival_begin`. Survival with bots is refused (`HCU_C5_SESSION_ERR_MODE`).

Every CE or EE call goes through `struct hcu_c5_session_ops`, so the host test uses fakes
(`tests/hcu_c5_session_main.c`, `tests/test_hcu_c5_session.py`, 4 tests, passing).

Per tick: `hcu_c5_session_tick` (survival resolves here; emits `survival-wave` and `survival-over`).
Bot events: `hcu_c5_session_note_event` (emits `bot-event`). Hash: `hcu_c5_session_report` (emits `session-hash`).

Hash order (FNV-1a 64, u32 as 4 LE bytes, u64 as 8 LE bytes): domain `0xC5500001`, mode, tick, bot hash (u64),
survival state, wave, living humans, active units, reserved units, batch, intermission, waves cleared, enemies
admitted, humans respawned, then the 5 budget kinds x (count, evicted, refused), then kills, deaths, respawns, nav
steps, fights, score events. The Python test recomputes this order from a field dump of the C test.

## 2. Exact lines for `tools/ee-world.mk`

The C5 objects sit next to `hcu_local_setup.o` (currently line 86 of the `EE_OBJS` list). Add these lines to the
`EE_OBJS` list, after `$(WORLD_OUTPUT)/stream/hcu_local_setup.o \`, for the C5 build (gate with `ifeq ($(HCU_C5),1)`
or the same gate the integrator chooses; no source tests `HALO_PS2_SURVIVAL` today, see section 5):

```make
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_c5_session.o \
	$(WORLD_OUTPUT)/stream/hcu_coop_modes.o \
	$(WORLD_OUTPUT)/stream/hcu_coop_ce_bind.o \
	$(WORLD_OUTPUT)/stream/hcu_bot.o \
	$(WORLD_OUTPUT)/stream/hcu_survival.o \
	$(WORLD_OUTPUT)/ps2_bots.o
```

`hcu_coop_modes.o` is not in the brief's list; `hcu_coop_ce_bind.o` calls `hcu_coop_admit` and `hcu_coop_assign_teams`
from it, so it must be linked too. `hcu_local_setup.o` is already in the list.

Rules (put them next to the `hcu_local_setup.o` rule, which is at line 298 of the current file):

```make
$(WORLD_OUTPUT)/stream/hcu_c5_session.o: src/stream/hcu_c5_session.c src/stream/hcu_c5_session.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_coop_modes.o: src/stream/hcu_coop_modes.c src/stream/hcu_coop_modes.h src/stream/hcu_c5_limits.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_coop_ce_bind.o: src/stream/hcu_coop_ce_bind.c src/stream/hcu_coop_ce_bind.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_bot.o: src/stream/hcu_bot.c src/stream/hcu_bot.h src/stream/hcu_c5_limits.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

$(WORLD_OUTPUT)/stream/hcu_survival.o: src/stream/hcu_survival.c src/stream/hcu_survival.h src/stream/hcu_c5_limits.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -c $< -o $@

# ps2_bots.c is the CE side (submodule). Its header includes "hcu_bot.h" and "hcu_c5_limits.h" bare, so the
# stream directory must be on the include path, and HALO_PS2_BOTS must be defined for the CE hunks.
$(WORLD_OUTPUT)/ps2_bots.o: $(HCU_ROOT)/port/ps2/src/ps2_bots.c $(HCU_ROOT)/port/ps2/include/halo_ps2_bots.h
	@mkdir -p $(@D)
	$(EE_CC) $(EE_CFLAGS) $(EE_INCS) -Isrc -Isrc/stream -I$(HCU_ROOT)/port/ps2/include -I$(HCU_ROOT)/source \
		-I$(HCU_ROOT)/port/include -fshort-wchar -I$(HCU_ROOT)/source/cseries -DHALO_PS2=1 \
		-DHALO_PS2_BOTS=1 -c $< -o $@
```

Notes on the `ps2_bots.o` rule:
- `$(WORLD_OUTPUT)/ps2_bots.o` is a placeholder path. Put it under `$(WORLD_OUTPUT)/stream/` if that is where the
  integrator keeps objects, and match the `EE_OBJS` line to it.
- The CE build (the `game_engine.c` and `player_queues_new.c` hunks under `HALO_PS2_BOTS`, lines 4979/5018/7106 and
  398/869) must also be compiled with `-DHALO_PS2_BOTS=1`. No file in this repo sets that define yet. The integrator
  must find where the CE game sources are compiled for the PS2 world and add the define there.
- Include paths: `-Isrc` (for `stream/hcu_*.h`), `-Isrc/stream` (for the bare `"hcu_bot.h"` in `halo_ps2_bots.h`),
  and the CE PS2 include path `-I$(HCU_ROOT)/port/ps2/include`.

Defines: `-DHALO_PS2_BOTS=1` on every CE and `ps2_bots.o` compile unit (section 2 above). `-DHALO_PS2_SURVIVAL=1`
is not referenced anywhere yet; if the integrator wants it, gate the survival objects with it:
`ifeq ($(HALO_PS2_SURVIVAL),1)` around `hcu_survival.o` and the survival branch of `hcu_c5_session.c`. The session
calls `hcu_survival_*` unconditionally, so `hcu_survival.o` must be linked whenever `hcu_c5_session.o` is.

## 3. Exact lines for `src/stream/hcu_main.c` (for the integrator; do not apply from here)

Include and the adapters (put them where the other `#include "stream/..."` lines are, and the adapters after
the includes):

```c
#include "stream/hcu_c5_session.h"
#ifdef HALO_PS2_BOTS
#include "halo_ps2_bots.h"   /* port: submodules/halo-ce-universal/port/ps2/include */
#endif
/* The qualified rows are static in hcu_local_setup.c: see section 4, gap 1 (export an accessor first). */

static int hcu_c5_bots_start_adapter(void *user, const hcu_bot_config *config,
                                     const struct hcu_coop_ce_binding *binding)
{
	(void)user;
#ifdef HALO_PS2_BOTS
	return ps2_bots_start(config, binding);
#else
	(void)config; (void)binding;
	return -1;
#endif
}

static uint64_t hcu_c5_bots_hash_adapter(void *user)
{
	(void)user;
#ifdef HALO_PS2_BOTS
	return ps2_bots_hash();
#else
	return 0u;
#endif
}

static void hcu_c5_emit_adapter(void *user, const char *line)
{
	(void)user;
	printf("%s\n", line);
}
```

Start (at local game setup, in place of the current setup entry, once per match; `rows` is the qualified table,
see gap 1):

```c
static struct hcu_c5_session hcu_c5;
struct hcu_c5_session_ops c5_ops;
struct hcu_c5_session_options c5_opts;
memset(&c5_ops, 0, sizeof c5_ops);
c5_ops.user = NULL;
c5_ops.teardown = hcu_c5_teardown;          /* the map teardown: the integrator's existing function, int(void*, const hcu_local_setup_result*) */
c5_ops.bots_start = hcu_c5_bots_start_adapter;
c5_ops.bots_hash = hcu_c5_bots_hash_adapter;
c5_ops.emit = hcu_c5_emit_adapter;
memset(&c5_opts, 0, sizeof c5_opts);        /* 0 selects the default batch of 4 */
if (hcu_c5_session_start(&hcu_c5, &setup, rows, rows_count, &c5_ops, &c5_opts) != HCU_C5_SESSION_OK) {
	/* refused: the loaded map is untouched when the reason is a setup refusal */
}
```

Per simulated tick, once, in the same lane as `ps2_bots_update_actions()` (the tick lane; locate with
`grep -n ps2_bots_update_actions`):

```c
hcu_c5_session_tick(&hcu_c5);
```

Hash marker, once per match at teardown or every N ticks (not every tick, the marker is one line):

```c
hcu_c5_session_report(&hcu_c5);
```

Survival deaths: the adapter's kill calls go through the controller that the session owns:

```c
hcu_survival *sv = hcu_c5_session_survival(&hcu_c5);   /* NULL unless survival runs */
if (sv != NULL) {
	hcu_survival_kill_human(sv, human_index);           /* from the human death event */
	hcu_survival_kill_enemy(sv, enemy_slot);            /* from the enemy death event */
}
```

## 4. Gaps the integrator must close before any row can be claimed

1. **The qualified rows are all `qualified=0`.** `src/stream/hcu_local_setup_rows.inc` is generated (by
   `tools/c5_local_setup_rows.py`), has 13 rows, every one `STOCK_COOP` with `difficulty_mask=0`. `hcu_local_setup_admit`
   refuses every map with these rows, so no bot, coop or survival session can start on the guest yet. The `rows` array
   is `static` inside `hcu_local_setup.c`; the integrator needs an exported accessor
   (`const hcu_local_qualified_row *hcu_local_setup_rows(size_t *count)`) to pass it to `hcu_c5_session_start`. Survival
   has no rows at all.
2. **Bot events are not reported to the session yet.** `ps2_bots.c` (CE side) has no call to
   `hcu_c5_session_note_event`. Its `ps2_bots_player_killed` is the death event; nav, fight, respawn and score need
   hooks there or in `hcu_main.c`. Until then the `bot-event` markers (and so the bot guest rows) cannot appear.
3. **`ps2_bots_hash` is not in the session hash by the simulation.** The session folds `ops->bots_hash` in; the
   integrator must call `hcu_c5_session_hash` (not `ps2_bots_hash`) wherever the simulation hash is written.
4. **Coop variant check.** `hcu_coop_ce_bind` admits against the stock rows only. Nothing compares the live CE
   `global_variant` to the binding yet (`hcu_coop_ce_check_live`); call it after the variant is built.
5. **Survival is not wired to CE death events** (section 3 shows the calls, not the CE hooks that make them).

## 5. Things checked and not changed

- `src/stream/hcu_c5_session.c` compiles clean under `cc -std=gnu89 -Wall -Wextra -Werror`.
- `tests/test_hcu_c5_session.py`: 4 passed (coop start and refusals, mapping tables, survival waves and game over,
  events and hash order).
- `hcu_c5_limits.h`, `hcu_bot.h`, `hcu_coop_modes.h`, `hcu_coop_ce_bind.h`, `hcu_local_setup.h` and `hcu_survival.h`
  are unchanged.
- No file in `src/stream/hcu_main.c` or `tools/ee-world.mk` was edited.
