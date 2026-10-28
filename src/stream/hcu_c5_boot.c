/* C5 boot harness for the PS2 guest (new file; no shared source is edited to reach it).
 *
 * The C5 session starts on the first simulated tick after a map loads. The tick is observed through a link-time
 * wrap of ps2_bots_update_actions (tools/c5_build.py wraps it in the closure's per-unit objects, so the calls from
 * the CE tick lane reach __wrap_ps2_bots_update_actions). The wrapper runs the CE call, then this harness:
 *
 *   1. starts a MEASURE coop session with bots on the boot map (the stock coop rows of hcu_local_setup_rows.inc,
 *      plus one measurement coop row for the boot map: qualified=0, MEASURE reports MEASURING, never a qualification),
 *      ticks it, reports the hash;
 *   2. stops the coop roster (ps2_bots_start with NULL arguments clears ps2_bots_running; CE has no stop call), then
 *      starts a MEASURE survival session on the same map (one human, no bots) and, when built with HALO_PS2_SURVIVAL,
 *      the CE survival driver (ps2_survival_start). CE's own tick calls ps2_survival_update (player_queues_new.c), so
 *      this file does not call it. Ticks the session, reports the hash, then stops the CE survival driver;
 *   3. drives the retail actor lifecycle once through the seven stages of tools/c5_retail_actor_lifecycle.py
 *      (placement, attachment, activation, update, combat, death, cleanup), printing one "C5 <stage> ok=1|0 detail=..."
 *      line per stage, then exits.
 *
 * Boot map: the shell loads CE's solo map "levels\b30\b30" (source/main/main.c, the non-headless branch of main_loop),
 * because the C5 build does not define HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST. The boot map is therefore b30.
 *
 * The session prints HALO_PS2_C5 markers itself; the lifecycle prints its own lines (no marker prefix). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stream/hcu_bot.h"
#include "stream/hcu_coop_ce_bind.h"
#include "stream/hcu_c5_session.h"
#include "stream/hcu_local_setup.h"

/* The generated stock-coop rows. Defines hcu_local_generated_rows (static) and HCU_LOCAL_GENERATED_ROW_COUNT. */
#include "stream/hcu_local_setup_rows.inc"

/* Boot map name and CE scenario path, and the actor variant for the lifecycle stages. tools/c5_build.py writes
 * c5_lifecycle_variant.h from --boot-map: HCU_C5_BOOT_MAP, HCU_C5_BOOT_MAP_PATH, the tag PATH and the roster datum
 * (the first eligible combat actv variant of the boot map, or none), never an index. The index is resolved at runtime
 * with tag_loaded('actv', path) on the map that is actually loaded. */
#include "c5_lifecycle_variant.h"
#ifndef HCU_C5_BOOT_COOP_TICKS
#define HCU_C5_BOOT_COOP_TICKS 600u
#endif
#ifndef HCU_C5_BOOT_SURVIVAL_TICKS
#define HCU_C5_BOOT_SURVIVAL_TICKS 600u
#endif
#ifndef HCU_C5_BOOT_BOTS
#define HCU_C5_BOOT_BOTS 3u
#endif
#ifndef NONE
#define NONE (-1)
#endif
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif
struct actor_starting_location;

/* CE entry points, declared locally so this file does not pull the CE headers. Types follow the CE sources:
 * boolean is byte, real is float, NONE is -1 (cseries.h). Each is a rooted CE symbol (tools/c5_build.py). */
extern int ps2_bots_start(hcu_bot_config const *config, struct hcu_coop_ce_binding const *binding);
extern uint64_t ps2_bots_hash(void);
/* The CE tick call, wrapped at link time: __real_ runs the CE function (tools/c5_build.py --wrap). */
extern void __real_ps2_bots_update_actions(void);
extern void ps2_bots_set_event_sink(void (*fn)(void *user, int kind, uint32_t bot, long arg), void *user);
/* The CE survival driver (port/ps2/src/ps2_survival.c). Built into the closure with HALO_PS2_SURVIVAL. */
extern int ps2_survival_start(hcu_survival_config const *config);
extern void ps2_survival_stop(void);
extern long actor_place(long variant, long encounter, long squad, struct actor_starting_location *location,
                        unsigned char upgrade_major, short initial_variant);
