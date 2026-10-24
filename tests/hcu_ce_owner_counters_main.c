/* Host check for the always-on PS2 owner counters (C2.6). The producer
   source is included directly; the cache and memory getters it reads are
   stubbed here, so the test needs no game data. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "halo_ps2_owner_counters.h"
#include "../submodules/halo-ce-universal/port/ps2/src/ps2_owner_counters.c"

static int failures;

#define CHECK(condition) \
	do { \
		if (!(condition)) { \
			printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); \
			failures++; \
		} \
	} while (0)

static halo_ps2_cache_owner_telemetry stub_telemetry;
static unsigned long stub_tag_capacity = 4685920u;
static unsigned long stub_bsp_capacity = 1993744u;

void ps2_cache_get_owner_telemetry(halo_ps2_cache_owner_telemetry *out)
{
	*out = stub_telemetry;
}

unsigned long physical_memory_get_tag_cache_size(void)
{
	return stub_tag_capacity;
}

unsigned long physical_memory_get_structure_bsp_cache_size(void)
{
	return stub_bsp_capacity;
}

static void check_unbound_and_bad_args(void)
{
	halo_ps2_owner_counters c;

	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_OBJECT_POOL, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_AUDIO_REQUESTS, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(-1, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_COUNT, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_TAGS, NULL) == -1);
}

static void check_game_state(void)
{
	halo_ps2_owner_counters c;

	halo_ps2_owner_counters_note_game_state(1000u, 100u);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c) == 0);
	CHECK(c.capacity == 1000u && c.used == 100u && c.high_water == 100u);
	CHECK(c.failures == 0 && c.resets == 0);

	halo_ps2_owner_counters_note_game_state(1000u, 40u);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c);
	CHECK(c.used == 40u && c.high_water == 100u);

	halo_ps2_owner_counters_note_game_state_failure();
	halo_ps2_owner_counters_note_game_state_reset();
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c);
	CHECK(c.failures == 1 && c.resets == 1);
	CHECK(c.high_water == 100u);
}

static void check_object_pool(void)
{
	halo_ps2_owner_counters c;

	/* the object pool is fed only by its memory pool: the datum array is not a
	   source, and a bad owner is refused without touching game state */
	CHECK(halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_OBJECT_POOL, &c, 8u, 4u) == -1);
	CHECK(halo_ps2_owner_counters_note_pool(HALO_PS2_OWNER_GAME_STATE, 1u, 1u, 1u, 1u, 1u, 1u) == -1);
	CHECK(halo_ps2_owner_counters_note_pool(HALO_PS2_OWNER_ACTOR_POOL, 1u, 1u, 1u, 1u, 1u, 1u) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c) == -1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_OBJECT_POOL, &c) == -1);

	/* the pool's own counters (memory_pool.c) are copied as they are */
	CHECK(halo_ps2_owner_counters_note_pool(HALO_PS2_OWNER_OBJECT_POOL, 1000000u, 400u, 800u, 3u, 2u, 2u) == 0);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_OBJECT_POOL, &c) == 0);
	CHECK(c.capacity == 1000000u && c.used == 400u && c.high_water == 800u);
	CHECK(c.failures == 5u && c.resets == 2u);

	/* a later value replaces the used bytes and keeps the pool's high water */
	CHECK(halo_ps2_owner_counters_note_pool(HALO_PS2_OWNER_OBJECT_POOL, 1000000u, 0u, 800u, 3u, 2u, 2u) == 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_OBJECT_POOL, &c);
	CHECK(c.used == 0u && c.high_water == 800u && c.failures == 5u);

	/* nested in game state: game state keeps the value it had */
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c);
	CHECK(c.used == 40u && c.high_water == 100u);

	/* values past UINT32_MAX saturate */
	CHECK(halo_ps2_owner_counters_note_pool(HALO_PS2_OWNER_OBJECT_POOL, ~0UL, ~0UL, ~0UL, ~0UL, ~0UL, ~0UL) == 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_OBJECT_POOL, &c);
	CHECK(c.capacity == UINT32_MAX && c.used == UINT32_MAX && c.high_water == UINT32_MAX);
	CHECK(c.failures == UINT32_MAX && c.resets == UINT32_MAX);
}

static void check_widget_pool(void)
{
	halo_ps2_owner_counters c;

	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_WIDGET_POOL, &c) == -1);
	halo_ps2_owner_counters_note_widget_pool(262144u, 1200u, 4096u);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_WIDGET_POOL, &c) == 0);
	CHECK(c.capacity == 262144u && c.used == 1200u && c.high_water == 4096u);
	CHECK(c.failures == 0u && c.resets == 0u);
	halo_ps2_owner_counters_note_widget_pool_failure();
	halo_ps2_owner_counters_note_widget_pool_failure();
	halo_ps2_owner_counters_note_widget_pool(262144u, 900u, 4096u);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_WIDGET_POOL, &c);
	CHECK(c.capacity == 262144u && c.used == 900u && c.high_water == 4096u);
	CHECK(c.failures == 2u && c.resets == 0u);
	halo_ps2_owner_counters_note_widget_pool_reset();
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_WIDGET_POOL, &c);
	CHECK(c.resets == 1u && c.high_water == c.used);
}

