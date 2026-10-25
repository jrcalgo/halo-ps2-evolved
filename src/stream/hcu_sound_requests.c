#include "stream/hcu_sound_requests.h"

#include <float.h>
#include <stdio.h>
#include <string.h>

static int float_finite(float value)
{
	return value == value && value <= FLT_MAX && value >= -FLT_MAX;
}

static int request_valid(const hcu_sound_request *request)
{
	if (request->event == HCU_SOUND_EVENT_NONE ||
		request->event > HCU_SOUND_EVENT_STOP)
		return 0;
	if (request->owner_kind > HCU_SOUND_OWNER_CE_SOURCE)
		return 0;
	if (request->metadata_known & ~0x3fu)
		return 0;
	if (request->flags & ~0x7u)
		return 0;
	if (request->has_position > 1u || request->accepted > 1u)
		return 0;
	if ((request->metadata_known & 0x08u) &&
		(!float_finite(request->gain) || !(request->gain >= 0.0f)))
		return 0;
	if ((request->metadata_known & 0x10u) &&
		(!float_finite(request->pitch) || !(request->pitch > 0.0f)))
		return 0;
	if (request->has_position && !(request->metadata_known & 0x02u))
		return 0;
	if ((request->metadata_known & 0x02u) && request->has_position) {
		size_t i;
		for (i = 0; i < 3; ++i)
			if (!float_finite(request->position[i]))
				return 0;
	}
	return 1;
}

/* Always fills *out, so a caller that submits the record never sends stale
 * stack bytes. An invalid capture is marked with event NONE, which the queue
 * refuses and counts as rejected. An unknown owner clears the owner metadata
 * bit so owner coverage never counts it. */
int hcu_sound_request_capture_playback(hcu_sound_request *out,
	uint16_t event, uint32_t permutation, uint32_t sound_index,
	uint16_t owner_kind, uint32_t owner_datum, int has_position,
	const float position[3], uint8_t priority, float gain, float pitch,
	uint32_t game_time, uint8_t metadata_known)
{
	if (!out) return 0;
	memset(out, 0, sizeof(*out));
	out->event = event;
	out->permutation = permutation;
	out->sound_index = sound_index;
	out->owner_kind = owner_kind;
	out->owner_datum = owner_datum;
	out->has_position = has_position ? 1u : 0u;
	if (position) {
		out->position[0] = position[0];
		out->position[1] = position[1];
		out->position[2] = position[2];
	}
	out->priority = priority;
	out->accepted = 1u; /* CE dispatched this event to the recorder bridge. */
	out->gain = gain;
	out->pitch = pitch;
	out->game_time = game_time;
	out->metadata_known = metadata_known;
	if (owner_kind == HCU_SOUND_OWNER_NONE || owner_kind > HCU_SOUND_OWNER_CE_SOURCE) {
		out->owner_kind = HCU_SOUND_OWNER_NONE;
		out->owner_datum = UINT32_MAX;
		out->metadata_known &= (uint8_t)~0x01u;
	}
	if (has_position && (!position || !(metadata_known & 0x02u)))
		out->event = HCU_SOUND_EVENT_NONE; /* position claimed but not supplied */
	return request_valid(out);
}

/* FNV-1a over the preserved fields only: event, owner, position, priority,
 * gain and pitch. Sequence, repeat, accepted and metadata are excluded. */
static uint32_t fnv_word(uint32_t h, uint32_t w)
{
	uint32_t i;
	for (i = 0; i < 4u; ++i) {
		h ^= (w >> (8u * i)) & 0xffu;
		h *= 16777619u;
	}
	return h;
}

static uint32_t float_bits(float f)
{
	uint32_t u;
	memcpy(&u, &f, sizeof(u));
	return u;
}

