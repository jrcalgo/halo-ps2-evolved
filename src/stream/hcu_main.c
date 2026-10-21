/* Optional parent machine entry for the CE gameplay closure.
 * The ordinary halo-ps2 viewer remains the default build target. */
#include "core/mem.h"
#include "platform/pad.h"
#include "platform/video.h"
#include "stream/hcu_memory_bind.h"
#include "stream/hcu_map_service.h"
#include "stream/hcu_file_bridge.h"
#include "stream/hcu_storage_boot.h"

#include <kernel.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#ifndef HALO_HCU_TAG_CACHE_BYTES
#define HALO_HCU_TAG_CACHE_BYTES 2097152u
#endif
#ifndef HALO_HCU_ASSET_ROOT
#define HALO_HCU_ASSET_ROOT "host:/"
#endif

static hcu_map_service s_map_service;

/* The host link/guest placement gate budgets this exact worst-case padding. */
_Static_assert(MEM_LAYOUT_V2_GUARDED_SLACK == 310u,
	"update the M1 physical placement probe when guard layout changes");

static const char *const s_region_names[MEM_LAYOUT_V2_REGION_COUNT] = {
	"resident_gameplay", "current_bsp", "texture_cache",
	"dynamic_simulation", "dma_commands", "streaming", "checkpoint",
	"audio", "frame_scratch"
};

/* The machine owns the target mode; CE's CPU camera uses these dimensions
 * without taking ownership of GS setup or drawing. */
long halo_screen_width(void) { return VIDEO_WIDTH; }
long halo_ps2_display_height(void) { return VIDEO_HEIGHT; }

int ps2_abi_check(void);
void physical_memory_allocate(void);
int physical_memory_ready(void);
void physical_memory_free(void);
int halo_shell_main(void);
void *__real_malloc(unsigned long size);
void __real_free(void *ptr);
extern char _fbss;
extern char _end;
extern char _ftext;

static uintptr_t ee_physical_address(const void *pointer)
{
	uintptr_t address = (uintptr_t)pointer;
	if (address >= 0x80000000u && address < 0xc0000000u)
		return address & 0x1fffffffu;
	return address;
}

static int report_and_validate_regions(const mem_layout_v2_t *layout,
	uintptr_t boot_start, size_t boot_bytes)
{
	uintptr_t starts[MEM_LAYOUT_V2_REGION_COUNT];
	uintptr_t ends[MEM_LAYOUT_V2_REGION_COUNT];
	uintptr_t boot_end;
	int i, j;

	if (boot_bytes > UINTPTR_MAX - boot_start)
		return -1;
	boot_end = boot_start + boot_bytes;
	for (i = 0; i < MEM_LAYOUT_V2_REGION_COUNT; i++) {
		const arena_t *region = &layout->regions[i];
		uintptr_t base = ee_physical_address(region->base);

		if (!region->base || region->cap == 0 || region->used > region->cap ||
			region->high > region->cap || region->cap > UINTPTR_MAX - base)
			return -1;
		starts[i] = base;
		ends[i] = base + region->cap;
		if (starts[i] < boot_start || ends[i] > boot_end ||
			ends[i] > 0x01a00000u)
			return -1;
		for (j = 0; j < i; j++) {
			if (starts[i] < ends[j] && starts[j] < ends[i])
				return -1;
		}
		printf("HALO_PS2_LOCAL arena name=%s base=0x%x cap=%u used=%u high=%u\n",
			s_region_names[i], (unsigned)starts[i], (unsigned)region->cap,
			(unsigned)region->used, (unsigned)region->high);
	}
	return 0;
}

static int report_kernel_stack(void)
{
	ee_thread_status_t status;
	int thread_id = GetThreadId();
	uintptr_t stack_start, stack_end;
	if (thread_id < 0 || ReferThreadStatus(thread_id, &status) <= 0 ||
		!status.stack || status.stack_size <= 0)
		return -1;
	stack_start = ee_physical_address(status.stack);
	if ((uintptr_t)status.stack_size > UINTPTR_MAX - stack_start)
		return -1;
	stack_end = stack_start + (uintptr_t)status.stack_size;
	/* The v2 reserve is [26 MiB, 31.5 MiB); the remaining top 512 KiB
	 * plus low 1 MiB are the 1.5 MiB kernel/system reservation. */
	if (stack_start < 0x01f80000u || stack_end > 0x02000000u)
		return -1;
	printf("HALO_PS2_LOCAL kernel-stack base=0x%x size=%u end=0x%x\n",
		(unsigned)stack_start, (unsigned)status.stack_size,
		(unsigned)stack_end);
	printf("HALO_PS2_LOCAL kernel-reservation low=0x0 low_bytes=1048576 "
		"high=0x1f80000 high_bytes=524288 reserve=0x1a00000 "
		"reserve_bytes=5767168\n");
	return 0;
}

