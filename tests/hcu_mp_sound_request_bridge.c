/* Test-only recorder in front of CE's sound platform vtable.
 * This is not an SPU2 backend and it does not play audio. The production
 * PS2 preferences select no platform; the drive build (no HALO_PS2) uses
 * platform 0 so the real sound_manager calls can be observed. */
#include "sound/sound_preferences.c"
#include "sound/sound_manager.c"
#include "structures/structure_bsp_definitions.h"
#include "scenario/fog_definitions.h"

#include <stdint.h>

typedef char soundreq_ilp32[sizeof(void *) == 4 && sizeof(long) == 4 ? 1 : -1];

struct soundreq_contract_record
{
	long tag_datum;
	long owner;
	short channel_index;
	short spatialized;
	struct sound_location location;
	real obstruction;
	real occlusion;
	struct platform_sound_channel_properties playback;
};

enum { SOUNDREQ_MAX_REQUESTS = 32, SOUNDREQ_MAX_SHADOWS = 96, SOUNDREQ_MAX_TAGS = 64 };

struct soundreq_request
{
	short channel_index;
	char name[32];
	real permutation_gain;
	struct platform_sound_channel_properties properties;
	boolean properties_valid;
};

struct soundreq_shadow
{
	void *live;
	void *copy;
	unsigned size;
	const char *label;
};

struct soundreq_tag
{
	long group;
	long index;
	void *body;
};

static struct soundreq_request soundreq_requests[SOUNDREQ_MAX_REQUESTS];
static int soundreq_request_count;
static int soundreq_property_count;
static int soundreq_location_count;
static int soundreq_listener_count;
static int soundreq_initialize_count;
static int soundreq_dispose_count;
static int soundreq_stop_count;
static int soundreq_begin_count;
static int soundreq_end_count;
static struct soundreq_shadow soundreq_shadows[SOUNDREQ_MAX_SHADOWS];
static int soundreq_shadow_count;
static struct soundreq_tag soundreq_tags[SOUNDREQ_MAX_TAGS];
static int soundreq_tag_count;
static int soundreq_published_bsp;
static int soundreq_collision_depth;

extern unsigned soundreq_obstruction_calls;
extern unsigned soundreq_cache_new_calls;
extern unsigned soundreq_cache_request_calls;
extern unsigned soundreq_stereo_calls;
extern unsigned soundreq_stereo_positioned_calls;
extern unsigned soundreq_stereo_unexpected_args;

static unsigned soundreq_bits(real value)
{
	unsigned bits;

	csmemcpy(&bits, &value, sizeof(bits));
	return bits;
}

static void soundreq_fail(const char *message)
{
	fprintf(stderr, "soundreq: %s\n", message);
	exit(1);
}

static void soundreq_shadow_add(void *live, unsigned size, const char *label)
{
	struct soundreq_shadow *shadow;

	if (soundreq_shadow_count >= SOUNDREQ_MAX_SHADOWS)
		soundreq_fail("shadow table full");
	shadow = &soundreq_shadows[soundreq_shadow_count++];
	shadow->live = live;
	shadow->size = size;
	shadow->label = label;
	shadow->copy = malloc(size ? size : 1u);
	if (!shadow->copy)
		soundreq_fail("shadow malloc");
	csmemcpy(shadow->copy, live, size);
}

static int soundreq_shadow_check(void)
{
	int index;

	for (index = 0; index < soundreq_shadow_count; index++)
	{
		struct soundreq_shadow *shadow = &soundreq_shadows[index];

		if (csmemcmp(shadow->live, shadow->copy, shadow->size) != 0)
		{
			fprintf(stderr, "feedback write in %s\n", shadow->label);
			return 0;
		}
	}
	return 1;
}

static void soundreq_reset_recorder(void)
{
	csmemset(soundreq_requests, 0, sizeof(soundreq_requests));
	soundreq_request_count = 0;
	soundreq_property_count = 0;
	soundreq_location_count = 0;
	soundreq_listener_count = 0;
	soundreq_initialize_count = 0;
	soundreq_dispose_count = 0;
	soundreq_stop_count = 0;
	soundreq_begin_count = 0;
	soundreq_end_count = 0;
	soundreq_shadow_count = 0;
	soundreq_tag_count = 0;
	soundreq_obstruction_calls = 0;
	soundreq_cache_request_calls = 0;
	soundreq_stereo_calls = 0;
	soundreq_stereo_positioned_calls = 0;
	soundreq_stereo_unexpected_args = 0;
}