extern unsigned char actor_set_active(long actor, unsigned char active);
extern void actors_update(void);
extern void actor_handle_damage(long actor, long aggressor, float damage_fraction, void *damage_velocity);
extern void actor_kill(long actor, unsigned char silent, unsigned char delayed);
extern void actor_delete(long actor, unsigned char died);
/* CE tag lookup by group and tag path (source/cache/cache_files.c). Returns NONE when the loaded map has no such tag. */
extern long tag_loaded(long group_tag, char const *name);
/* 'actv' as CE spells the group (source/ai/actor_definitions.h). */
#define HCU_C5_ACTV_GROUP ((long)'actv')
/* Map request and map-state queries (source/main/main.c, source/cache/cache_files.h, source/game/game.h,
 * source/scenario/scenario.h). CE's own solo-map path: the menu calls main_set_map_name, then
 * main_menu_switch_to_single_player (defer_map_change), and the main loop runs main_change_map_name -> main_new_map. */
extern void main_set_map_name(char const *map_name);
extern void main_menu_switch_to_single_player(void);
extern unsigned char game_map_loaded(void);
extern unsigned char cache_files_precache_map_loaded(char const *map_name);
extern void *cache_files_tag_instances(long *count);
extern struct scenario *global_scenario_try_and_get(void);
/* CE multiplayer variant (source/game/game_engine.c, game.c). The team-slayer builder is the one the coop table names
 * for HCU_COOP_MODE_TEAM_SLAYER (hcu_coop_modes.c); game_set_game_variant installs it as the current variant, so
 * the map load that follows runs a game with that variant. game_in_progress is read before the request so a
 * refused request can be told apart from a map that was never asked for. */
extern struct game_variant *build_game_variant_team_slayer(struct game_variant *variant);
extern void game_set_game_variant(struct game_variant *variant);
extern unsigned char game_in_progress(void);
/* Storage for one struct game_variant. The CE struct is not included here; the buffer is larger than the struct and
 * is aligned for any CE field. The size is an assumption about the CE struct, not checked at build time. */
#define HCU_C5_VARIANT_STORAGE_BYTES 4096u

/* Measurement rows for the boot map. MEASURE needs a row for the map and mode; it does not read the difficulty mask
 * or the population caps. They are measurement rows, not evidence: no qualified row exists for this map. */
#define HCU_C5_BOOT_EXTRA_ROWS 2u
#define HCU_C5_BOOT_ROWS_MAX (HCU_LOCAL_GENERATED_ROW_COUNT + HCU_C5_BOOT_EXTRA_ROWS)

static hcu_local_qualified_row hcu_c5_boot_rows[HCU_C5_BOOT_ROWS_MAX];
static size_t hcu_c5_boot_row_count;

static struct hcu_c5_session hcu_c5_boot_session;
static int hcu_c5_boot_started_once;
static unsigned int hcu_c5_boot_phase;      /* 0 coop, 1 survival, 2 lifecycle, 3 done */
static unsigned int hcu_c5_boot_phase_ticks;
static int hcu_c5_boot_session_failed;
static int hcu_c5_boot_lifecycle_done;

/* The boot map is requested from the first simulated tick, because the shell starts on the UI map. The session
 * starts only after the boot map is mounted (CE map state and tag table), with a bounded wait. */
#define HCU_C5_BOOT_MAP_TICKS 3600u
/* Hash report period (session-hash lines), so the hash can be seen to change tick to tick. */
#define HCU_C5_BOOT_HASH_PERIOD 100u
static int hcu_c5_boot_map_requested;
static int hcu_c5_boot_map_ready;
static unsigned int hcu_c5_boot_map_wait;

static void hcu_c5_boot_emit(void *user, const char *line)
{
	(void)user;
	printf("%s\n", line);
	fflush(stdout);
}

static int hcu_c5_boot_teardown(void *user, const hcu_local_setup_result *accepted)
{
	(void)user;
	(void)accepted;
	/* The map is already loaded by the CE shell. The boot harness does not reload it between sessions. */
	printf("HALO_PS2_C5 teardown skipped (boot harness keeps the loaded map)\n");
	fflush(stdout);
	return 0;
}

static int hcu_c5_boot_bots_start(void *user, const hcu_bot_config *config,
                                  const struct hcu_coop_ce_binding *binding)
{
	(void)user;
	int rc = ps2_bots_start(config, binding);

	printf("C5 bots-start ok=%d detail=ps2_bots_start rc=%d\n", rc == 0 ? 1 : 0, rc);
	fflush(stdout);
	return rc;
}