static void check_datum_pools(void)
{
	halo_ps2_owner_counters c;
	int actor_array = 0;
	int other_array = 0;

	/* an array nobody bound, and a bad owner, change nothing */
	halo_ps2_owner_counters_datum_changed(&other_array, 9u, 1, 1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c) == -1);
	CHECK(halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_GAME_STATE, &actor_array, 8u, 4u) == -1);
	CHECK(halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_ACTOR_POOL, NULL, 8u, 4u) == -1);

	CHECK(halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_ACTOR_POOL, &actor_array, 8u, 4u) == 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.capacity == 32u && c.used == 0u && c.high_water == 0u);

	halo_ps2_owner_counters_datum_changed(&actor_array, 3u, 0, 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.used == 24u && c.high_water == 24u);

	halo_ps2_owner_counters_datum_changed(&actor_array, 4u, 1, 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.used == 32u && c.high_water == 32u && c.failures == 1u);

	halo_ps2_owner_counters_datum_changed(&actor_array, 1u, 0, 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.used == 8u && c.high_water == 32u);

	halo_ps2_owner_counters_datum_changed(&actor_array, 0u, 0, 1);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.resets == 1u && c.used == 0u && c.high_water == 32u);

	CHECK(halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_ACTOR_POOL, &actor_array, 16u, 2u) == 0);
	halo_ps2_owner_counters_datum_changed(&actor_array, 2u, 0, 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.capacity == 32u && c.used == 32u && c.high_water == 32u);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_GAME_STATE, &c);
	CHECK(c.used == 40u && c.high_water == 100u);
}

static void check_cache_pull(void)
{
	halo_ps2_owner_counters c;

	memset(&stub_telemetry, 0, sizeof(stub_telemetry));
	stub_telemetry.tag_current_bytes = 1234u;
	stub_telemetry.tag_peak_bytes = 5678u;
	stub_telemetry.tag_failures = 2u;
	stub_telemetry.tag_resets = 3u;
	stub_telemetry.bsp_current_bytes = 99u;
	stub_telemetry.bsp_peak_bytes = 400u;
	stub_telemetry.bsp_failures = 4u;
	stub_telemetry.bsp_resets = 5u;

	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_TAGS, &c) == 0);
	CHECK(c.capacity == 4685920u && c.used == 1234u && c.high_water == 5678u);
	CHECK(c.failures == 2u && c.resets == 3u);

	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_BSP, &c) == 0);
	CHECK(c.capacity == 1993744u && c.used == 99u && c.high_water == 400u);
	CHECK(c.failures == 4u && c.resets == 5u);
}

static void check_audio_requests(void)
{
	halo_ps2_owner_counters c;

	/* unbound until the sound cache is created */
	halo_ps2_owner_counters_note_audio_request(1);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_AUDIO_REQUESTS, &c) == -1);

	halo_ps2_owner_counters_bind_audio_requests();
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_AUDIO_REQUESTS, &c) == 0);
	CHECK(c.capacity == 0u && c.used == 0u && c.high_water == 0u);
	CHECK(c.submitted == 0u && c.failures == 0u && c.resets == 0u);

	halo_ps2_owner_counters_note_audio_request(1);
	halo_ps2_owner_counters_note_audio_request(1);
	halo_ps2_owner_counters_note_audio_request(1);
	halo_ps2_owner_counters_note_audio_request(0);
	halo_ps2_owner_counters_note_audio_request(0);
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_AUDIO_REQUESTS, &c) == 0);
	CHECK(c.submitted == 5u && c.failures == 2u && c.high_water == 0u);

	halo_ps2_owner_counters_note_audio_reset();
	CHECK(halo_ps2_owner_counters_get(HALO_PS2_OWNER_AUDIO_REQUESTS, &c) == 0);
	CHECK(c.submitted == 5u && c.failures == 2u && c.resets == 1u);
}

static void check_saturation(void)
{
	halo_ps2_owner_counters c;
	int array = 0;

	halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_ACTOR_POOL, &array, 1u, 4u);
	owner_counters[HALO_PS2_OWNER_ACTOR_POOL].failures = UINT32_MAX - 1u;
	halo_ps2_owner_counters_datum_changed(&array, 0u, 1, 0);
	halo_ps2_owner_counters_datum_changed(&array, 0u, 1, 0);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.failures == UINT32_MAX);

	/* a product that does not fit saturates instead of wrapping */
	halo_ps2_owner_counters_bind_datum(HALO_PS2_OWNER_ACTOR_POOL, &array, UINT32_MAX, 2u);
	halo_ps2_owner_counters_get(HALO_PS2_OWNER_ACTOR_POOL, &c);
	CHECK(c.capacity == UINT32_MAX);
}

int main(void)
{
	check_unbound_and_bad_args();
	check_game_state();
	check_object_pool();
	check_datum_pools();
	check_cache_pull();
	check_audio_requests();
	check_saturation();
	check_widget_pool();

	if (failures)
	{
		printf("hcu_ce_owner_counters: %d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_ce_owner_counters: pass\n");
	return 0;
}