static boolean soundreq_initialize(struct sound_preferences *preferences)
{
	(void)preferences;
	soundreq_initialize_count++;
	return TRUE;
}

static void soundreq_dispose_platform(void)
{
	soundreq_dispose_count++;
}

static void soundreq_set_listener(
	struct platform_sound_listener_properties const *properties)
{
	(void)properties;
	soundreq_listener_count++;
}

static void soundreq_begin_scene(void)
{
	soundreq_begin_count++;
}

static void soundreq_end_scene(void)
{
	soundreq_end_count++;
}

static void soundreq_queue(short channel_index, struct sound_permutation *permutation)
{
	struct soundreq_request *request;
	unsigned char before[sizeof(struct sound_permutation)];

	if (!permutation)
		soundreq_fail("null permutation queued");
	if (soundreq_request_count >= SOUNDREQ_MAX_REQUESTS)
		soundreq_fail("request table full");
	csmemcpy(before, permutation, sizeof(before));
	request = &soundreq_requests[soundreq_request_count++];
	request->channel_index = channel_index;
	csmemcpy(request->name, permutation->name, sizeof(request->name));
	request->permutation_gain = permutation->gain;
	if (csmemcmp(before, permutation, sizeof(before)) != 0)
		soundreq_fail("recorder wrote the permutation");
}

static void soundreq_channel_update(short channel_index)
{
	(void)channel_index;
}

static void soundreq_stop_channel(short channel_index)
{
	(void)channel_index;
	soundreq_stop_count++;
}

static short soundreq_get_channel_state(short channel_index)
{
	(void)channel_index;
	return _sound_channel_playing;
}

static void soundreq_set_pause(boolean paused)
{
	(void)paused;
}

static void soundreq_flush(void) {}

static void soundreq_set_location(short channel_index, boolean spatialized,
	struct sound_location const *location, real obstruction, real occlusion,
	boolean attenuate_direct_path)
{
	(void)channel_index;
	(void)spatialized;
	(void)location;
	(void)obstruction;
	(void)occlusion;
	(void)attenuate_direct_path;
	soundreq_location_count++;
}

static void soundreq_set_properties(short channel_index,
	struct platform_sound_channel_properties const *properties, boolean gain_only)
{
	struct soundreq_request *request;

	if (!properties)
		soundreq_fail("null properties");
	if (soundreq_property_count >= SOUNDREQ_MAX_REQUESTS)
		soundreq_fail("property table full");
	request = &soundreq_requests[soundreq_property_count++];
	request->channel_index = channel_index;
	request->properties = *properties;
	request->properties_valid = TRUE;
	request->properties.gain = properties->gain;
	if (gain_only)
		soundreq_fail("first properties call was gain-only");
}

struct sound_platform_definition platform_sound_dsound =
{
	0,
	{0, 0},
	soundreq_initialize,
	soundreq_dispose_platform,
	soundreq_set_listener,
	soundreq_begin_scene,
	soundreq_end_scene,
	soundreq_queue,
	soundreq_channel_update,
	soundreq_stop_channel,
	soundreq_get_channel_state,
	soundreq_set_pause,
	soundreq_flush,
	soundreq_set_location,
	soundreq_set_properties,
	1.f
};

void *tag_get(long group_tag, long tag_index)
{
	int index;

	for (index = 0; index < soundreq_tag_count; index++)
	{
		if (soundreq_tags[index].group == group_tag &&
			soundreq_tags[index].index == tag_index)
			return soundreq_tags[index].body;
	}
	return NULL;
}

static void soundreq_register_tag(long group, long index, void *body)
{
	if (soundreq_tag_count >= SOUNDREQ_MAX_TAGS)
		soundreq_fail("tag table full");
	soundreq_tags[soundreq_tag_count].group = group;
	soundreq_tags[soundreq_tag_count].index = index;
	soundreq_tags[soundreq_tag_count].body = body;
	soundreq_tag_count++;
}