static uint32_t record_hash(const hcu_sound_request *r)
{
	uint32_t h = 2166136261u;
	h = fnv_word(h, r->event);
	h = fnv_word(h, r->owner_kind);
	h = fnv_word(h, r->owner_datum);
	h = fnv_word(h, r->has_position);
	h = fnv_word(h, float_bits(r->position[0]));
	h = fnv_word(h, float_bits(r->position[1]));
	h = fnv_word(h, float_bits(r->position[2]));
	h = fnv_word(h, r->priority);
	h = fnv_word(h, float_bits(r->gain));
	h = fnv_word(h, float_bits(r->pitch));
	return h;
}

static void coverage_one(hcu_sound_coverage *c, const hcu_sound_request *r,
	uint32_t hash)
{
	c->kinds[r->event & 7u]++;
	c->checksum ^= hash;
	if (r->event == HCU_SOUND_EVENT_PERMUTATION_REQUEST)
		return;
	c->playback++;
	if (r->has_position)
		c->spatial++;
	if (r->metadata_known & 0x01u)
		c->owner_known++;
	if ((r->metadata_known & 0x02u) && r->has_position)
		c->position_known++;
	if (r->metadata_known & 0x04u) {
		c->priority_known++;
		if (r->priority < c->priority_min) c->priority_min = r->priority;
		if (r->priority > c->priority_max) c->priority_max = r->priority;
	}
	if (r->metadata_known & 0x08u)
		c->gain_known++;
	if (r->metadata_known & 0x10u)
		c->pitch_known++;
}

#define RING_MASK (HCU_SOUND_REQUEST_CAPACITY - 1u)

void hcu_sound_requests_init(hcu_sound_request_queue *queue)
{
	if (!queue) return;
	memset(queue, 0, sizeof(*queue));
	queue->coverage.priority_min = 255u;
	queue->spu2_playback_qualified = 0;
}

void hcu_sound_requests_reset(hcu_sound_request_queue *queue)
{
	uint32_t i;
	if (!queue) return;
	for (i = 0; i < queue->count; ++i)
		queue->coverage.out_fold ^= record_hash(&queue->ring[(queue->head + i) & RING_MASK]);
	queue->head = 0;
	queue->count = 0;
	queue->counters.pending = 0;
	queue->counters.resets++;
}

#define COALESCE_WINDOW 8u
#define REPEAT_MAX 255u

/* Holds only while the ring is power-of-two sized and the record stays within
 * its 52-byte budget (the queue is BSS, charged to resident_gameplay). */
typedef char hcu_sound_request_capacity_is_pow2
	[((HCU_SOUND_REQUEST_CAPACITY & RING_MASK) == 0u) ? 1 : -1];
typedef char hcu_sound_request_size_budget[(sizeof(hcu_sound_request) <= 52u) ? 1 : -1];

#define AT(queue, i) ((queue)->ring[((queue)->head + (i)) & RING_MASK])

static int is_stop(const hcu_sound_request *r)
{
	return r->event == HCU_SOUND_EVENT_STOP || r->event == HCU_SOUND_EVENT_LOOPING_STOP;
}

static int same_loop(const hcu_sound_request *a, const hcu_sound_request *b)
{
	return a->owner_kind == b->owner_kind && a->owner_datum == b->owner_datum &&
		a->sound_index == b->sound_index;
}

/* Merges into a pending PERMUTATION_REQUEST in the last few slots only. */
static int coalesce_permutation(hcu_sound_request_queue *queue,
	const hcu_sound_request *r)
{
	uint32_t j, n = queue->count < COALESCE_WINDOW ? queue->count : COALESCE_WINDOW;
	for (j = 0; j < n; ++j) {
		hcu_sound_request *e = &AT(queue, queue->count - 1u - j);
		if (e->event == HCU_SOUND_EVENT_PERMUTATION_REQUEST &&
			e->permutation == r->permutation && e->flags == r->flags &&
			e->repeat < REPEAT_MAX) {
			e->repeat++;
			e->accepted &= r->accepted;
			queue->counters.coalesced++;
			return 1;
		}
	}
	return 0;
}

static int find_oldest_permutation(const hcu_sound_request_queue *queue)
{
	uint32_t i;
	for (i = 0; i < queue->count; ++i)
		if (AT(queue, i).event == HCU_SOUND_EVENT_PERMUTATION_REQUEST)
			return (int)i;
	return -1;
}

