#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include "ps2_animation_trace.h"

static int write_capture_to_stdout(void *user, void const *bytes,
	unsigned long count)
{
	(void)user;
	return fwrite(bytes, 1, count, stdout) == count;
}

static int reject_capture_chunk(void *user, void const *bytes,
	unsigned long count)
{
	(void)user;
	(void)bytes;
	(void)count;
	return 0;
}

int main(void)
{
	static struct ps2_animation_trace_event storage[PS2_ANIMATION_TRACE_CAPACITY];
	static struct ps2_animation_trace_context context_storage[PS2_ANIMATION_TRACE_CAPACITY];
	static struct ps2_animation_trace_event other_storage[1];
	static struct ps2_animation_trace_context other_context_storage[1];
	static unsigned char misaligned_storage[sizeof(struct ps2_animation_trace_event) + sizeof(unsigned long)];
	static unsigned char misaligned_context_storage[sizeof(struct ps2_animation_trace_context) + sizeof(unsigned long)];
	struct animation *animation = (struct animation *)0x1234;
	void const *base = (void const *)0x5678;
	struct ps2_animation_trace_event const *events;
	struct ps2_animation_trace_context const *contexts;
	long index;
	short previous_phase;
	struct ps2_animation_trace_context context, previous_context, saved_animation_context;

	assert(!ps2_animation_trace_valid());
	assert(!ps2_animation_trace_bind(0, PS2_ANIMATION_TRACE_CAPACITY));
	assert(!ps2_animation_trace_bind(storage, 0));
	assert(!ps2_animation_trace_bind(
		(struct ps2_animation_trace_event *)(misaligned_storage + 1), 1));
	assert(!ps2_animation_trace_bind(storage, LONG_MAX));
	assert(!ps2_animation_trace_bind(
		(struct ps2_animation_trace_event *)(uintptr_t)(UINTPTR_MAX -
			sizeof(struct ps2_animation_trace_event) + 1), 1));
	assert(!ps2_animation_trace_bind_contexts(0, PS2_ANIMATION_TRACE_CAPACITY));
	assert(!ps2_animation_trace_bind_contexts(context_storage, 0));
	assert(!ps2_animation_trace_bind_contexts(context_storage, LONG_MAX));
	assert(!ps2_animation_trace_bind_contexts(
		(struct ps2_animation_trace_context *)(uintptr_t)(UINTPTR_MAX -
			sizeof(struct ps2_animation_trace_context) + 1), 1));
	assert(!ps2_animation_trace_bind_contexts(
		(struct ps2_animation_trace_context *)(misaligned_context_storage + 1), 1));
#if defined(TEST_TRACE_EVENT_BIND_FIRST)
	assert(ps2_animation_trace_bind(storage, PS2_ANIMATION_TRACE_CAPACITY));
	assert(!ps2_animation_trace_valid());
	assert(!ps2_animation_trace_bind_contexts(context_storage,
		PS2_ANIMATION_TRACE_CAPACITY - 1));
	assert(!ps2_animation_trace_bind_contexts(
		(struct ps2_animation_trace_context *)storage,
		PS2_ANIMATION_TRACE_CAPACITY));
	assert(ps2_animation_trace_bind_contexts(context_storage,
		PS2_ANIMATION_TRACE_CAPACITY));
#else
	assert(ps2_animation_trace_bind_contexts(context_storage,
		PS2_ANIMATION_TRACE_CAPACITY));
	assert(!ps2_animation_trace_bind(storage,
		PS2_ANIMATION_TRACE_CAPACITY - 1));
	assert(!ps2_animation_trace_bind(
		(struct ps2_animation_trace_event *)context_storage,
		PS2_ANIMATION_TRACE_CAPACITY));
	assert(ps2_animation_trace_bind_contexts(context_storage,
		PS2_ANIMATION_TRACE_CAPACITY) == 0);
	assert(ps2_animation_trace_bind(storage, PS2_ANIMATION_TRACE_CAPACITY));
#endif
	assert(ps2_animation_trace_valid());
	assert(!ps2_animation_trace_bind(other_storage, 1));
	assert(!ps2_animation_trace_bind_contexts(other_context_storage, 1));
	ps2_animation_trace_reset();
	assert(ps2_animation_trace_valid());
	assert(ps2_animation_trace_phase_set(_ps2_animation_trace_phase_none) ==
		_ps2_animation_trace_phase_none);
	ps2_animation_trace_record(_ps2_animation_trace_frame_data, animation,
		base, 12, 24, 3, 1);
	assert(ps2_animation_trace_count() == 1);
	assert(ps2_animation_trace_dropped() == 0);
	events = ps2_animation_trace_events();
	contexts = ps2_animation_trace_contexts();
	assert(events[0].animation_identity == (unsigned long)animation);
	assert(events[0].base_identity == (unsigned long)base);
	assert(events[0].offset == 12 && events[0].bytes == 24);
	assert(events[0].site == _ps2_animation_trace_frame_data);
	assert(events[0].detail == 3 && events[0].accepted == 1);
	assert(events[0].context_token == 0);
	previous_phase = ps2_animation_trace_phase_set(
		_ps2_animation_trace_phase_object_pose);
	assert(previous_phase == _ps2_animation_trace_phase_none);
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 0, 4, 0, 1);
	assert(events[1].context_token == 2);
	assert(contexts[1].phase == _ps2_animation_trace_phase_object_pose);
	previous_phase = ps2_animation_trace_phase_set(
		_ps2_animation_trace_phase_unit_pose);
	assert(previous_phase == _ps2_animation_trace_phase_object_pose);
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 4, 4, 0, 1);
	assert(events[2].context_token == 3);
	assert(contexts[2].phase == _ps2_animation_trace_phase_unit_pose);
	assert(ps2_animation_trace_phase_set(previous_phase) ==
		_ps2_animation_trace_phase_unit_pose);
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 8, 4, 0, 1);
	assert(events[3].context_token == 4);
	assert(contexts[3].phase == _ps2_animation_trace_phase_object_pose);
	assert(ps2_animation_trace_phase_set(previous_phase) ==
		_ps2_animation_trace_phase_object_pose);
	assert(ps2_animation_trace_phase_set(_ps2_animation_trace_phase_none) ==
		_ps2_animation_trace_phase_object_pose);
	ps2_animation_trace_record(_ps2_animation_trace_schema_data, animation,
		base, 0, 99, 0, 0);
	assert(ps2_animation_trace_count() == 5 && events[4].accepted == 0);
	context.map_epoch = 9;
	context.datum_index = 0x1234;
	context.tick = 42;
	context.render_frame = 84;
	context.graph_index = 3;
	context.animation_index = 7;
	context.frame_index = 11;
	context.owner_index = 2;
	context.phase = _ps2_animation_trace_phase_object_pose;
	context.reserved = 0;
	context.valid_mask = _ps2_animation_trace_context_installed |
		_ps2_animation_trace_context_map_epoch |
		_ps2_animation_trace_context_datum |
		_ps2_animation_trace_context_tick |
		_ps2_animation_trace_context_render_frame |
		_ps2_animation_trace_context_graph |
		_ps2_animation_trace_context_animation |
		_ps2_animation_trace_context_frame |
		_ps2_animation_trace_context_owner;
	previous_context = ps2_animation_trace_context_set(&context);
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 0, 1, 0, 1);
	assert(events[5].context_token == 6);
	assert(contexts[5].map_epoch == 9 && contexts[5].datum_index == 0x1234);
	assert(contexts[5].tick == 42 && contexts[5].render_frame == 84);
	assert(contexts[5].graph_index == 3 && contexts[5].animation_index == 7);
	assert(contexts[5].frame_index == 11 && contexts[5].owner_index == 2);
	assert(contexts[5].valid_mask == context.valid_mask);
	ps2_animation_trace_context_set(&previous_context);
	ps2_animation_trace_context_set(&context);
	ps2_animation_trace_context_push_animation(&saved_animation_context, 12, 44, 0);
	assert(ps2_animation_trace_context_get().animation_index == 12);
	assert(!(ps2_animation_trace_context_get().valid_mask &
		_ps2_animation_trace_context_frame));
	ps2_animation_trace_context_pop(&saved_animation_context);
	assert(ps2_animation_trace_context_get().animation_index == 7);
	assert(ps2_animation_trace_context_get().frame_index == 11);
	ps2_animation_trace_context_set(&previous_context);
	ps2_animation_trace_map_epoch_advance();
	ps2_animation_trace_tick_advance();
	ps2_animation_trace_tick_advance();
	ps2_animation_trace_render_frame_set(17);
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 0, 1, 0, 1);
	assert(events[6].context_token == 7);
	assert(contexts[6].map_epoch == 1 && contexts[6].tick == 2);
	assert(contexts[6].render_frame == 17);
	assert((contexts[6].valid_mask &
		(_ps2_animation_trace_context_map_epoch |
		 _ps2_animation_trace_context_tick |
		 _ps2_animation_trace_context_render_frame)) ==
		(_ps2_animation_trace_context_map_epoch |
		 _ps2_animation_trace_context_tick |
		 _ps2_animation_trace_context_render_frame));
	ps2_animation_trace_map_epoch_advance();
	ps2_animation_trace_tick_advance();
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
		base, 0, 1, 0, 1);
	assert(contexts[7].map_epoch == 2 && contexts[7].tick == 3);
	assert(ps2_animation_trace_export(reject_capture_chunk, 0) == 0);
	assert(ps2_animation_trace_export(write_capture_to_stdout, 0) == 1);
	assert(fflush(stdout) == 0);
	for (index = ps2_animation_trace_count(); index < PS2_ANIMATION_TRACE_CAPACITY + 3; index++)
		ps2_animation_trace_record(_ps2_animation_trace_frame_info, animation,
			base, index, 1, 0, 1);
	assert(ps2_animation_trace_count() == PS2_ANIMATION_TRACE_CAPACITY);
	assert(ps2_animation_trace_dropped() == 3);
	assert(!ps2_animation_trace_valid());
	ps2_animation_trace_reset();
	assert(ps2_animation_trace_count() == 0 && ps2_animation_trace_dropped() == 0);
	assert(ps2_animation_trace_valid());
	return 0;
}