static void soundreq_print_contract(void)
{
	struct sound_preferences *preferences;
	unsigned size = (unsigned)sizeof(struct soundreq_contract_record);
	int sum = 0;
	int index;

	read_sound_preferences(&preferences);
	for (index = 0; index < 4; index++)
		sum += preferences->virtual_channel_counts[index];
	printf("contract_size %u\n", size);
	printf("virtual_counts %d %d %d %d\n",
		preferences->virtual_channel_counts[0],
		preferences->virtual_channel_counts[1],
		preferences->virtual_channel_counts[2],
		preferences->virtual_channel_counts[3]);
	printf("virtual_sum %d\n", sum);
	printf("virtual_bytes %u\n", size * (unsigned)sum);
	printf("max_channels %d\n", MAXIMUM_SOUND_CHANNELS);
	printf("max_bytes %u\n", size * (unsigned)MAXIMUM_SOUND_CHANNELS);
	printf("audio_region 524288\n");
	printf("contract_fit %d\n",
		size * (unsigned)MAXIMUM_SOUND_CHANNELS <= 524288u &&
		size * (unsigned)sum <= 524288u);
	printf("platform_slot1_null %d\n", platform_definitions[1] == NULL);
	printf("published_bsp %d\n", soundreq_published_bsp);
	printf("collision_depth %d\n", soundreq_collision_depth);
}

extern char const *sound_class_names[];

static void soundreq_print_classes(void)
{
	short index;

	for (index = 0; index < 51; index++)
	{
		struct sound_class_definition *definition;

		if (!sound_class_names[index] || !sound_class_names[index][0])
		{
			printf("CLASS %d empty\n", index);
			continue;
		}
		definition = sound_class_get(index);
		printf("CLASS %d wet=%08x min=%08x max=%08x disabled=%d\n",
			index,
			soundreq_bits(definition->wet_gain),
			soundreq_bits(definition->minimum_distance),
			soundreq_bits(definition->maximum_distance),
			definition->disabled ? 1 : 0);
	}
}