/* Oldest IMPULSE or FADE that satisfies accept(). */
static int find_impulse_or_fade(const hcu_sound_request_queue *queue,
	const hcu_sound_request *r, int any_priority)
{
	uint32_t i;
	for (i = 0; i < queue->count; ++i) {
		const hcu_sound_request *e = &AT(queue, i);
		if ((e->event == HCU_SOUND_EVENT_IMPULSE || e->event == HCU_SOUND_EVENT_FADE) &&
			(any_priority || e->priority < r->priority))
			return (int)i;
	}
	return -1;
}

/* Picks the record to evict for a full ring, or -1 when the new record must be
 * rejected. Permutation requests never evict. */
static int pick_victim(const hcu_sound_request_queue *queue,
	const hcu_sound_request *r)
{
	uint32_t i;
	int v;
	if (r->event == HCU_SOUND_EVENT_PERMUTATION_REQUEST)
		return -1;
	v = find_oldest_permutation(queue);
	if (v >= 0)
		return v;
	if (!is_stop(r))
		return find_impulse_or_fade(queue, r, 0);
	/* Stops are never dropped while a non-stop can make room: its START may be
	 * pending or already drained and playing. Evict any IMPULSE/FADE, then a
	 * redundant stop, then a LOOPING_START for another loop, then any
	 * LOOPING_START. A ring of distinct stops rejects the new stop. */
	v = find_impulse_or_fade(queue, r, 1);
	if (v >= 0)
		return v;
	/* An older stop with a newer stop for the same loop is redundant. */
	for (i = 0; i < queue->count; ++i) {
		const hcu_sound_request *e = &AT(queue, i);
		uint32_t j;
		if (!is_stop(e))
			continue;
		for (j = i + 1u; j < queue->count; ++j)
			if (is_stop(&AT(queue, j)) && same_loop(&AT(queue, j), e))
				return (int)i;
		if (same_loop(e, r))
			return (int)i;
	}
	for (i = 0; i < queue->count; ++i) {
		const hcu_sound_request *e = &AT(queue, i);
		if (e->event == HCU_SOUND_EVENT_LOOPING_START && !same_loop(e, r))
			return (int)i;
	}
	for (i = 0; i < queue->count; ++i)
		if (AT(queue, i).event == HCU_SOUND_EVENT_LOOPING_START)
			return (int)i;
	return -1;
}

/* Removes slot i and shifts newer records down one place, keeping order. */
static void evict_at(hcu_sound_request_queue *queue, uint32_t i)
{
	uint32_t j;
	queue->coverage.out_fold ^= record_hash(&AT(queue, i));
	for (j = i; j + 1u < queue->count; ++j)
		AT(queue, j) = AT(queue, j + 1u);
	queue->count--;
	queue->counters.evicted++;
	queue->counters.pending = queue->count;
}

int hcu_sound_requests_submit(hcu_sound_request_queue *queue,
	const hcu_sound_request *request)
{
	hcu_sound_request *slot;
	int victim;
	if (!queue || !request) return 0;
	queue->counters.submitted++;
	if (!request_valid(request)) {
		queue->counters.rejected++;
		return 0;
	}
	if (request->event == HCU_SOUND_EVENT_PERMUTATION_REQUEST &&
		coalesce_permutation(queue, request))
		return 1;
	if (queue->count >= HCU_SOUND_REQUEST_CAPACITY) {
		victim = pick_victim(queue, request);
		if (victim < 0) {
			queue->counters.rejected++;
			queue->counters.dropped_while_full++;
			return 0;
		}
		evict_at(queue, (uint32_t)victim);
	}
	slot = &AT(queue, queue->count);
	*slot = *request;
	queue->next_sequence++;
	if (queue->next_sequence == 0) queue->next_sequence = 1;
	slot->sequence = queue->next_sequence;
	slot->repeat = 1u;
	queue->coverage.record_fold ^= record_hash(slot);
	queue->count++;
	queue->counters.accepted++;
	queue->counters.pending = queue->count;
	if (queue->count > queue->counters.high_water)
		queue->counters.high_water = queue->count;
	return 1;
}

