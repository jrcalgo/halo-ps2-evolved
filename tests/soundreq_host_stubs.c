/* Host symbols the real CE sound units reference. This is not a PS2
 * sound backend and it does not implement SPU2. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>

static void *(*soundreq_libc_malloc)(size_t) = malloc;
static void (*soundreq_libc_free)(void *) = free;
static void *(*soundreq_libc_realloc)(void *, size_t) = realloc;
static void *(*soundreq_libc_memset)(void *, int, size_t) = memset;
static void *(*soundreq_libc_memcpy)(void *, const void *, size_t) = memcpy;
static void *(*soundreq_libc_memmove)(void *, const void *, size_t) = memmove;
static int (*soundreq_libc_memcmp)(const void *, const void *, size_t) = memcmp;
static char *(*soundreq_libc_strncpy)(char *, const char *, size_t) = strncpy;
static char *(*soundreq_libc_strcpy)(char *, const char *) = strcpy;
static int (*soundreq_libc_strcmp)(const char *, const char *) = strcmp;
static int (*soundreq_libc_strncmp)(const char *, const char *, size_t) = strncmp;
static size_t (*soundreq_libc_strlen)(const char *) = strlen;
static char *(*soundreq_libc_strcat)(char *, const char *) = strcat;
static char *(*soundreq_libc_strncat)(char *, const char *, size_t) = strncat;
static char *(*soundreq_libc_strtok)(char *, const char *) = strtok;
static int (*soundreq_libc_vsnprintf)(char *, size_t, const char *, va_list) = vsnprintf;

#include "cseries.h"
#include "math/real_math.h"
#include "tag_files/tag_groups.h"
#include "cache/sound_cache.h"
#include "sound/game_sound.h"
#include "sound/sound_definitions.h"
#include "cseries/profile.h"
#include "camera/observer.h"
#include "render/render_debug.h"
#include "effects/player_effects.h"

boolean profile_global_enable;

char temporary[256];
unsigned soundreq_obstruction_calls;
unsigned soundreq_cache_new_calls;
unsigned soundreq_cache_request_calls;
unsigned soundreq_stereo_calls;
unsigned soundreq_stereo_positioned_calls;
unsigned soundreq_stereo_unexpected_args;

void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *pointer;

	(void)file;
	(void)line;
	pointer = soundreq_libc_malloc(size ? size : 1u);
	if (pointer && clear)
		soundreq_libc_memset(pointer, 0, size);
	return pointer;
}

void debug_free(void *pointer, const char *file, long line)
{
	(void)file;
	(void)line;
	soundreq_libc_free(pointer);
}

void *debug_realloc(void *pointer, unsigned int size, const char *file, long line)
{
	(void)file;
	(void)line;
	return soundreq_libc_realloc(pointer, size ? size : 1u);
}

void *csmemset(void *buffer, long c, unsigned long size)
{
	return soundreq_libc_memset(buffer, (int)c, size);
}

void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	return soundreq_libc_memcpy(destination, source, size);
}

void *csmemmove(void *destination, const void *source, unsigned long size)
{
	return soundreq_libc_memmove(destination, source, size);
}

long csmemcmp(const void *a, const void *b, unsigned long size)
{
	return soundreq_libc_memcmp(a, b, size);
}

char *csstrncpy(char *s1, const char *s2, unsigned long size)
{
	return soundreq_libc_strncpy(s1, s2, size);
}

char *csstrcpy(char *s1, const char *s2)
{
	return soundreq_libc_strcpy(s1, s2);
}

long csstrcmp(const char *a, const char *b)
{
	return soundreq_libc_strcmp(a, b);
}

long csstrncmp(const char *a, const char *b, unsigned long size)
{
	return soundreq_libc_strncmp(a, b, size);
}

unsigned long csstrlen(const char *s)
{
	return (unsigned long)soundreq_libc_strlen(s);
}

char *csstrcat(char *s1, const char *s2)
{
	return soundreq_libc_strcat(s1, s2);
}

char *csstrncat(char *s1, const char *s2, unsigned long size)
{
	return soundreq_libc_strncat(s1, s2, size);
}

char *csstrtok(char *s, const char *delim)
{
	return soundreq_libc_strtok(s, delim);
}

char *csprintf(char *buffer, char *format, ...)
{
	va_list args;

	va_start(args, format);
	soundreq_libc_vsnprintf(buffer, 256, format, args);
	va_end(args);
	return buffer;
}

void display_assert(char *information, char *file, long line, boolean fatal)
{
	fprintf(stderr, "ce-assert %s:%ld %s\n",
		file ? file : "?", line, information ? information : "");
	if (fatal)
		exit(1);
}

void system_exit(long code)
{
	exit((int)code);
}

void platform_log(const char *format, ...)
{
	va_list args;

	va_start(args, format);
	vfprintf(stderr, format, args);
	fputc('\n', stderr);
	va_end(args);
}

void error(short priority, const char *format, ...)
{
	va_list args;

	(void)priority;
	fprintf(stderr, "ce-error ");
	va_start(args, format);
	vfprintf(stderr, format, args);
	va_end(args);
	fputc('\n', stderr);
}

double config_real(const char *name)
{
	(void)name;
	return 1.0;
}

unsigned long config_changes(void)
{
	return 0;
}

void *game_state_malloc(const char *name, const char *type, long size)
{
	(void)name;
	(void)type;
	return debug_malloc((unsigned int)size, TRUE, __FILE__, __LINE__);
}

boolean game_engine_running(void)
{
	return FALSE;
}

unsigned long system_milliseconds(void)
{
	return 0;
}

unsigned long system_seconds(void)
{
	return 0;
}

void sound_cache_new(void)
{
	soundreq_cache_new_calls++;
}

void sound_cache_delete(void) {}
void sound_cache_idle(void) {}
void sound_cache_flush(void) {}
void sound_cache_close(void) {}
void sound_cache_open(void) {}

void sound_cache_sound_finished(struct sound_permutation *sound)
{
	(void)sound;
}

boolean _sound_cache_sound_request(struct sound_permutation *sound,
	boolean block, boolean load, boolean reference)
{
	(void)block;
	(void)load;
	(void)reference;
	soundreq_cache_request_calls++;
	return sound != NULL;
}

void halo_ps2_sound_playback_note(const void *sound, int event,
	int owner_kind, unsigned owner_datum, int has_position,
	float x, float y, float z, int priority, float gain, float pitch,
	unsigned game_time)
{
	(void)sound; (void)event; (void)owner_kind; (void)owner_datum;
	(void)has_position; (void)x; (void)y; (void)z; (void)priority;
	(void)gain; (void)pitch; (void)game_time;
}

void dsound_port_set_channel_stereo_position(short virtual_channel_index,
	boolean positioned, real pan, real distance, real minimum_distance,
	real distance_fade, real occlusion, real obstruction,
	boolean attenuate_direct_path)
{
	(void)virtual_channel_index;
	(void)positioned;
	(void)pan;
	(void)distance;
	(void)minimum_distance;
	(void)distance_fade;
	(void)occlusion;
	(void)obstruction;
	soundreq_stereo_calls++;
	if (positioned)
		soundreq_stereo_positioned_calls++;
	if (positioned || pan != 0.f || distance != 0.f || minimum_distance != 0.f ||
		distance_fade != 1.f || occlusion != 0.f || obstruction != 0.f ||
		attenuate_direct_path)
		soundreq_stereo_unexpected_args++;
}

void compute_sound_obstruction(short local_player_index,
	struct sound_source *source, real distance)
{
	(void)local_player_index;
	(void)source;
	(void)distance;
	soundreq_obstruction_calls++;
}

void game_sound_set_mouth_aperture(long object_index, real mouth_aperture)
{
	(void)object_index;
	(void)mouth_aperture;
	fprintf(stderr, "unexpected mouth aperture\n");
	exit(1);
}

boolean track_object_impulse_sound(long object_index, void const *attachment_data,
	struct sound_source *source)
{
	(void)object_index;
	(void)attachment_data;
	(void)source;
	return FALSE;
}

void player_effect_continuous_refresh(long definition_index,
	real_point3d const *position)
{
	(void)definition_index;
	(void)position;
}

char *tag_get_name(long tag_index)
{
	(void)tag_index;
	return "";
}

void *tag_block_get_element_with_size(struct tag_block const *block,
	long index, long element_size)
{
	fprintf(stderr, "tag block slow path count=%ld index=%ld size=%ld\n",
		block ? block->count : -1, index, element_size);
	exit(1);
	return NULL;
}

static union real_argb_color soundreq_color;
const union real_argb_color *global_real_argb_white = &soundreq_color;
const union real_argb_color *global_real_argb_cyan = &soundreq_color;
const union real_argb_color *global_real_argb_blue = &soundreq_color;
const union real_argb_color *global_real_argb_yellow = &soundreq_color;
const union real_argb_color *global_real_argb_red = &soundreq_color;

void render_debug_sphere(boolean immediate, real_point3d const *center,
	real radius, real_argb_color const *color)
{
	(void)immediate;
	(void)center;
	(void)radius;
	(void)color;
}

void render_debug_string_at_point(boolean immediate, real_point3d const *point,
	const char *string, real_argb_color const *color)
{
	(void)immediate;
	(void)point;
	(void)string;
	(void)color;
}

void render_debug_string(boolean immediate, const char *string)
{
	(void)immediate;
	(void)string;
}

void profile_enter_private(struct profile_section *section)
{
	(void)section;
}

void profile_exit_private(struct profile_section *section)
{
	(void)section;
}

real_point3d *matrix4x3_inverse_transform_point(real_matrix4x3 const *matrix,
	real_point3d const *point, real_point3d *result)
{
	(void)matrix;
	(void)point;
	fprintf(stderr, "unexpected inverse point\n");
	exit(1);
	return result;
}

real_vector3d *matrix4x3_inverse_transform_vector(real_matrix4x3 const *matrix,
	real_vector3d const *vector, real_vector3d *result)
{
	(void)matrix;
	(void)vector;
	fprintf(stderr, "unexpected inverse vector\n");
	exit(1);
	return result;
}

real_vector3d *matrix4x3_inverse_transform_normal(real_matrix4x3 const *matrix,
	real_vector3d const *normal, real_vector3d *result)
{
	(void)matrix;
	(void)normal;
	fprintf(stderr, "unexpected inverse normal\n");
	exit(1);
	return result;
}

boolean players_are_all_dead(void)
{
	return FALSE;
}

boolean game_in_progress(void)
{
	return FALSE;
}

long game_time_get(void)
{
	return 0;
}

long local_player_get_player_index(short local_player_index)
{
	(void)local_player_index;
	return NONE;
}

static struct observer_result soundreq_camera;

struct observer_result const *observer_get_camera(short local_player_index)
{
	(void)local_player_index;
	return &soundreq_camera;
}

boolean scenario_location_underwater(const struct location *location,
	const real_point3d *position, short *optional_weather_palette_index)
{
	(void)location;
	(void)position;
	(void)optional_weather_palette_index;
	return FALSE;
}

struct game_globals *scenario_get_game_globals(void)
{
	return NULL;
}

static real_point3d soundreq_origin;
static real_vector3d soundreq_zero;
static real_vector3d soundreq_forward = {.n = {1.f, 0.f, 0.f}};
static real_vector3d soundreq_up = {.n = {0.f, 0.f, 1.f}};
const real_point3d *global_origin3d = &soundreq_origin;
const real_vector3d *global_zero_vector3d = &soundreq_zero;
const real_vector3d *global_forward3d = &soundreq_forward;
const real_vector3d *global_up3d = &soundreq_up;

long halo_cseries_strnlen(const char *string, long n)
{
	long i;

	if (!string)
		return 0;
	for (i = 0; i < n && string[i]; i++)
		;
	return i;
}