static void soundreq_print_schema(void)
{
	printf("mode schema\n");
	printf("sizeof_sound_definition %u\n", (unsigned)sizeof(struct sound_definition));
	printf("off_sound_class %u\n", (unsigned)offsetof(struct sound_definition, sound_class));
	printf("off_sample_rate %u\n", (unsigned)offsetof(struct sound_definition, sample_rate));
	printf("off_minimum_distance %u\n", (unsigned)offsetof(struct sound_definition, minimum_distance));
	printf("off_random_pitch_bounds %u\n", (unsigned)offsetof(struct sound_definition, random_pitch_bounds));
	printf("off_inner_cone %u\n", (unsigned)offsetof(struct sound_definition, inner_cone_angle));
	printf("off_gain_modifier %u\n", (unsigned)offsetof(struct sound_definition, gain_modifier));
	printf("off_zero_gain %u\n", (unsigned)offsetof(struct sound_definition, zero_gain_modifier));
	printf("off_zero_pitch %u\n", (unsigned)offsetof(struct sound_definition, zero_pitch_modifier));
	printf("off_one_gain %u\n", (unsigned)offsetof(struct sound_definition, one_gain_modifier));
	printf("off_one_pitch %u\n", (unsigned)offsetof(struct sound_definition, one_pitch_modifier));
	printf("off_encoding %u\n", (unsigned)offsetof(struct sound_definition, encoding));
	printf("off_compression %u\n", (unsigned)offsetof(struct sound_definition, compression));
	printf("off_pitch_ranges %u\n", (unsigned)offsetof(struct sound_definition, pitch_ranges));
	printf("sizeof_pitch_range %u\n", (unsigned)sizeof(struct sound_pitch_range));
	printf("off_natural_pitch %u\n", (unsigned)offsetof(struct sound_pitch_range, natural_pitch));
	printf("off_bend_bounds %u\n", (unsigned)offsetof(struct sound_pitch_range, bend_bounds));
	printf("off_actual_permutation_count %u\n", (unsigned)offsetof(struct sound_pitch_range, actual_permutation_count));
	printf("off_playback_rate %u\n", (unsigned)offsetof(struct sound_pitch_range, playback_rate));
	printf("off_permutations %u\n", (unsigned)offsetof(struct sound_pitch_range, permutations));
	printf("sizeof_permutation %u\n", (unsigned)sizeof(struct sound_permutation));
	printf("off_permutation_gain %u\n", (unsigned)offsetof(struct sound_permutation, gain));
	printf("sizeof_looping %u\n", (unsigned)sizeof(struct looping_sound_definition));
	printf("off_tracks %u\n", (unsigned)offsetof(struct looping_sound_definition, tracks));
	printf("off_details %u\n", (unsigned)offsetof(struct looping_sound_definition, details));
	printf("sizeof_track %u\n", (unsigned)sizeof(struct looping_sound_track));
	printf("off_track_flags %u\n", (unsigned)offsetof(struct looping_sound_track, flags));
	printf("off_track_gain %u\n", (unsigned)offsetof(struct looping_sound_track, gain));
	printf("off_fade_in %u\n", (unsigned)offsetof(struct looping_sound_track, fade_in_duration));
	printf("off_start_sound %u\n", (unsigned)offsetof(struct looping_sound_track, start_sound));
	printf("off_loop_sound %u\n", (unsigned)offsetof(struct looping_sound_track, loop_sound));
	printf("sizeof_environment %u\n", (unsigned)sizeof(struct sound_environment_definition));
	printf("off_environment_priority %u\n", (unsigned)offsetof(struct sound_environment_definition, priority));
	printf("sizeof_location %u\n", (unsigned)sizeof(struct sound_location));
	printf("sizeof_properties %u\n", (unsigned)sizeof(struct platform_sound_channel_properties));
	printf("sizeof_bsp %u\n", (unsigned)sizeof(struct structure_bsp));
	printf("off_clusters %u\n", (unsigned)offsetof(struct structure_bsp, clusters));
	printf("off_background_palette %u\n", (unsigned)offsetof(struct structure_bsp, background_sound_palette));
	printf("off_environment_palette %u\n", (unsigned)offsetof(struct structure_bsp, sound_environment_palette));
	printf("off_world_bounds %u\n", (unsigned)offsetof(struct structure_bsp, world_bounds));
	printf("sizeof_cluster %u\n", (unsigned)sizeof(struct structure_cluster));
	printf("sizeof_fog %u\n", (unsigned)sizeof(struct fog_definition));
	printf("off_fog_background %u\n", (unsigned)offsetof(struct fog_definition, background_sound_index));
	printf("off_fog_environment %u\n", (unsigned)offsetof(struct fog_definition, sound_environment));
	printf("preferences_platform %d\n", 0);
	soundreq_print_contract();
	soundreq_print_classes();
}

static void soundreq_prepare_manager(void)
{
	sound_dispose();
	sound_data = NULL;
	looping_sound_data = NULL;
	sound_manager_globals.channel_count = 0;
	sound_manager_globals.initialized = FALSE;
	sound_manager_globals.platform_definition = NULL;
	sound_manager_globals.render_time = 0;
	sound_manager_globals.ticks_elapsed = 0.f;
	sound_manager_globals.nondialog_gain = 1.f;
	*get_global_local_random_seed_address() = 0;
}

static const unsigned char *soundreq_cursor;
static const unsigned char *soundreq_end;

static void soundreq_need(unsigned size)
{
	if ((unsigned)(soundreq_end - soundreq_cursor) < size)
		soundreq_fail("truncated case");
}

static uint32_t soundreq_u32(void)
{
	uint32_t value;

	soundreq_need(4);
	csmemcpy(&value, soundreq_cursor, 4);
	soundreq_cursor += 4;
	return value;
}

static int32_t soundreq_i32(void)
{
	return (int32_t)soundreq_u32();
}