int main(int argc, char **argv)
{
	void *backing;
	arena_t boot;
	mem_layout_v2_t layout;
	size_t resident_static_bytes, backing_bytes;
	int result;
	(void)argc;
	(void)argv;

	setbuf(stdout, NULL);
	printf("HALO_PS2_LOCAL machine entry\n");
	if (!ps2_abi_check()) {
		printf("HALO_PS2_FAIL CE ABI runtime smoke failed\n");
		return 1;
	}
	/* CRT clears this NOBITS span before main. Charge it to resident_gameplay
	 * so the one boot allocation covers only the rest of the v2 layout. */
	if ((uintptr_t)&_end < (uintptr_t)&_fbss) {
		printf("[err] invalid ELF NOBITS bounds\n");
		return 1;
	}
	resident_static_bytes = (size_t)((uintptr_t)&_end - (uintptr_t)&_fbss);
	if (resident_static_bytes > 6815744u) {
		printf("[err] ELF NOBITS exceeds resident_gameplay\n");
		return 1;
	}
	backing_bytes = MEM_LAYOUT_V2_BYTES - resident_static_bytes;
	/* Alignment slack is required because arena_init receives an
	 * allocator-owned address. The link/runtime ledger includes this slack. */
	/* Bypass HCU's post-boot malloc arena wrapper for the single machine-owned
	 * backing allocation. The linked HCU profile supplies --wrap=malloc/free. */
	backing = __real_malloc((unsigned long)(backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK));
	if (!backing)
	{
		printf("[err] cannot allocate budget-v2 backing\n");
		return 1;
	}
	/* EE RAM below 1 MiB and above 31.5 MiB belongs to system/kernel;
	 * 26–31.5 MiB is the untouched v2 reserve. The full boot allocation,
	 * including allocator metadata between _end and the returned pointer,
	 * must finish before that reserve. */
	if (ee_physical_address(&_ftext) < 0x00100000u ||
		ee_physical_address(&_fbss) > 0x00300000u ||
		ee_physical_address(backing) < ee_physical_address(&_end) ||
		ee_physical_address(backing) > 0x01a00000u ||
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK >
			0x01a00000u - ee_physical_address(backing))
	{
		printf("[err] ELF/boot backing exceeds EE fixed budget\n");
		__real_free(backing);
		return 1;
	}
	if (report_kernel_stack() != 0) {
		printf("[err] cannot prove kernel stack is inside system_kernel reservation\n");
		__real_free(backing);
		return 1;
	}
	arena_init(&boot, "boot", backing,
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK);
	if (mem_layout_v2_init_charged_guarded(&layout, &boot,
		resident_static_bytes, 0xA5u) != 0 ||
		hcu_memory_bind_parent_v2(&layout, (size_t)HALO_HCU_TAG_CACHE_BYTES) != 0)
	{
		printf("[err] cannot bind CE fixed memory regions\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	if (report_and_validate_regions(&layout,
		ee_physical_address(backing),
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK) != 0 ||
		!mem_layout_v2_guards_intact(&layout)) {
		printf("[err] budget-v2 intervals or boundary canaries invalid\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL memory-layout bss=%u backing=%u guard_slack=%u\n",
		(unsigned)resident_static_bytes, (unsigned)backing_bytes,
		(unsigned)MEM_LAYOUT_V2_GUARDED_SLACK);
	printf("HALO_PS2_LOCAL memory-physical elf_end=0x%x boot=0x%x boot_end=0x%x reserve=0x1a00000 allocator_gap=%u\n",
		(unsigned)ee_physical_address(&_end),
		(unsigned)ee_physical_address(backing),
		(unsigned)(ee_physical_address(backing) + backing_bytes +
			MEM_LAYOUT_V2_GUARDED_SLACK),
		(unsigned)(ee_physical_address(backing) -
			ee_physical_address(&_end)));
	physical_memory_allocate();
	if (!physical_memory_ready())
	{
		printf("[err] required CE fixed memory regions are unavailable\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	if (!mem_layout_v2_guards_intact(&layout)) {
		printf("[err] budget-v2 boundary canary corrupted during CE bind\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL memory-ready canaries=%u\n",
		(unsigned)(MEM_LAYOUT_V2_REGION_COUNT + 1));
	if (!pad_init())
	{
		printf("[err] PS2 pad service initialization failed\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL pad-ready\n");
	/* pad_init starts SIF RPC. Reuse OPL's IOP modules when present; never
	 * reset the IOP because that can destroy the launcher's storage driver. */
	printf("HALO_PS2_LOCAL storage-boot-begin\n");
	if (hcu_storage_boot_init() != 0)
	{
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL storage-boot-ready\n");
	if (hcu_map_service_init(&s_map_service, &layout,
		HALO_HCU_ASSET_ROOT) != 0)
	{
		printf("[err] cannot initialize HCU map service at %s\n",
			HALO_HCU_ASSET_ROOT);
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	{
		unsigned long asset_bytes = 0;
		const char *failed_stage = NULL;
		if (!hcu_file_bridge_probe("D:\\maps\\ui.map", &asset_bytes,
			&failed_stage)) {
			printf("[err] asset root %s failed read-only maps/ui.map probe at %s\n",
				HALO_HCU_ASSET_ROOT,
				failed_stage ? failed_stage : "unknown");
			hcu_map_service_shutdown(&s_map_service);
			physical_memory_free();
			__real_free(backing);
			return 1;
		}
		printf("HALO_PS2_LOCAL asset-probe-ready root=%s bytes=%u\n",
			HALO_HCU_ASSET_ROOT, (unsigned)asset_bytes);
	}
	printf("HALO_PS2_LOCAL memory-and-input-ready (cache=%u bytes; bootstrap only)\n",
		(unsigned)HALO_HCU_TAG_CACHE_BYTES);
	result = halo_shell_main();
	if (!mem_layout_v2_guards_intact(&layout)) {
		printf("HALO_PS2_FAIL budget-v2 boundary canary corrupted\n");
		result = 1;
	}
	hcu_map_service_shutdown(&s_map_service);
	physical_memory_free();
	__real_free(backing);
	return result;
}
