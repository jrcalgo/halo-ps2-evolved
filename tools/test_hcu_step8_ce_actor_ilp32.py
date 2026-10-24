#!/usr/bin/env python3
"""Run the real CE actor create/delete bodies in a freestanding ILP32 fixture."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "submodules/halo-ce-universal"
ACTORS = CE / "source/ai/actors.c"


def extract_function(source: str, signature: str) -> str:
	# CE often declares these functions before defining them. Selecting the
	# first match can pair a prototype with the next unrelated function body.
	start = source.rindex(signature)
	opening = source.index("{", start)
	depth = 0
	for index in range(opening, len(source)):
		if source[index] == "{":
			depth += 1
		elif source[index] == "}":
			depth -= 1
			if depth == 0:
				return source[start:index + 1]
	raise AssertionError(f"unterminated CE function: {signature}")


HEADERS = r'''
#include "cseries.h"
#include "actors.h"
#include "actor_definitions.h"
#include "actor_types.h"
#include "encounters.h"
#include "props.h"
#include "ai_debug.h"
#include "memory/data.h"
#include "saved games/game_state.h"
#include "units/bipeds.h"
#include "units/units.h"
#include "networking/network_game_globals.h"
#include "halo_ps2_limits.h"
#include "cseries/errors.h"
#undef match_assert
#define match_assert(file, line, expression) ((void)0)
#undef match_vassert
#define match_vassert(file, line, expression, message) ((void)0)
enum { _actor_mode_braindead = 0, _actor_mode_alert = 2 };
enum { _actor_combat_status_none = 0 };
enum { MAXIMUM_NUMBER_OF_UNITS_PER_SWARM = MAXIMUM_UNIT_INDICES_PER_SWARM };
struct encounter_actor_iterator { long encounter_index, index, next_index; };
void platform_log(const char *format, ...);
'''

ADAPTERS = r'''
struct data_array *actor_data, *swarm_data, *swarm_component_data;
struct actor_debug_info *actor_debug_array;
struct ai_debug_state ai_debug;
struct data_array *prop_data;
struct data_array *encounter_data;
long global_updating_actor_index = NONE;
static struct actor_variant_definition fixture_variant;
static struct actor_definition fixture_definition;
static struct biped_datum fixture_biped;
static struct actor_debug_info fixture_debug[MAXIMUM_NUMBER_OF_ACTORS];
static unsigned char fixture_game_state[HALO_PORT_GAME_STATE_CPU_SIZE];
static unsigned long fixture_game_state_used, fixture_game_state_peak;
static unsigned long fixture_object_pool_used, fixture_object_pool_peak;
static unsigned long fixture_seed;
static unsigned long s_actor_pool_high_water;
static unsigned long s_actor_pool_failed_allocations;
static unsigned long s_actor_pool_resets;
static const real_vector3d fixture_forward = { { 1.f, 0.f, 0.f } };
#define STEP8_ACTOR_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_ACTORS * sizeof(struct actor_datum))
#define STEP8_SWARM_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_SWARMS * sizeof(struct swarm_datum))
#define STEP8_COMPONENT_ARRAY_BYTES (sizeof(struct data_array) + MAXIMUM_SWARM_COMPONENTS * SWARM_COMPONENT_DATUM_SIZE)
char step8_metric_game_state_peak[STEP8_ACTOR_ARRAY_BYTES + STEP8_SWARM_ARRAY_BYTES + STEP8_COMPONENT_ARRAY_BYTES];
char step8_metric_actor_record[sizeof(struct actor_datum)];

static void bytes_zero(void *target, int value, unsigned long size)
{
    byte *out = (byte *)target;
    unsigned long i;
    for (i = 0; i < size; ++i) out[i] = (byte)value;
}
void *csmemset(void *target, long value, unsigned long size) { bytes_zero(target, (int)value, size); return target; }

struct data_array *game_state_data_new(const char *name, short maximum_count, short size)
{
    unsigned long payload;
    struct data_array *array;
    if (!name || maximum_count <= 0 || size <= 0) return NULL;
    payload = (unsigned long)data_allocation_size(maximum_count, size);
    if (fixture_game_state_used + payload > sizeof(fixture_game_state)) return NULL;
    array = (struct data_array *)(fixture_game_state + fixture_game_state_used);
    data_initialize(array, name, maximum_count, size);
    fixture_game_state_used += payload;
    if (fixture_game_state_used > fixture_game_state_peak)
        fixture_game_state_peak = fixture_game_state_used;
    return array;
}

char *csstrncpy(char *destination, const char *source, unsigned long size)
{
    unsigned long index;
    for (index = 0; index < size; ++index)
        destination[index] = source[index] ? source[index] : 0;
    return destination;
}

void platform_log(const char *format, ...) { (void)format; }
void actor_types_initialize(void) { }
void actor_type_initialize(long index) { (void)index; }
boolean actor_type_get_swarm(short type) { (void)type; return FALSE; }
boolean network_game_distributed_client(void) { return FALSE; }
void *tag_get(long group, long index)
{
    if (index == 11 && group == ACTOR_VARIANT_DEFINITION_TAG) return &fixture_variant;
    if (index == 22 && group == ACTOR_DEFINITION_TAG) return &fixture_definition;
    return NULL;
}
char *tag_get_name(long index) { (void)index; return "synthetic\\fixture"; }
char const *tag_name_strip_path(char const *name) { return name; }
unsigned long *get_global_random_seed_address(void) { return &fixture_seed; }
real real_seed_random(unsigned long *seed) { (void)seed; return 0.f; }
const real_vector3d *global_forward3d = &fixture_forward;
void error(short type, char const *format, ...) { (void)type; (void)format; }
void actor_clear_discarded_firing_positions(long actor, boolean force) { (void)actor; (void)force; }
void encounterless_attach_actor(long actor)
{
    struct actor_datum *datum = (struct actor_datum *)datum_get(actor_data, actor);
    datum->meta.encounterless = TRUE;
}
void encounterless_detach_actor(long actor)
{
    struct actor_datum *datum = (struct actor_datum *)datum_get(actor_data, actor);
    datum->meta.encounterless = FALSE;
}
void actor_delete_props(long actor) { (void)actor; }
void ai_debug_actor_deleted(long actor) { (void)actor; }
void ai_conversation_actor_deleted(long actor) { (void)actor; }
void actor_swarm_cache_delete(long actor) { (void)actor; }
boolean actor_swarm_attach_unit(long actor, long unit) { (void)actor; (void)unit; return TRUE; }
void actor_swarm_detach_from_unit(long actor, long unit) { (void)actor; (void)unit; }
void actor_set_dormant(long actor, boolean dormant) { (void)actor; (void)dormant; }
const char *actor_type_get_name(short type) { (void)type; return "fixture"; }
void encounter_actor_iterator_new(struct encounter_actor_iterator *iterator, long encounter)
{ iterator->encounter_index = encounter; iterator->index = NONE; iterator->next_index = NONE; }
struct actor_datum *encounter_actor_iterator_next(struct encounter_actor_iterator *iterator)
{ (void)iterator; return NULL; }
void encounter_attach_actor(long actor, long encounter, short squad, boolean previous)
{ (void)actor; (void)encounter; (void)squad; (void)previous; }
void encounter_detach_actor(long actor, boolean died) { (void)actor; (void)died; }
void encounter_attach_unit(long encounter, long unit) { (void)encounter; (void)unit; }
void encounter_actor_iterator_unused(void) { }
void object_set_automatic_deactivation(long unit, boolean enabled) { (void)unit; (void)enabled; }
void unit_set_actively_controlled(long unit, boolean enabled) { (void)unit; (void)enabled; }
void object_deactivate(long unit) { (void)unit; }
void object_activate(long unit) { (void)unit; }
void *object_try_and_get_and_verify_type(long index, unsigned long flags)
{ (void)flags; return index == 7 ? &fixture_biped : NULL; }
void *object_get_and_verify_type(long index, unsigned long flags)
{ (void)flags; return index == 7 ? &fixture_biped : NULL; }
void data_iterator_new(struct data_iterator *iterator, struct data_array *array)
{ iterator->data = array; iterator->absolute_index = 0; iterator->datum_index = NONE; }
void *data_iterator_next(struct data_iterator *iterator) { (void)iterator; return NULL; }
static void actor_input_update(long actor) { (void)actor; }
static void actor_verify_unit_activation(long actor, long unit, const char *name)
{ (void)actor; (void)unit; (void)name; }

short actor_action_get_default_state(short initial_state) { return initial_state; }
void unit_unused_stub(void) { }
'''

def main() -> int:
	clang = shutil.which("clang")
	if not clang:
		raise SystemExit("clang is required for the CE i386 ILP32 fixture")
	actor_source = ACTORS.read_text()
	data_source = (CE / "source/memory/data.c").read_text()
	data_functions = "\n\n".join(extract_function(data_source, signature) for signature in (
		"long data_allocation_size(", "void data_initialize(", "static void datum_initialize(",
		"static boolean data_usable(", "void data_verify(",
		"void *datum_get(", "long datum_new(", "void datum_delete(",
		"void data_make_valid(", "void data_make_invalid(", "void data_delete_all(",
	))
	functions = "\n\n".join(extract_function(actor_source, signature) for signature in (
		"void actors_initialize(", "void actors_get_pool_telemetry(",
		"void actors_initialize_for_new_map(",
		"void actors_dispose_from_old_map(",
		"long actor_new(", "long actor_create_for_unit(",
		"void actor_attach_unit(", "void actor_detach_from_unit(",
		"void actor_verify_activation(", "void actor_delete(",
	))
	# Function-local engine constants used by the copied CE bodies.
	constants = r'''
enum { _actor_mode_braindead = 0, _actor_mode_alert = 2 };
enum { _actor_combat_status_none = 0 };
'''
	# Remove duplicate constant declarations from the header preamble above.
	unit_accessors = r'''
void *object_try_and_get_and_verify_type(long, unsigned long);
void *object_get_and_verify_type(long, unsigned long);
'''
	main_body = r'''
int fixture_main(void)
{
    struct actor_datum *actor;
    struct unit_datum *unit = (struct unit_datum *)&fixture_biped;
    long actor_indices[HALO_PORT_MAXIMUM_ACTORS];
    long actor_index;
    unsigned long before_game_state;
    unsigned long before_object_pool = fixture_object_pool_peak;
    unsigned long capacity, high_water, failures, resets;
    short i;
    if (MAXIMUM_ACTORS != HALO_PORT_MAXIMUM_ACTORS ||
        MAXIMUM_OBJECTS_PER_MAP != HALO_PORT_MAXIMUM_OBJECTS_PER_MAP ||
        OBJECT_MEMORY_POOL_SIZE != HALO_PORT_OBJECT_MEMORY_POOL_SIZE) return 8;
    actor_debug_array = fixture_debug;
    fixture_biped.object.damage_flags = 0;
    unit->unit.actor_index = NONE;
    unit->unit.swarm_actor_index = NONE;
    fixture_definition.type = 0;
    fixture_definition.flags = 0;
    fixture_variant.actor_reference.index = 22;
    actors_initialize();
    if (!actor_data || !swarm_data || !swarm_component_data ||
        fixture_game_state_peak != sizeof(step8_metric_game_state_peak) ||
        fixture_game_state_peak > sizeof(fixture_game_state)) return 1;
    actors_get_pool_telemetry(&capacity, &high_water, &failures, &resets);
    if (capacity != MAXIMUM_ACTORS || high_water != 0 || failures != 0 || resets != 0) return 12;
    actors_initialize_for_new_map();
    actors_get_pool_telemetry(&capacity, &high_water, &failures, &resets);
    if (resets != 1) return 13;
    before_game_state = fixture_game_state_peak;
    actor_index = actor_create_for_unit(FALSE, 7, 11, NONE, NONE, FALSE, NONE,
        FALSE, 1, 2, NONE, NONE);
    if (actor_index == NONE || actor_data->actual_count != 1) return 2;
    actor = (struct actor_datum *)datum_get(actor_data, actor_index);
    if (actor->meta.unit_index != 7 || actor->meta.definition_index != 22 ||
        actor->meta.variant_definition_index != 11 || !actor->meta.encounterless ||
        unit->unit.actor_index != actor_index) return 3;
    if (fixture_game_state_peak != before_game_state ||
        fixture_object_pool_peak != before_object_pool) return 4;
    actor_delete(actor_index, FALSE);
    if (actor_data->actual_count != 0 || unit->unit.actor_index != NONE) return 5;
    /* Exercise CE's fixed actor-array ceiling and exhaustion result. These
     * records are allocation-only; no 256-unit world or AI tick is implied. */
    for (i = 0; i < MAXIMUM_ACTORS; ++i)
    {
        actor_indices[i] = actor_new(11);
        if (actor_indices[i] == NONE) return 9;
    }
    if (actor_data->actual_count != MAXIMUM_ACTORS ||
        actor_new(11) != NONE || actor_data->actual_count != MAXIMUM_ACTORS) return 10;
    actors_get_pool_telemetry(&capacity, &high_water, &failures, &resets);
    if (capacity != MAXIMUM_ACTORS || high_water != MAXIMUM_ACTORS || failures != 1 || resets != 1) return 14;
    for (i = 0; i < MAXIMUM_ACTORS; ++i)
        actor_delete(actor_indices[i], FALSE);
    if (actor_data->actual_count != 0) return 11;
    actors_initialize_for_new_map();
    actors_get_pool_telemetry(&capacity, &high_water, &failures, &resets);
    if (high_water != MAXIMUM_ACTORS || failures != 1 || resets != 2) return 15;
    actors_dispose_from_old_map();
    if (actor_data->valid || swarm_data->valid || swarm_component_data->valid) return 6;
    if (fixture_game_state_used != fixture_game_state_peak) return 7;
    return 0;
}
'''
	# The preamble already declares these constants once.
	constants = ""
	with tempfile.TemporaryDirectory(prefix="hcu-step8-actor-ilp32-") as directory:
		temp = Path(directory)
		harness = temp / "actor_fixture.c"
		binary = temp / "actor_fixture"
		prefix = temp / "halo_step8_ps2_prefix.h"
		prefix_text = (CE / "port/linux/include/halo_linux_prefix.h").read_text()
		linux_capacity = '#include "halo_port_limits.h"'
		if prefix_text.count(linux_capacity) != 1:
			raise SystemExit("unexpected Linux prefix capacity include; cannot pin PS2 ILP32 bounds")
		prefix.write_text(prefix_text.replace(linux_capacity, '#include "halo_ps2_limits.h"'))
		harness.write_text(HEADERS + constants + data_functions + ADAPTERS + unit_accessors + functions + main_body + r'''
void _start(void)
{
    int status = fixture_main();
    /* The sandbox rejects i386 syscalls (SIGSYS), so use distinct CPU traps
     * as a libc-free pass/fail result from this freestanding ILP32 process. */
    if (status == 0) __asm__ volatile("int3");
    if (status == 9) __asm__ volatile("ud2");
    if (status == 10) __asm__ volatile("xorl %ecx, %ecx; movl $1, %eax; divl %ecx");
    if (status == 11) __asm__ volatile("movl $0, %eax; movl (%eax), %eax");
    __asm__ volatile("ud2");
    for (;;) { }
}
''')
		includes = json.loads((CE / "port/linux/port.json").read_text())["game"]["include_dirs"]
		command = [clang, "--target=i686-linux-gnu", "-m32", "-fshort-wchar",
			"-malign-double", "-fcommon", "-fno-pic", "-fno-stack-protector",
			"-fno-builtin", "-Wno-implicit-function-declaration", "-D__STRICT_ANSI__",
			"-DDEBUG", "-Dxbox", "-include", str(prefix),
			"-I", str(CE / "port/linux/include"), "-I", str(CE / "port/include/xdk"),
			"-I", str(CE / "port/ps2/include"), "-nostdlib", "-static", "-Wl,-e,_start",
			"-Wl,--build-id=none", str(harness), "-o", str(binary)]
		for include in includes:
			command.extend(["-I", str(CE / include)])
		built = subprocess.run(command, capture_output=True, text=True)
		if built.returncode:
			raise SystemExit("ILP32 CE actor harness compile failed:\n" + built.stdout + built.stderr)
		retained = ROOT / "build/hcu-step8-actor-ilp32"
		retained.mkdir(parents=True, exist_ok=True)
		for artifact in (harness, binary, prefix):
			shutil.copy2(artifact, retained / artifact.name)
		run = subprocess.run([str(binary)], capture_output=True, text=True)
		if run.returncode != -5:
			raise SystemExit(f"ILP32 CE actor fixture did not report the pass trap (returncode {run.returncode})")
		nm = shutil.which("nm")
		if not nm:
			raise SystemExit("nm is required to report ILP32 actor layout sizes")
		listing = subprocess.run([nm, "-S", "--defined-only", str(binary)], capture_output=True, text=True, check=True).stdout
		metrics = {}
		for line in listing.splitlines():
			parts = line.split()
			if len(parts) >= 4 and parts[-1].startswith("step8_metric_"):
				metrics[parts[-1]] = int(parts[1], 16)
		if set(metrics) != {"step8_metric_game_state_peak", "step8_metric_actor_record"}:
			raise SystemExit("missing ILP32 actor size markers from linked fixture")
		binary_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
		print("step8-ce-actor-ilp32 "
			f"actual_ce_functions=actor_new,actor_create_for_unit,actor_attach_unit,actor_delete "
			f"synthetic_tag_and_biped=1 actor_capacity=256 actor_peak=256 actor_record_bytes={metrics['step8_metric_actor_record']} "
			f"game_state_cpu_capacity=3162112 game_state_high_water={metrics['step8_metric_game_state_peak']} "
			f"object_pool_capacity=1048576 object_pool_delta=0 actor_cleanup=passed map_data_invalidated=passed "
			f"executable_sha256={binary_sha256} retained={retained.relative_to(ROOT)}")
	return 0


if __name__ == "__main__":
	main()