static uint64_t hcu_c5_boot_bots_hash(void *user)
{
	(void)user;
	return ps2_bots_hash();
}

static void hcu_c5_boot_build_rows(void)
{
	size_t i;

	hcu_c5_boot_row_count = 0;
	for (i = 0; i < HCU_LOCAL_GENERATED_ROW_COUNT; ++i) {
		hcu_c5_boot_rows[hcu_c5_boot_row_count++] = hcu_local_generated_rows[i];
	}
	/* Measurement only: MEASURE checks that a row exists for map and mode, and nothing about its values. */
	hcu_c5_boot_rows[hcu_c5_boot_row_count].map_name = HCU_C5_BOOT_MAP;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].mode = HCU_LOCAL_MODE_STOCK_COOP;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].difficulty_mask = 0x0u;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].max_humans = 0u;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].max_bots = 0u;
	hcu_c5_boot_row_count++;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].map_name = HCU_C5_BOOT_MAP;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].mode = HCU_LOCAL_MODE_SURVIVAL;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].difficulty_mask = 0x0u;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].max_humans = 0u;
	hcu_c5_boot_rows[hcu_c5_boot_row_count].max_bots = 0u;
	hcu_c5_boot_row_count++;
}

static void hcu_c5_boot_setup_for(hcu_local_setup *setup, hcu_local_mode mode)
{
	memset(setup, 0, sizeof *setup);
	setup->mode = mode;
	setup->intent = HCU_LOCAL_INTENT_MEASURE;
	setup->difficulty = HCU_LOCAL_DIFFICULTY_NORMAL;
	setup->human_mask = 0x1u;
	/* Survival admits only the qualification seeds (hcu_survival_validate); seed 1 is not one of them. */
	setup->seed = mode == HCU_LOCAL_MODE_SURVIVAL ? HCU_SURVIVAL_QUAL_SEED_0 : 1u;
	strncpy(setup->map_name, HCU_C5_BOOT_MAP, sizeof setup->map_name - 1u);
	if (mode == HCU_LOCAL_MODE_STOCK_COOP) {
		setup->variant = HCU_LOCAL_VARIANT_SLAYER;
		setup->teams = HCU_LOCAL_TEAMS_ON;
		setup->bot_count = HCU_C5_BOOT_BOTS;
	} else {
		setup->variant = HCU_LOCAL_VARIANT_NONE;
		setup->teams = HCU_LOCAL_TEAMS_OFF;
		setup->bot_count = 0u;
	}
}

static void hcu_c5_boot_session_ops(struct hcu_c5_session_ops *ops)
{
	memset(ops, 0, sizeof *ops);
	ops->teardown = hcu_c5_boot_teardown;
	ops->bots_start = hcu_c5_boot_bots_start;
	ops->bots_hash = hcu_c5_boot_bots_hash;
	ops->emit = hcu_c5_boot_emit;
}

/* Starts one MEASURE session of the given mode. Returns the session status (OK on success). */
static enum hcu_c5_session_status hcu_c5_boot_start(hcu_local_mode mode)
{
	hcu_local_setup setup;
	struct hcu_c5_session_ops ops;
	struct hcu_c5_session_options options;
	enum hcu_c5_session_status status;

	hcu_c5_boot_setup_for(&setup, mode);
	hcu_c5_boot_session_ops(&ops);
	memset(&options, 0, sizeof options);
	status = hcu_c5_session_start(&hcu_c5_boot_session, &setup, hcu_c5_boot_rows, hcu_c5_boot_row_count,
		&ops, &options);
	printf("HALO_PS2_C5 boot mode=%s map=%s status=%s setup_reason=%d\n",
		mode == HCU_LOCAL_MODE_SURVIVAL ? "survival" : "coop", HCU_C5_BOOT_MAP,
		hcu_c5_session_status_name(status), (int)hcu_c5_boot_session.setup_reason);
	fflush(stdout);
	if (status == HCU_C5_SESSION_OK) {
		if (mode == HCU_LOCAL_MODE_STOCK_COOP) {
			ps2_bots_set_event_sink(hcu_c5_session_bot_sink, &hcu_c5_boot_session);
		}
	}
	return status;
}

/* Stops the coop roster before survival. CE has no bot stop call; ps2_bots_start clears ps2_bots_running first and
 * then refuses a NULL config, so this call leaves no roster running and its tick does nothing. */