static void *soundreq_take(unsigned size)
{
	void *body = malloc(size ? size : 1u);

	if (!body)
		soundreq_fail("case malloc");
	soundreq_need(size);
	if (size)
		csmemcpy(body, soundreq_cursor, size);
	soundreq_cursor += size;
	return body;
}

static void soundreq_bind(struct tag_block *block, void *address)
{
	block->address = address;
	block->definition = NULL;
}

static void soundreq_clear_tag_data(struct tag_data *data)
{
	data->address = NULL;
	data->definition = NULL;
}

static void soundreq_load_sounds(int sound_count)
{
	int sound_index;

	for (sound_index = 0; sound_index < sound_count; sound_index++)
	{
		int32_t datum = soundreq_i32();
		uint32_t nbytes = soundreq_u32();
		struct sound_definition *definition;
		int range_index;
		int range_count;

		if (nbytes != sizeof(struct sound_definition))
			soundreq_fail("sound size");
		definition = soundreq_take(nbytes);
		range_count = soundreq_i32();
		if (range_count != definition->pitch_ranges.count ||
			range_count < 0 || range_count > MAXIMUM_PITCH_RANGES_PER_SOUND)
			soundreq_fail("pitch range count");
		if (range_count)
		{
			struct sound_pitch_range *ranges =
				soundreq_take((unsigned)range_count * sizeof(*ranges));

			soundreq_bind(&definition->pitch_ranges, ranges);
			for (range_index = 0; range_index < range_count; range_index++)
			{
				int permutation_count = soundreq_i32();
				struct sound_pitch_range *range = &ranges[range_index];
				int permutation_index;

				if (permutation_count != range->permutations.count ||
					permutation_count < 0 ||
					permutation_count > MAXIMUM_PERMUTATIONS_PER_PITCH_RANGE)
					soundreq_fail("permutation count");
				if (permutation_count)
				{
					struct sound_permutation *permutations = soundreq_take(
						(unsigned)permutation_count * sizeof(*permutations));

					soundreq_bind(&range->permutations, permutations);
					for (permutation_index = 0;
						permutation_index < permutation_count;
						permutation_index++)
					{
						soundreq_clear_tag_data(&permutations[permutation_index].samples);
						soundreq_clear_tag_data(&permutations[permutation_index].mouth_data);
						soundreq_clear_tag_data(&permutations[permutation_index].subtitle_data);
					}
				}
				else
					soundreq_bind(&range->permutations, NULL);
			}
		}
		else
			soundreq_bind(&definition->pitch_ranges, NULL);
		soundreq_register_tag(SOUND_DEFINITION_TAG, datum, definition);
	}
}

static void soundreq_hex_name(const char *name)
{
	int index;

	for (index = 0; index < 32; index++)
		printf("%02x", (unsigned char)name[index]);
}

static void soundreq_print_records(long owner)
{
	int index;

	if (soundreq_property_count != soundreq_request_count)
		soundreq_fail("properties and queue counts differ");
	for (index = 0; index < soundreq_request_count; index++)
	{
		struct soundreq_request *request = &soundreq_requests[index];
		struct sound_channel_datum *channel = channel_get(request->channel_index);
		struct sound_datum *sound = sound_get(channel->sound_index);
		struct looping_sound_datum *loop = looping_sound_get(sound->source_identifier);

		printf("RECORD channel=%d ce_tag=%ld ce_owner=%ld ce_source=%ld ce_type=%d ce_track=%d ce_range=%d ce_perm=%d ce_pitch=%08x ce_pos=%08x,%08x,%08x plat_gain=%08x plat_pitch=%08x plat_min=%08x plat_max=%08x plat_in=%08x plat_out=%08x plat_outgain=%08x plat_reverb=%08x perm_gain=%08x perm_name=",
			request->channel_index,
			sound->definition_index,
			loop->loop_identifier,
			sound->source_identifier,
			sound->type,
			sound->loop_track_index,
			sound->pitch_range_index,
			sound->permutation_index,
			soundreq_bits(sound->pitch),
			soundreq_bits(sound->source.location.position.x),
			soundreq_bits(sound->source.location.position.y),
			soundreq_bits(sound->source.location.position.z),
			soundreq_bits(request->properties.gain),
			soundreq_bits(request->properties.pitch),
			soundreq_bits(request->properties.minimum_distance),
			soundreq_bits(request->properties.maximum_distance),
			soundreq_bits(request->properties.cone_inside_angle),
			soundreq_bits(request->properties.cone_outside_angle),
			soundreq_bits(request->properties.cone_outside_gain),
			soundreq_bits(request->properties.reverb_attenuation),
			soundreq_bits(request->permutation_gain));
		soundreq_hex_name(request->name);
		printf("\n");
		if (loop->loop_identifier != owner)
			soundreq_fail("owner was not retained on the looping datum");
	}
	printf("PLATFORM_ARGS channel permutation properties\n");
	printf("PLATFORM_OMITS tag owner position\n");
}

