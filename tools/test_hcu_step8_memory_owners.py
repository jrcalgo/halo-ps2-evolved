#!/usr/bin/env python3
"""Host exercise of CE game-state and fixed object-pool diagnostic hooks."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def extract_function(source: str, signature: str) -> str:
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
	raise AssertionError(f"unterminated source function {signature}")


def main() -> int:
	gs_source = (HCU / "source/saved games/game_state.c").read_text()
	obj_source = (HCU / "source/objects/objects.c").read_text()
	fragments = [
		extract_function(gs_source, "static void ps2_step8_game_state_diagnostics_begin("),
		extract_function(gs_source, "static void ps2_step8_game_state_diagnostics_end("),
		extract_function(gs_source, "void *game_state_malloc("),
		extract_function(gs_source, "int ps2_step8_game_state_memory_diagnostics("),
		extract_function(obj_source, "static void ps2_step8_object_pool_diagnostics_begin("),
		extract_function(obj_source, "static void ps2_step8_object_pool_diagnostics_end("),
		extract_function(obj_source, "static void ps2_step8_object_pool_record("),
		extract_function(obj_source, "static long object_header_new("),
		extract_function(obj_source, "int ps2_step8_object_pool_memory_diagnostics("),
	]
	for owner_function, signature in (
		("object_header_new", "static long object_header_new("),
		("object_header_block_allocate", "boolean object_header_block_allocate("),
	):
		body = extract_function(obj_source, signature)
		if "ps2_step8_object_pool_record(TRUE)" not in body or "ps2_step8_object_pool_record(FALSE)" not in body:
			raise SystemExit(f"{owner_function} is not wired to both pool outcomes")

	harness = r'''
#include <limits.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define HALO_PS2 1
#define HALO_PS2_STEP8_MEMORY_DIAGNOSTIC 1
#define GAME_STATE_CPU_SIZE 64
#define GAME_STATE_GPU_SIZE 16
#define HALO_PORT_GAME_STATE_BASE_ADDRESS 0u
#define NONE (-1)
#define TRUE 1
#define FALSE 0
#define match_assert(file, line, expression) ((void)0)
typedef unsigned char byte;
typedef int boolean;
struct game_state_header { unsigned long checksum; };
static unsigned char game_state_arena[GAME_STATE_CPU_SIZE];
static struct {
    void *base_address;
    long cpu_allocation_size;
    long gpu_allocation_size;
    long allocation_size_checksum;
    boolean locked, saved_game_valid;
    long revert_time;
    struct game_state_header *header;
} game_state_globals = { 0 };
static unsigned long ps2_step8_game_state_high_water;
static unsigned long ps2_step8_game_state_failures;
static int ps2_step8_game_state_diagnostics_active;
struct ps2_step8_memory_owner_diagnostics {
    unsigned long capacity_bytes, used_bytes, high_water_bytes, failed_allocations;
};
static struct memory_pool { long size, used; } object_pool_storage;
static struct memory_pool *object_memory_pool;
static unsigned long ps2_step8_object_pool_high_water;
static unsigned long ps2_step8_object_pool_failures;
static int ps2_step8_object_pool_diagnostics_active;
static unsigned char object_pool_arena[64];
struct data_array { int unused; };
struct object_header_datum { void *datum; short data_size; };
static struct object_header_datum test_header;
static unsigned long dynamic_simulation_used = 0x1234u;

static void game_state_allocation_record(const char *name, const char *type, long size, boolean gpu)
{ (void)name; (void)type; (void)size; (void)gpu; }
static void crc_checksum_buffer(unsigned long *checksum, void *data, unsigned long size)
{ (void)checksum; (void)data; (void)size; }
static void *datum_get(struct data_array *data, long index)
{ (void)data; (void)index; return &test_header; }
static long datum_new(struct data_array *data) { (void)data; return 0; }
static long datum_new_at_index(struct data_array *data, long index)
{ (void)data; return index; }
static void datum_delete(struct data_array *data, long index)
{ (void)data; (void)index; }
static long memory_pool_get_used_size(struct memory_pool *pool) { return pool->used; }
static boolean memory_pool_block_allocate(struct memory_pool *pool, void **reference, long size)
{
    long allocation = size + 16;
    if (pool->used + allocation > pool->size) return FALSE;
    *reference = object_pool_arena + pool->used;
    pool->used += allocation;
    return TRUE;
}
static void *game_state_allocate_buffer(unsigned long address, unsigned long cpu, unsigned long gpu)
{ (void)address; (void)cpu; (void)gpu; return game_state_arena; }
static void game_state_create_or_open_file(void) { }
static void game_state_free_buffer(void) { }
static void game_state_close_file(void) { }
static void crc_new(long *checksum) { *checksum = 0; }
'''
	harness += "\n".join(fragments)
	harness += r'''
int main(void)
{
    struct ps2_step8_memory_owner_diagnostics gs, objects;
    struct data_array data = { 0 };
    long first, second, exhausted;
    unsigned long initial_game_state_peak;

    ps2_step8_game_state_diagnostics_begin();
    game_state_globals.base_address = game_state_arena;
    if (!game_state_malloc("fixture", NULL, 64)) return 1;
    if (!ps2_step8_game_state_memory_diagnostics(&gs) ||
        gs.capacity_bytes != 64 || gs.used_bytes != 64 ||
        gs.high_water_bytes != 64 || gs.failed_allocations != 0) return 2;
    initial_game_state_peak = gs.high_water_bytes;
    if (game_state_malloc("exhausted", NULL, 4) != NULL) return 3;
    if (!ps2_step8_game_state_memory_diagnostics(&gs) ||
        gs.used_bytes != 64 || gs.high_water_bytes != 64 ||
        gs.failed_allocations != 1) return 4;
    ps2_step8_game_state_diagnostics_end();
    if (ps2_step8_game_state_memory_diagnostics(&gs)) return 5;
    game_state_globals.cpu_allocation_size = 0;
    ps2_step8_game_state_diagnostics_begin();
    if (!ps2_step8_game_state_memory_diagnostics(&gs) ||
        gs.used_bytes != 0 || gs.high_water_bytes != 0 ||
        gs.failed_allocations != 0) return 13;
    if (!game_state_malloc("reset", NULL, 8) ||
        !ps2_step8_game_state_memory_diagnostics(&gs) ||
        gs.used_bytes != 8 || gs.high_water_bytes != 8 ||
        gs.failed_allocations != 0) return 14;
    ps2_step8_game_state_diagnostics_end();
    if (ps2_step8_game_state_memory_diagnostics(&gs)) return 15;

    object_pool_storage.size = 64;
    object_pool_storage.used = 0;
    object_memory_pool = &object_pool_storage;
    ps2_step8_object_pool_diagnostics_begin();
    first = object_header_new(&data, NONE, 16);
    second = object_header_new(&data, NONE, 16);
    exhausted = object_header_new(&data, NONE, 16);
    if (first != 0 || second != 0 || exhausted != NONE) return 6;
    if (!ps2_step8_object_pool_memory_diagnostics(&objects) ||
        objects.capacity_bytes != 64 || objects.used_bytes != 64 ||
        objects.high_water_bytes != 64 || objects.failed_allocations != 1) return 7;
    if (initial_game_state_peak + objects.high_water_bytes != 128) return 8;
    if (dynamic_simulation_used != 0x1234u) return 9;

    object_pool_storage.used = 0;
    ps2_step8_object_pool_diagnostics_begin();
    if (!ps2_step8_object_pool_memory_diagnostics(&objects) ||
        objects.used_bytes != 0 || objects.high_water_bytes != 0 ||
        objects.failed_allocations != 0) return 10;
    ps2_step8_object_pool_diagnostics_end();
    if (ps2_step8_object_pool_memory_diagnostics(&objects)) return 11;
    if (dynamic_simulation_used != 0x1234u) return 12;
    puts("step8-owner-diagnostics game_state=64/64 game_state_fail=1 object_pool=64/64 object_pool_fail=1 nested_owner=separate dynamic_simulation=unchanged reset=passed");
    return 0;
}
'''
	with tempfile.TemporaryDirectory(prefix="hcu-step8-owner-diag-") as temp:
		cfile = Path(temp) / "owner-diagnostics.c"
		binary = Path(temp) / "owner-diagnostics"
		cfile.write_text(harness)
		built = subprocess.run(
			["cc", "-std=gnu99", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
			 "-Wno-unused-function", str(cfile), "-o", str(binary)],
			capture_output=True, text=True)
		if built.returncode:
			raise SystemExit("host compile failed:\n" + built.stdout + built.stderr)
		run = subprocess.run([str(binary)], capture_output=True, text=True)
		if run.returncode:
			raise SystemExit(f"owner diagnostic failed ({run.returncode}):\n{run.stdout}{run.stderr}")
		print(run.stdout, end="")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