static void hcu_c5_boot_stop_roster(void)
{
	(void)ps2_bots_start(NULL, NULL);
	printf("C5 roster-stop ok=1 detail=ps2_bots_running cleared (NULL start)\n");
	fflush(stdout);
}

static void hcu_c5_boot_survival_driver_start(void)
{
#ifdef HALO_PS2_SURVIVAL
	hcu_survival_config cfg;
	hcu_survival_difficulty difficulty;
	int rc;

	if (hcu_c5_session_survival_difficulty(HCU_LOCAL_DIFFICULTY_NORMAL, &difficulty) != 0) {
		rc = -100;
	} else {
		memset(&cfg, 0, sizeof cfg);
		cfg.difficulty = difficulty;
		cfg.seed = HCU_SURVIVAL_QUAL_SEED_0;
		cfg.humans = 1u;
		cfg.active_limit = 4u;
		rc = ps2_survival_start(&cfg);
	}
	printf("C5 survival-driver ok=%d detail=ps2_survival_start rc=%d\n", rc == 0 ? 1 : 0, rc);
	fflush(stdout);
#endif
}

static void hcu_c5_boot_survival_driver_stop(void)
{
#ifdef HALO_PS2_SURVIVAL
	ps2_survival_stop();
	printf("C5 survival-driver-stop ok=1 detail=ps2_survival_stop returned\n");
	fflush(stdout);
#endif
}

static void hcu_c5_boot_lifecycle_stage(const char *stage, int ok, const char *detail)
{
	printf("C5 %s ok=%d detail=%s\n", stage, ok ? 1 : 0, detail);
	fflush(stdout);
}

/* Drives the retail actor lifecycle once, on the loaded map, through the seven stages of
 * tools/c5_retail_actor_lifecycle.py. Attachment runs inside actor_place (actors.c) and has no separate CE call, so
 * it is reported as skipped rather than as a pass. Update, combat, death and cleanup report that their CE call
 * returned; no observable state is checked for them. */