static int soundreq_count_sounds(void)
{
	int count = 0;
	long index = data_next_index(sound_data, NONE);

	while (index != NONE)
	{
		count++;
		index = data_next_index(sound_data, index);
	}
	return count;
}

static void soundreq_drive_one(void)
{
	char name[64];
	uint32_t name_length;
	int32_t background;
	int32_t environment;
	int32_t owner;
	int32_t has_environment;
	int32_t has_loop;
	real position[3];
	struct sound_source source;
	int feedback;
	int sound_count_before;

	name_length = soundreq_u32();
	if (name_length >= sizeof(name))
		soundreq_fail("map name");
	soundreq_need(name_length);
	csmemcpy(name, soundreq_cursor, name_length);
	name[name_length] = 0;
	soundreq_cursor += name_length;
	background = soundreq_i32();
	environment = soundreq_i32();
	owner = soundreq_i32();
	position[0] = 0;
	csmemcpy(&position[0], soundreq_cursor, 4);
	soundreq_cursor += 4;
	csmemcpy(&position[1], soundreq_cursor, 4);
	soundreq_cursor += 4;
	csmemcpy(&position[2], soundreq_cursor, 4);
	soundreq_cursor += 4;
	has_environment = soundreq_i32();
	has_loop = soundreq_i32();

	soundreq_prepare_manager();
	sound_initialize();
	if (!sound_is_active())
		soundreq_fail("drive initialize did not activate");
	if (soundreq_initialize_count != 1)
		soundreq_fail("platform initialize was not called");

	printf("MAP %s\n", name);
	printf("background %d\n", background);
	printf("environment %d\n", environment);
	printf("owner %d\n", owner);
	if (has_environment)
	{
		struct sound_environment_definition *definition;

		if (soundreq_u32() != sizeof(*definition))
			soundreq_fail("environment size");
		definition = soundreq_take(sizeof(*definition));
		sound_manager_set_sound_environment(definition);
	}
	if (!has_loop || background == NONE)
	{
		printf("requests 0\n");
		printf("sounds 0\n");
		printf("empty 1\n");
		printf("reason %s\n", background == NONE ? "background-tag-none" : "loop-definition-none");
		printf("feedback 1\n");
		printf("location_calls 0\n");
		printf("listener_calls 0\n");
		printf("obstruction_calls 0\n");
		printf("ENDMAP\n");
		return;
	}

	{
		uint32_t nbytes = soundreq_u32();
		struct looping_sound_definition *definition;
		int track_count;
		int detail_count;
		int sound_count;

		if (nbytes != sizeof(*definition))
			soundreq_fail("looping size");
		definition = soundreq_take(nbytes);
		track_count = soundreq_i32();
		detail_count = soundreq_i32();
		if (track_count != definition->tracks.count || track_count < 0 ||
			track_count > MAXIMUM_TRACKS_PER_LOOPING_SOUND)
			soundreq_fail("track count");
		if (detail_count != definition->details.count || detail_count < 0 ||
			detail_count > MAXIMUM_DETAIL_SOUNDS_PER_LOOPING_SOUND)
			soundreq_fail("detail count");
		if (track_count)
			soundreq_bind(&definition->tracks,
				soundreq_take((unsigned)track_count * sizeof(struct looping_sound_track)));
		else
			soundreq_bind(&definition->tracks, NULL);
		if (detail_count)
			soundreq_bind(&definition->details,
				soundreq_take((unsigned)detail_count * sizeof(struct looping_sound_detail)));
		else
			soundreq_bind(&definition->details, NULL);
		soundreq_register_tag(LOOPING_SOUND_DEFINITION_TAG, background, definition);
		sound_count = soundreq_i32();
		if (sound_count < 0 || sound_count > 32)
			soundreq_fail("sound count");
		soundreq_load_sounds(sound_count);
	}

	csmemset(&source, 0, sizeof(source));
	source.spatialization_mode = _sound_spatialization_mode_none;
	source.scale = 1.f;
	source.gain = 1.f;
	source.location.position.x = position[0];
	source.location.position.y = position[1];
	source.location.position.z = position[2];
	sound_manager_globals.render_time = 0;
	sound_refresh_looping(background, owner, &source,
		_looping_sound_refresh_start, FALSE, 0.f);
	sound_count_before = soundreq_count_sounds();
	{
		int tag_index;

		for (tag_index = 0; tag_index < soundreq_tag_count; tag_index++)
			soundreq_shadow_add(soundreq_tags[tag_index].body,
				soundreq_tags[tag_index].group == LOOPING_SOUND_DEFINITION_TAG ?
					(unsigned)sizeof(struct looping_sound_definition) :
					(unsigned)sizeof(struct sound_definition),
				"definition-header");
	}
	soundreq_shadow_add(&sound_manager_globals.sound_environment,
		sizeof(sound_manager_globals.sound_environment), "environment");
	{
		int tag_index;

		for (tag_index = 0; tag_index < soundreq_tag_count; tag_index++)
		{
			struct looping_sound_definition *definition;

			if (soundreq_tags[tag_index].group != LOOPING_SOUND_DEFINITION_TAG)
				continue;
			definition = soundreq_tags[tag_index].body;
			if (definition->tracks.address && definition->tracks.count)
				soundreq_shadow_add(definition->tracks.address,
					(unsigned)definition->tracks.count * sizeof(struct looping_sound_track),
					"tracks");
			if (definition->details.address && definition->details.count)
				soundreq_shadow_add(definition->details.address,
					(unsigned)definition->details.count * sizeof(struct looping_sound_detail),
					"details");
		}
	}
	{
		int tag_index;

		for (tag_index = 0; tag_index < soundreq_tag_count; tag_index++)
		{
			if (soundreq_tags[tag_index].group != SOUND_DEFINITION_TAG)
				continue;
			{
				struct sound_definition *definition = soundreq_tags[tag_index].body;
				int range_index;

				if (!definition->pitch_ranges.address)
					continue;
				for (range_index = 0; range_index < definition->pitch_ranges.count; range_index++)
				{
					struct sound_pitch_range *range = TAG_BLOCK_GET_ELEMENT(
						&definition->pitch_ranges, range_index, struct sound_pitch_range);

					soundreq_shadow_add(range, sizeof(*range), "pitch-range");
					if (range->permutations.address && range->permutations.count)
						soundreq_shadow_add(range->permutations.address,
							(unsigned)range->permutations.count * sizeof(struct sound_permutation),
							"permutations");
				}
			}
		}
	}
	prioritize_sounds();
	update_channels();
	if (soundreq_request_count)
	{
		real saved = soundreq_requests[0].permutation_gain;

		soundreq_requests[0].permutation_gain = -999.f;
		feedback = soundreq_shadow_check();
		soundreq_requests[0].permutation_gain = saved;
	}
	else
		feedback = soundreq_shadow_check();

	printf("requests %d\n", soundreq_request_count);
	printf("sounds %d\n", sound_count_before);
	printf("empty %d\n", soundreq_request_count == 0);
	if (soundreq_request_count == 0)
		printf("reason %s\n", sound_count_before == 0 ? "no-component-sound" : "no-channel");
	else
		printf("reason queued\n");
	printf("feedback %d\n", feedback);
	printf("poison_isolated %d\n", feedback);
	printf("location_calls %d\n", soundreq_location_count);
	printf("listener_calls %d\n", soundreq_listener_count);
	printf("obstruction_calls %d\n", soundreq_obstruction_calls);
	printf("stereo_calls %u\n", soundreq_stereo_calls);
	printf("stereo_positioned %u\n", soundreq_stereo_positioned_calls);
	printf("stereo_unexpected %u\n", soundreq_stereo_unexpected_args);
	printf("stop_calls %d\n", soundreq_stop_count);
	printf("queue_calls %d\n", soundreq_request_count);
	printf("property_calls %d\n", soundreq_property_count);
	printf("published_bsp %d\n", soundreq_published_bsp);
	printf("collision_depth %d\n", soundreq_collision_depth);
	if (soundreq_request_count)
		soundreq_print_records(owner);
	printf("ENDMAP\n");
	if (!feedback)
		soundreq_fail("CE tag or environment bytes changed across the platform call");
}