size_t hcu_sound_requests_drain_each(hcu_sound_request_queue *queue,
	hcu_sound_request_fn fn, void *context, size_t max)
{
	size_t n = 0;
	if (!queue) return 0;
	while (n < max && queue->count > 0) {
		const hcu_sound_request *r = &queue->ring[queue->head];
		coverage_one(&queue->coverage, r, record_hash(r));
		if (fn) fn(context, r);
		queue->head = (queue->head + 1u) & RING_MASK;
		queue->count--;
		n++;
	}
	queue->counters.drained += (uint32_t)n;
	queue->counters.pending = queue->count;
	return n;
}

struct drain_copy {
	hcu_sound_request *out;
	size_t n;
};

static void drain_copy_one(void *context, const hcu_sound_request *request)
{
	struct drain_copy *c = (struct drain_copy *)context;
	c->out[c->n++] = *request;
}

size_t hcu_sound_requests_drain(hcu_sound_request_queue *queue,
	hcu_sound_request *out, size_t max)
{
	struct drain_copy c;
	if (!queue || !out) return 0;
	c.out = out;
	c.n = 0;
	hcu_sound_requests_drain_each(queue, drain_copy_one, &c, max);
	return c.n;
}

void hcu_sound_requests_counters(const hcu_sound_request_queue *queue,
	hcu_sound_request_counters *out)
{
	if (!queue || !out) return;
	*out = queue->counters;
}

void hcu_sound_requests_coverage(const hcu_sound_request_queue *queue,
	hcu_sound_coverage *out)
{
	if (!queue || !out) return;
	*out = queue->coverage;
}

void hcu_sound_requests_print(const hcu_sound_request_queue *queue,
	const char *phase)
{
	const hcu_sound_coverage *c;
	uint32_t i, pending_fold = 0;
	if (!queue) return;
	c = &queue->coverage;
	/* Pending records are still in the ring; their fold completes the record side. */
	for (i = 0; i < queue->count; ++i)
		pending_fold ^= record_hash(&AT(queue, i));
	printf("HALO_PS2_LOCAL sound-requests phase=%s submitted=%u accepted=%u "
		"rejected=%u drained=%u pending=%u high=%u dropped-full=%u resets=%u "
		"coalesced=%u evicted=%u capacity=%u spu2-playback=not-qualified\n",
		phase ? phase : "-",
		(unsigned)queue->counters.submitted, (unsigned)queue->counters.accepted,
		(unsigned)queue->counters.rejected, (unsigned)queue->counters.drained,
		(unsigned)queue->counters.pending, (unsigned)queue->counters.high_water,
		(unsigned)queue->counters.dropped_while_full, (unsigned)queue->counters.resets,
		(unsigned)queue->counters.coalesced, (unsigned)queue->counters.evicted,
		(unsigned)HCU_SOUND_REQUEST_CAPACITY);
	printf("HALO_PS2_LOCAL sound-coverage phase=%s ev-perm=%u ev-impulse=%u "
		"ev-loop-start=%u ev-loop-stop=%u ev-fade=%u ev-stop=%u playback=%u "
		"owner=%u position=%u spatial=%u priority=%u gain=%u pitch=%u "
		"prio-min=%u prio-max=%u drain-checksum=%08x record-checksum=%08x\n",
		phase ? phase : "-",
		(unsigned)c->kinds[1], (unsigned)c->kinds[2], (unsigned)c->kinds[3],
		(unsigned)c->kinds[4], (unsigned)c->kinds[5], (unsigned)c->kinds[6],
		(unsigned)c->playback, (unsigned)c->owner_known, (unsigned)c->position_known,
		(unsigned)c->spatial, (unsigned)c->priority_known, (unsigned)c->gain_known, (unsigned)c->pitch_known,
		(unsigned)c->priority_min, (unsigned)c->priority_max,
		(unsigned)c->checksum, (unsigned)(c->record_fold ^ c->out_fold ^ pending_fold));
}