static void hcu_c5_boot_lifecycle(void)
{
	static unsigned char location_storage[256];
	long variant;
	long actor;
	unsigned char active;

	if (hcu_c5_boot_lifecycle_done) {
		return;
	}
	hcu_c5_boot_lifecycle_done = 1;
	/* Runtime resolution on the map that is loaded now. A map without the roster tag (for example the UI map) is a
	 * stage failure, reported with ok=0, never an assert inside actor_place. */
	variant = tag_loaded(HCU_C5_ACTV_GROUP, HCU_C5_LIFECYCLE_VARIANT_PATH);
	if (variant == NONE) {
		printf("C5 variant-resolve ok=0 detail=tag_loaded(actv) returned NONE for %s on map %s\n",
			HCU_C5_LIFECYCLE_VARIANT_PATH, HCU_C5_BOOT_MAP);
		hcu_c5_boot_lifecycle_stage("placement", 0, "variant-not-loaded");
		printf("C5 attachment skipped detail=runs inside actor_place (no separate CE call)\n");
		hcu_c5_boot_lifecycle_stage("activation", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("update", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("combat", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("death", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("cleanup", 0, "no actor");
		return;
	}
	printf("C5 variant-resolve ok=1 detail=tag_loaded(actv) index=%ld for %s\n", variant,
		HCU_C5_LIFECYCLE_VARIANT_PATH);
	fflush(stdout);
	memset(location_storage, 0, sizeof location_storage);
	actor = actor_place(variant, NONE, NONE, (struct actor_starting_location *)location_storage, FALSE, NONE);
	hcu_c5_boot_lifecycle_stage("placement", actor != NONE, actor != NONE ? "actor placed" : "actor_place returned NONE");
	printf("C5 attachment skipped detail=runs inside actor_place (no separate CE call)\n");
	fflush(stdout);
	if (actor == NONE) {
		hcu_c5_boot_lifecycle_stage("activation", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("update", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("combat", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("death", 0, "no actor");
		hcu_c5_boot_lifecycle_stage("cleanup", 0, "no actor");
		return;
	}
	active = actor_set_active(actor, TRUE);
	hcu_c5_boot_lifecycle_stage("activation", active != 0, active ? "active" : "not active");
	actors_update();
	hcu_c5_boot_lifecycle_stage("update", 1, "actors_update returned (no state check)");
	actor_handle_damage(actor, NONE, 0.5f, NULL);
	hcu_c5_boot_lifecycle_stage("combat", 1, "actor_handle_damage returned (no state check)");
	actor_kill(actor, TRUE, FALSE);
	hcu_c5_boot_lifecycle_stage("death", 1, "actor_kill returned (no state check)");
	actor_delete(actor, TRUE);
	hcu_c5_boot_lifecycle_stage("cleanup", 1, "actor_delete returned (no state check)");
}

/* Replaces the path separators for the log: the PS2 printf path drops backslashes in %s (measured in the r7 log). */
static void hcu_c5_boot_print_name(const char *label, const char *name)
{
	char plain[128];
	size_t i;

	for (i = 0; i + 1 < sizeof plain && name[i]; ++i) {
		plain[i] = name[i] == '\\' ? '/' : name[i];
	}
	plain[i] = 0;
	printf("%s%s\n", label, plain);
	fflush(stdout);
}

static int hcu_c5_boot_map_mounted(long *tag_count)
{
	void *tags;

	*tag_count = 0;
	if (!game_map_loaded() || !cache_files_precache_map_loaded(HCU_C5_BOOT_MAP_PATH)) {
		return 0;
	}
	if (!global_scenario_try_and_get()) {
		return 0;
	}
	tags = cache_files_tag_instances(tag_count);
	return tags != NULL && *tag_count > 0;
}

/* Counts the C1 roster paths the mounted map resolves: actv (the actor variants) and bipd (their units). */
static void hcu_c5_boot_report_map_tags(long tag_count)
{
	unsigned int i;
	unsigned int actv_resolved = 0;
	unsigned int unit_resolved = 0;

	for (i = 0; i < HCU_C5_BOOT_ACTV_COUNT; ++i) {
		if (tag_loaded(HCU_C5_ACTV_GROUP, hcu_c5_boot_actv_paths[i]) != NONE) {
			actv_resolved++;
		}
	}
	for (i = 0; i < HCU_C5_BOOT_UNIT_COUNT; ++i) {
		if (tag_loaded((long)'bipd', hcu_c5_boot_unit_paths[i]) != NONE) {
			unit_resolved++;
		}
	}
	printf("C5 map-tags tag-count=%ld actv-resolved=%u of=%u bipd-resolved=%u of=%u\n", tag_count,
		actv_resolved, (unsigned int)HCU_C5_BOOT_ACTV_COUNT, unit_resolved, (unsigned int)HCU_C5_BOOT_UNIT_COUNT);
	fflush(stdout);
}

static void hcu_c5_boot_map_fail(void)
{
	hcu_c5_boot_lifecycle_stage("placement", 0, "boot-map-not-loaded");
	hcu_c5_boot_lifecycle_stage("activation", 0, "no actor");
	hcu_c5_boot_lifecycle_stage("update", 0, "no actor");
	hcu_c5_boot_lifecycle_stage("combat", 0, "no actor");
	hcu_c5_boot_lifecycle_stage("death", 0, "no actor");
	hcu_c5_boot_lifecycle_stage("cleanup", 0, "no actor");
	printf("HALO_PS2_C5 boot done\n");
	fflush(stdout);
	exit(0);
}

/* Installs the CE team-slayer variant for a multiplayer boot map (sidewinder), before the map request, so the map load
 * that CE runs next carries the variant. Solo boot maps (b30) keep CE's own variant and are not touched. */
static void hcu_c5_boot_variant_install(void)
{
	static union {
		unsigned char bytes[HCU_C5_VARIANT_STORAGE_BYTES];
		long double align;
	} variant_storage;

	if (strcmp(HCU_C5_BOOT_MAP, "sidewinder") != 0) {
		return;
	}
	memset(&variant_storage, 0, sizeof variant_storage);
	build_game_variant_team_slayer((struct game_variant *)variant_storage.bytes);
	game_set_game_variant((struct game_variant *)variant_storage.bytes);
	printf("C5 variant-install ok=1 detail=build_game_variant_team_slayer + game_set_game_variant map=%s\n",
		HCU_C5_BOOT_MAP);
	fflush(stdout);
}

/* Returns 1 once the boot map is mounted. Requests it on the first call; the main loop acts on the request. */
static int hcu_c5_boot_await_map(void)
{
	long tag_count;

	if (hcu_c5_boot_map_ready) {
		return 1;
	}
	if (!hcu_c5_boot_map_requested) {
		hcu_c5_boot_map_requested = 1;
		printf("C5 game-state in_progress=%d before-request\n", (int)game_in_progress());
		fflush(stdout);
		hcu_c5_boot_variant_install();
		main_set_map_name(HCU_C5_BOOT_MAP_PATH);
		main_menu_switch_to_single_player();
		printf("C5 game-state in_progress=%d after-request\n", (int)game_in_progress());
		fflush(stdout);
		hcu_c5_boot_print_name("C5 map-request ok=1 detail=main_set_map_name+defer_map_change map=",
			HCU_C5_BOOT_MAP_PATH);
		return 0;
	}
	if (hcu_c5_boot_map_mounted(&tag_count)) {
		hcu_c5_boot_map_ready = 1;
		hcu_c5_boot_print_name("HALO_PS2_C5 map-loaded name=", HCU_C5_BOOT_MAP_PATH);
		printf("HALO_PS2_C5 map-loaded tags=%ld ticks=%u scenario=%s\n", tag_count, hcu_c5_boot_map_wait,
			HCU_C5_BOOT_SCENARIO_PATH[0] ? "set" : "none");
		fflush(stdout);
		hcu_c5_boot_report_map_tags(tag_count);
		return 1;
	}
	if (++hcu_c5_boot_map_wait >= HCU_C5_BOOT_MAP_TICKS) {
		printf("C5 map-load ok=0 detail=boot map not mounted after %u ticks\n", hcu_c5_boot_map_wait);
		fflush(stdout);
		hcu_c5_boot_map_fail();
	}
	return 0;
}

/* One simulated tick of the boot schedule. Called after ps2_bots_update_actions has run. */
static void hcu_c5_boot_tick(void)
{
	enum hcu_c5_session_status status;

	if (!hcu_c5_boot_await_map()) {
		return;
	}
	if (!hcu_c5_boot_started_once) {
		hcu_c5_boot_started_once = 1;
		hcu_c5_boot_build_rows();
		status = hcu_c5_boot_start(HCU_LOCAL_MODE_STOCK_COOP);
		if (status != HCU_C5_SESSION_OK) {
			hcu_c5_boot_session_failed = 1;
		}
		hcu_c5_boot_phase = 0;
		hcu_c5_boot_phase_ticks = 0;
	}
	if (hcu_c5_boot_phase == 0) {
		if (!hcu_c5_boot_session_failed) {
			hcu_c5_session_tick(&hcu_c5_boot_session);
			if (hcu_c5_boot_phase_ticks % HCU_C5_BOOT_HASH_PERIOD == 0u) {
				hcu_c5_session_report(&hcu_c5_boot_session);
			}
		}
		if (++hcu_c5_boot_phase_ticks >= HCU_C5_BOOT_COOP_TICKS || hcu_c5_boot_session_failed) {
			hcu_c5_session_report(&hcu_c5_boot_session);
			hcu_c5_boot_phase = 1;
			hcu_c5_boot_phase_ticks = 0;
			hcu_c5_boot_session_failed = 0;
			hcu_c5_boot_stop_roster();
			status = hcu_c5_boot_start(HCU_LOCAL_MODE_SURVIVAL);
			if (status != HCU_C5_SESSION_OK) {
				hcu_c5_boot_session_failed = 1;
			} else {
				hcu_c5_boot_survival_driver_start();
			}
		}
		return;
	}
	if (hcu_c5_boot_phase == 1) {
		if (!hcu_c5_boot_session_failed) {
			hcu_c5_session_tick(&hcu_c5_boot_session);
			if (hcu_c5_boot_phase_ticks % HCU_C5_BOOT_HASH_PERIOD == 0u) {
				hcu_c5_session_report(&hcu_c5_boot_session);
			}
		}
		if (++hcu_c5_boot_phase_ticks >= HCU_C5_BOOT_SURVIVAL_TICKS || hcu_c5_boot_session_failed) {
			hcu_c5_session_report(&hcu_c5_boot_session);
			hcu_c5_boot_survival_driver_stop();
			hcu_c5_boot_phase = 2;
		}
		return;
	}
	if (hcu_c5_boot_phase == 2) {
		hcu_c5_boot_lifecycle();
		printf("HALO_PS2_C5 boot done\n");
		fflush(stdout);
		hcu_c5_boot_phase = 3;
		exit(0);
	}
}

/* Link-time wrap (tools/c5_build.py): every CE call to ps2_bots_update_actions lands here. */
void __wrap_ps2_bots_update_actions(void)
{
	__real_ps2_bots_update_actions();
	hcu_c5_boot_tick();
}