static int soundreq_drive_main(const char *path)
{
	FILE *file;
	long length;
	unsigned char *bytes;

	file = fopen(path, "rb");
	if (!file)
		soundreq_fail("open case");
	if (fseek(file, 0, SEEK_END) != 0)
		soundreq_fail("seek case");
	length = ftell(file);
	if (length < 8)
		soundreq_fail("short case");
	rewind(file);
	bytes = malloc((unsigned)length);
	if (!bytes || fread(bytes, 1, (size_t)length, file) != (size_t)length)
		soundreq_fail("read case");
	fclose(file);
	soundreq_cursor = bytes;
	soundreq_end = bytes + length;
	if (soundreq_u32() != 0x31515253u)
		soundreq_fail("case magic");
	{
		int maps = soundreq_i32();
		int index;

		sound_classes_initialize();
		sound_classes_initialize_for_new_map();
		printf("mode drive\n");
		printf("preferences_platform %d\n", 0);
		soundreq_print_contract();
		printf("ISSUE queue-args-lack-tag-owner-position\n");
		for (index = 0; index < maps; index++)
		{
			soundreq_reset_recorder();
			soundreq_drive_one();
		}
	}
	if (soundreq_cursor != soundreq_end)
		soundreq_fail("case trailing bytes");
	return 0;
}

