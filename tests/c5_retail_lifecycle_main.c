/* C5 retail lifecycle harness: drives the real CE actor code for one C1 recipe on the host.
 *
 * Usage: c5_retail_lifecycle_main <variant datum index>
 *
 * The recipe's actor variant goes into actor_place (ai/actors.c), the function the encounter
 * placement (ai/encounters.c encounter_place_actor, the actor_place call) reaches for a squad's
 * actor palette entry. Stages run in order; a stage that cannot run prints its "begin" line and
 * the stub it reaches exits 3, so the producer reads the last open stage as blocked. Output is
 * line-oriented, one "C5 ..." record per event; the producer parses nothing else. */
#include "cseries/cseries.h"
#include "ai/actors.h"
#include "ai/actor_placement.h"
#include "ai/ai_scenario_definitions.h"
#include "memory/data.h"
#include "objects/objects.h"
#include "saved games/game_state.h"
#include "stream/hcu_actor_metrics.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

long c5_map_load(const char *path);

/* The actor pool, laid out as game_state_data_new lays it out (header, then elements). */
static unsigned long c5_pool_storage[(sizeof(struct data_array) + MAXIMUM_ACTORS * sizeof(struct actor_datum)) / sizeof(unsigned long) + 2];

static void begin(const char *stage)
{
	printf("C5 begin stage=%s\n", stage);
	fflush(stdout);
}

static void check(const char *stage, int ok, const char *what)
{
	printf("C5 check stage=%s ok=%d detail=%s\n", stage, ok ? 1 : 0, what);
	fflush(stdout);
}

static void end(const char *stage, long result)
{
	printf("C5 end stage=%s result=%ld\n", stage, result);
	fflush(stdout);
}

int main(int argc, char **argv)
{
	long variant;
	long placed;
	struct actor_starting_location location;
	hcu_actor_metrics metrics;

	if (argc != 3)
	{
		fprintf(stderr, "usage: c5_retail_lifecycle_main <variant datum index> <decompressed map>\n");
		return 2;
	}
	variant = strtol(argv[1], NULL, 10);
	if (c5_map_load(argv[2]) < 0)
	{
		return 2;
	}
	hcu_actor_metrics_reset(&metrics);

	data_initialize((struct data_array *)c5_pool_storage, "actor", MAXIMUM_ACTORS, sizeof(struct actor_datum));
	actor_data = (struct data_array *)c5_pool_storage;
	data_make_valid(actor_data);
	memset(&location, 0, sizeof location);

	begin("setup");
	game_state_initialize();
	objects_initialize();
	end("setup", 0);

	begin("placement");
	placed = actor_place(variant, NONE, NONE, &location, FALSE, NONE);
	end("placement", placed);
	/* observable state: a placed actor is a live datum of the pool, and the pool counts it */
	check("placement", placed != NONE && actor_data->actual_count == 1,
		"placed actor is a live datum and the actor pool counts one");
	if (placed == NONE)
	{
		hcu_actor_metrics_retail_failure(&metrics);
	}
	else
	{
		hcu_actor_metrics_sample_retail(&metrics, (uint32_t)actor_data->actual_count);
		begin("death");
		actor_kill((long)placed, TRUE, FALSE);
		end("death", placed);
		begin("cleanup");
		actor_delete((long)placed, TRUE);
		end("cleanup", placed);
		check("cleanup", actor_data->actual_count == 0, "the actor pool is empty after actor_delete");
		hcu_actor_metrics_sample_retail(&metrics, (uint32_t)actor_data->actual_count);
	}
	printf("C5 metrics retail_samples=%u retail_peak=%u retail_failures=%u bot_samples=%u\n",
		(unsigned)metrics.retail_actors.samples, (unsigned)metrics.retail_actors.peak,
		(unsigned)metrics.retail_actors.failures, (unsigned)metrics.spartan_bots.samples);
	return 0;
}
