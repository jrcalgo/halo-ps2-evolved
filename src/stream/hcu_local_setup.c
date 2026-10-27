/* Local setup validator for the HCU C5 bot and cooperative profiles.
 *
 * Every check runs before the caller tears anything down. Nothing here
 * allocates, keeps static state, or writes outside `out` on acceptance.
 */
#include "stream/hcu_local_setup.h"

#include <ctype.h>
#include <string.h>

static int name_is_valid(const char *name)
{
	size_t i;
	if (!name || name[0] == '\0') {
		return 0;
	}
	for (i = 0; i < HCU_LOCAL_MAP_NAME_BYTES; ++i) {
		if (name[i] == '\0') {
			return 1;
		}
		if (!isprint((unsigned char)name[i])) {
			return 0;
		}
	}
	/* No terminator inside the fixed buffer: refuse. */
	return 0;
}

static int names_equal_nocase(const char *a, const char *b)
{
	for (;;) {
		unsigned char ca = (unsigned char)*a++;
		unsigned char cb = (unsigned char)*b++;
		if (tolower(ca) != tolower(cb)) {
			return 0;
		}
		if (ca == '\0') {
			return 1;
		}
	}
}

static uint32_t popcount4(uint32_t mask)
{
	uint32_t n = 0;
	for (; mask; mask &= mask - 1u) {
		++n;
	}
	return n;
}

static int mode_known(hcu_local_mode mode)
{
	return mode == HCU_LOCAL_MODE_STOCK_COOP || mode == HCU_LOCAL_MODE_SURVIVAL;
}

static int variant_known(hcu_local_variant variant)
{
	return variant >= HCU_LOCAL_VARIANT_SLAYER && variant <= HCU_LOCAL_VARIANT_RACE;
}

static int difficulty_known(hcu_local_difficulty difficulty)
{
	return difficulty >= HCU_LOCAL_DIFFICULTY_EASY && difficulty <= HCU_LOCAL_DIFFICULTY_LEGENDARY;
}

hcu_local_setup_reason hcu_local_setup_validate(const hcu_local_setup *request,
	const hcu_local_qualified_row *rows, size_t row_count,
	hcu_local_setup_result *out)
{
	const hcu_local_qualified_row *row = NULL;
	size_t i;
	uint32_t humans;

	if (!request || !out || (!rows && row_count != 0u)) {
		return HCU_LOCAL_SETUP_BAD_ARGUMENT;
	}
	if (!mode_known(request->mode)) {
		return HCU_LOCAL_SETUP_UNKNOWN_MODE;
	}
	if (request->mode == HCU_LOCAL_MODE_SURVIVAL) {
		if (request->variant != HCU_LOCAL_VARIANT_NONE) {
			return HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE;
		}
	} else {
		if (request->variant == HCU_LOCAL_VARIANT_NONE) {
			return HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE;
		}
		if (!variant_known(request->variant)) {
			return HCU_LOCAL_SETUP_UNKNOWN_VARIANT;
		}
	}
	if (!difficulty_known(request->difficulty)) {
		return HCU_LOCAL_SETUP_UNKNOWN_DIFFICULTY;
	}
	if (!name_is_valid(request->map_name)) {
		return HCU_LOCAL_SETUP_BAD_MAP_NAME;
	}
	if (request->human_mask == 0u) {
		return HCU_LOCAL_SETUP_NO_HUMANS;
	}
	if (request->human_mask & ~((1u << HCU_LOCAL_HUMAN_SLOTS) - 1u)) {
		return HCU_LOCAL_SETUP_BAD_HUMAN_MASK;
	}
	if (request->bot_count > HCU_LOCAL_BOT_SLOTS) {
		return HCU_LOCAL_SETUP_TOO_MANY_BOTS;
	}

	for (i = 0; i < row_count; ++i) {
		if (rows[i].map_name && names_equal_nocase(rows[i].map_name, request->map_name) &&
			rows[i].mode == request->mode) {
			row = &rows[i];
			break;
		}
	}
	if (!row) {
		return HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED;
	}
	if (!(row->difficulty_mask & (1u << (unsigned)request->difficulty))) {
		return HCU_LOCAL_SETUP_DIFFICULTY_NOT_QUALIFIED;
	}
	humans = popcount4(request->human_mask);
	if (humans > row->max_humans || request->bot_count > row->max_bots) {
		return HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED;
	}

	memset(out, 0, sizeof *out);
	out->setup = *request;
	out->human_count = humans;
	out->bot_count = request->bot_count;
	out->qualified_population = row->max_humans + row->max_bots;
	return HCU_LOCAL_SETUP_OK;
}

hcu_local_setup_reason hcu_local_setup_admit(const hcu_local_setup *request,
	const hcu_local_qualified_row *rows, size_t row_count,
	hcu_local_teardown_fn teardown, void *user, hcu_local_setup_result *out)
{
	hcu_local_setup_reason reason = hcu_local_setup_validate(request, rows, row_count, out);
	if (reason != HCU_LOCAL_SETUP_OK) {
		return reason;
	}
	if (teardown && teardown(user, out) != 0) {
		return HCU_LOCAL_SETUP_TEARDOWN_FAILED;
	}
	return HCU_LOCAL_SETUP_OK;
}

const char *hcu_local_setup_reason_name(hcu_local_setup_reason reason)
{
	switch (reason) {
	case HCU_LOCAL_SETUP_OK: return "ok";
	case HCU_LOCAL_SETUP_BAD_ARGUMENT: return "bad-argument";
	case HCU_LOCAL_SETUP_UNKNOWN_MODE: return "unknown-mode";
	case HCU_LOCAL_SETUP_UNKNOWN_VARIANT: return "unknown-variant";
	case HCU_LOCAL_SETUP_UNKNOWN_DIFFICULTY: return "unknown-difficulty";
	case HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE: return "variant-not-applicable";
	case HCU_LOCAL_SETUP_BAD_MAP_NAME: return "bad-map-name";
	case HCU_LOCAL_SETUP_NO_HUMANS: return "no-humans";
	case HCU_LOCAL_SETUP_BAD_HUMAN_MASK: return "bad-human-mask";
	case HCU_LOCAL_SETUP_TOO_MANY_BOTS: return "too-many-bots";
	case HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED: return "map-not-qualified";
	case HCU_LOCAL_SETUP_DIFFICULTY_NOT_QUALIFIED: return "difficulty-not-qualified";
	case HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED: return "population-above-qualified";
	case HCU_LOCAL_SETUP_TEARDOWN_FAILED: return "teardown-failed";
	}
	return "unknown";
}