#ifdef HALO_PS2
int main(void)
{
	struct sound_preferences *preferences;

	printf("mode ps2\n");
	read_sound_preferences(&preferences);
	printf("preferences_platform %d\n", preferences->platform);
	soundreq_reset_recorder();
	soundreq_cache_new_calls = 0;
	sound_initialize();
	printf("sound_is_active %d\n", sound_is_active() ? 1 : 0);
	printf("cache_new %u\n", soundreq_cache_new_calls);
	printf("recorder_initialize %d\n", soundreq_initialize_count);
	printf("recorder_queue %d\n", soundreq_request_count);
	printf("recorder_properties %d\n", soundreq_property_count);
	printf("recorder_location %d\n", soundreq_location_count);
	printf("recorder_listener %d\n", soundreq_listener_count);
	printf("platform_definition_null %d\n",
		sound_manager_globals.platform_definition == NULL);
	soundreq_print_contract();
	printf("ISSUE queue-args-lack-tag-owner-position\n");
	/* The PS2 build selects the silent recorder platform (slot 1). The Xbox
	 * DirectSound stub must never be entered: its counters stay zero. */
	if (preferences->platform != 1 || !sound_is_active() ||
		soundreq_initialize_count || soundreq_request_count ||
		soundreq_location_count || soundreq_listener_count ||
		platform_definitions[1] == NULL ||
		sound_manager_globals.platform_definition != platform_definitions[1] ||
		soundreq_cache_new_calls != 1)
		return 1;
	return 0;
}
#else
int main(int argc, char **argv)
{
	if (argc == 2 && argv[1][0] == '-' && argv[1][1] == '-' &&
		argv[1][2] == 's')
	{
		soundreq_print_schema();
		return 0;
	}
	if (argc == 3 && argv[1][0] == '-' && argv[1][1] == '-' &&
		argv[1][2] == 'd')
		return soundreq_drive_main(argv[2]);
	fprintf(stderr, "usage: soundreq-drive --schema | --drive cases\n");
	return 2;
}
#endif
