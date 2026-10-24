/* Optional parent machine entry for the CE gameplay closure.
 * The ordinary halo-ps2 viewer remains the default build target. */
#include "core/mem.h"
#include "platform/pad.h"
#include "platform/video.h"
#include "stream/hcu_memory_bind.h"
#include "stream/hcu_map_service.h"
#include "stream/hcu_file_bridge.h"
#include "stream/hcu_render_snapshot.h"
#include "stream/hcu_storage_boot.h"

#include <kernel.h>
#include <dma.h>
#include <draw.h>
#include <graph.h>
#include <gs_psm.h>
#include <packet2.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#ifdef HALO_PS2_M2_ANIMATION_TRACE
#include "ps2_animation_trace.h"
#endif

#ifndef HALO_HCU_TAG_CACHE_BYTES
#define HALO_HCU_TAG_CACHE_BYTES 2097152u
#endif
#ifndef HALO_HCU_ASSET_ROOT
#define HALO_HCU_ASSET_ROOT "host:/"
#endif

static hcu_map_service s_map_service;
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
static mem_layout_v2_t *s_step8_candidate_layout;
#endif

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

#ifdef HALO_PS2_M3_RENDER_CLEAR_TEST
/*
 * Diagnostic-only GS bring-up. The snapshot owns the start of dma_commands;
 * place a small, aligned GIF packet after that published wire buffer so this
 * test neither allocates from the EE heap nor aliases CE snapshot data.
 */
static int hcu_m3_render_clear_test(void *dma_storage, size_t dma_bytes)
{
	video_t video;
	packet2_t packet;
	uintptr_t packet_address;
	uintptr_t storage_start = (uintptr_t)dma_storage;
	size_t snapshot_bytes = hcu_render_snapshot_dma_storage_required();
	const size_t packet_bytes = 64u * sizeof(qword_t);
	const uint32_t fb_words = (VIDEO_WIDTH * VIDEO_HEIGHT) / 2u;
	const uint32_t z_words = VIDEO_WIDTH * VIDEO_HEIGHT;
	const uint32_t tex_words = 2048u;
	uint32_t fb0, fb1, zbuf, texture;

	if (!dma_storage || snapshot_bytes > dma_bytes ||
		dma_bytes - snapshot_bytes < packet_bytes + 63u)
		return -1;
	packet_address = (storage_start + snapshot_bytes + 63u) & ~(uintptr_t)63u;
	if (packet_address < storage_start ||
		packet_address > storage_start + dma_bytes ||
		packet_bytes > storage_start + dma_bytes - packet_address)
		return -1;
	/* packet2_create_from() allocates its descriptor and packet2_free() frees
	 * the borrowed base. Initialize the public descriptor over arena storage
	 * directly to preserve the no-post-boot-allocation contract. */
	memset(&packet, 0, sizeof packet);
	packet.max_qwords_count = 64;
	packet.type = P2_TYPE_NORMAL;
	packet.mode = P2_MODE_NORMAL;
	packet.base = packet.next = (qword_t *)packet_address;
	memset(packet.base, 0, packet_bytes);

	dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
	dma_channel_fast_waits(DMA_CHANNEL_GIF);
	video_init(&video);
	fb0 = video.fb[0].address;
	fb1 = video.fb[1].address;
	zbuf = video.z.address;
	texture = video.tex_base;
	if (fb0 == UINT32_MAX || fb1 == UINT32_MAX || zbuf == UINT32_MAX ||
		texture == UINT32_MAX || fb0 > VIDEO_VRAM_WORDS ||
		fb_words > VIDEO_VRAM_WORDS - fb0 || fb1 > VIDEO_VRAM_WORDS ||
		fb_words > VIDEO_VRAM_WORDS - fb1 || zbuf > VIDEO_VRAM_WORDS ||
		z_words > VIDEO_VRAM_WORDS - zbuf || texture > VIDEO_VRAM_WORDS ||
		tex_words > VIDEO_VRAM_WORDS - texture ||
		(fb0 < fb1 + fb_words && fb1 < fb0 + fb_words) ||
		(fb0 < zbuf + z_words && zbuf < fb0 + fb_words) ||
		(fb1 < zbuf + z_words && zbuf < fb1 + fb_words) ||
		(texture < fb0 + fb_words && fb0 < texture + tex_words) ||
		(texture < fb1 + fb_words && fb1 < texture + tex_words) ||
		(texture < zbuf + z_words && zbuf < texture + tex_words)) {
		printf("HALO_PS2_FAIL m3 GS eDRAM ranges invalid or overlapping\n");
		return -1;
	}
	video_add_setup_env(&video, &packet);
	video_add_clear(&video, &packet, 24, 72, 120);
	packet2_update(&packet, draw_finish(packet.next));
	if ((uintptr_t)packet.next < packet_address ||
		((uintptr_t)packet.next - packet_address) % sizeof(qword_t) != 0u ||
		((uintptr_t)packet.next - packet_address) / sizeof(qword_t) == 0u ||
		((uintptr_t)packet.next - packet_address) / sizeof(qword_t) >
			packet.max_qwords_count) {
		printf("HALO_PS2_FAIL m3 GIF clear packet exceeded its arena slice\n");
		return -1;
	}
	dma_channel_send_packet2(&packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast();
	draw_wait_finish();
	video_present(&video);
	printf("HALO_PS2_LOCAL m3-render-clear-presented color=24,72,120 frames=%u\n",
		(unsigned)video.frames);
	return 0;
}
#endif

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
		printf("HALO_PS2_LOCAL arena name=%s base=0x%x cap=%u used=%u high=%u "
			"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
			s_region_names[i], (unsigned)starts[i], (unsigned)region->cap,
			(unsigned)region->used, (unsigned)region->high,
			(unsigned)region->failed_allocations,
			(unsigned)region->reset_count,
			(unsigned)region->release_count,
			(unsigned)region->invalid_releases);
	}
	return 0;
}

#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
/* Stock MP corpus candidate: the max aligned CTAG and Sidewinder BSP spans
 * need 6,470,832 bytes. Borrow 179,376 bytes from texture_cache; total owner
 * storage is unchanged and the end canary remains in the original regions. */
static int hcu_step8_mp_candidate_recarve(mem_layout_v2_t *layout)
{
	arena_t *bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	arena_t *texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	const size_t map_bytes = 6470832u;
	const size_t texture_bytes = 4014928u;
	uint8_t *combined_end;
	if (!bsp || !texture || !bsp->base || !texture->base ||
		bsp->cap != 6291456u || texture->cap != 4194304u ||
		((uintptr_t)bsp->base & 15u) ||
		texture->base != layout->guards[2] + MEM_LAYOUT_V2_GUARD_BYTES ||
		map_bytes + texture_bytes != 10485760u)
		return -1;
	combined_end = bsp->base + map_bytes + texture_bytes;
	if (combined_end > texture->base + texture->cap - MEM_LAYOUT_V2_GUARD_BYTES ||
		((uintptr_t)(bsp->base + map_bytes) & 15u))
		return -1;
	bsp->cap = map_bytes;
	texture->base = bsp->base + map_bytes;
	texture->cap = texture_bytes;
	/* The original post-BSP canary sat inside the candidate BSP span. Move it
	 * to the candidate combined owner's end and retain the old pointers for
	 * other guarded regions. Duplicate pointer checks are intentional. */
	layout->guards[2] = combined_end;
	layout->guards[3] = combined_end;
	memset(combined_end, layout->guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
	printf("HALO_PS2_LOCAL step8-mp-candidate-layout tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760 base=0x%x texture-base=0x%x end=0x%x\n",
		(unsigned)ee_physical_address(bsp->base),
		(unsigned)ee_physical_address(texture->base),
		(unsigned)ee_physical_address(combined_end));
	return 0;
}

int halo_ps2_step8_mp_candidate_guards_intact(void)
{
	return s_step8_candidate_layout &&
		mem_layout_v2_guards_intact(s_step8_candidate_layout);
}
#endif

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
	arena_t render_section_scratch;
	arena_t map_owner_storage;
	arena_t *frame_scratch;
	arena_t *dma_commands;
	arena_t *streaming;
	mem_layout_v2_t layout;
	size_t resident_static_bytes, backing_bytes, snapshot_bytes;
	int snapshot_bound = 0;
	int result;
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	arena_t *resident_gameplay;
	struct ps2_animation_trace_event *animation_trace_storage;
	struct ps2_animation_trace_context *animation_context_storage;
#endif
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
		resident_static_bytes, 0xA5u) != 0
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
		|| hcu_step8_mp_candidate_recarve(&layout) != 0
#endif
		||
		hcu_memory_bind_parent_v2(&layout, (size_t)HALO_HCU_TAG_CACHE_BYTES) != 0)
	{
		printf("[err] cannot bind CE fixed memory regions\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	/* Opt-in diagnostic storage is charged to resident_gameplay only after CE's
	 * game-state and claims allocations. Never borrow frame scratch, streaming,
	 * dynamic simulation, or the uncommitted reserve. */
	resident_gameplay = mem_layout_v2_get(&layout,
		MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	animation_trace_storage = resident_gameplay ? arena_alloc(
		resident_gameplay,
		PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_trace_storage), 16) : NULL;
	animation_context_storage = resident_gameplay ? arena_alloc(
		resident_gameplay,
		PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_context_storage), 16) : NULL;
	if (!animation_trace_storage || !animation_context_storage ||
		!ps2_animation_trace_bind(animation_trace_storage,
			PS2_ANIMATION_TRACE_CAPACITY) ||
		!ps2_animation_trace_bind_contexts(animation_context_storage,
			PS2_ANIMATION_TRACE_CAPACITY)) {
		printf("[err] cannot bind budgeted M2 animation trace buffer\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL animation-trace-bound events=0x%x contexts=0x%x count=%u event-bytes=%u context-bytes=%u resident-used=%u\n",
		(unsigned)ee_physical_address(animation_trace_storage),
		(unsigned)ee_physical_address(animation_context_storage),
		(unsigned)PS2_ANIMATION_TRACE_CAPACITY,
		(unsigned)(PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_trace_storage)),
		(unsigned)(PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_context_storage)),
		(unsigned)resident_gameplay->used);
#endif
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
	frame_scratch = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_FRAME_SCRATCH);
	dma_commands = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_DMA_COMMANDS);
	streaming = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_STREAMING);
	snapshot_bytes = hcu_render_snapshot_storage_required();
	if (!frame_scratch || !dma_commands || !streaming ||
		snapshot_bytes > frame_scratch->cap || streaming->cap < 1572864u ||
		hcu_render_snapshot_bind(frame_scratch->base,
			frame_scratch->cap, dma_commands->base, dma_commands->cap) != 0)
	{
		printf("[err] cannot bind bounded CE render snapshot storage\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	snapshot_bound = 1;
	/* Keep simulation snapshot storage in frame_scratch. Map owners and decode
	 * scratch receive disjoint bounded slices of streaming so section loads do
	 * not consume render-time frame scratch. */
	arena_init(&map_owner_storage, "streaming_map_owner",
		streaming->base, 1048576u);
	arena_init(&render_section_scratch, "streaming_section_scratch",
		streaming->base + 1048576u, 524288u);
	printf("HALO_PS2_LOCAL render-snapshot-bound banks=%u streaming-map-cap=%u section-scratch-base=0x%x section-scratch-cap=%u dma=%u\n",
		(unsigned)snapshot_bytes,
		(unsigned)map_owner_storage.cap,
		(unsigned)ee_physical_address(render_section_scratch.base),
		(unsigned)render_section_scratch.cap,
		(unsigned)hcu_render_snapshot_dma_storage_required());
	if (hcu_map_service_init_with_arenas(&s_map_service, &layout,
		HALO_HCU_ASSET_ROOT, &map_owner_storage, &render_section_scratch) != 0)
	{
		printf("[err] cannot initialize HCU map service at %s\n",
			HALO_HCU_ASSET_ROOT);
		hcu_render_snapshot_unbind();
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
			hcu_render_snapshot_unbind();
			physical_memory_free();
			__real_free(backing);
			return 1;
		}
		printf("HALO_PS2_LOCAL asset-probe-ready root=%s bytes=%u\n",
			HALO_HCU_ASSET_ROOT, (unsigned)asset_bytes);
	}
	printf("HALO_PS2_LOCAL memory-and-input-ready (cache=%u bytes; bootstrap only)\n",
		(unsigned)HALO_HCU_TAG_CACHE_BYTES);
#ifdef HALO_PS2_M3_RENDER_CLEAR_TEST
	{
		const arena_t *dma_commands = mem_layout_v2_get(&layout,
			MEM_LAYOUT_V2_DMA_COMMANDS);
		if (!dma_commands || hcu_m3_render_clear_test(dma_commands->base,
			dma_commands->cap) != 0) {
			printf("HALO_PS2_FAIL m3 renderer clear diagnostic could not initialize/present\n");
			hcu_map_service_shutdown(&s_map_service);
			if (snapshot_bound)
				hcu_render_snapshot_unbind();
			physical_memory_free();
			__real_free(backing);
			return 1;
		}
	}
#endif
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
	s_step8_candidate_layout = &layout;
#endif
	result = halo_shell_main();
	if (report_and_validate_regions(&layout,
		ee_physical_address(backing),
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK) != 0 ||
		!mem_layout_v2_guards_intact(&layout)) {
		printf("HALO_PS2_FAIL budget-v2 boundary canary corrupted\n");
		result = 1;
	}
	printf("HALO_PS2_LOCAL arena name=%s cap=%u used=%u high=%u "
		"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
		map_owner_storage.name, (unsigned)map_owner_storage.cap,
		(unsigned)map_owner_storage.used, (unsigned)map_owner_storage.high,
		(unsigned)map_owner_storage.failed_allocations,
		(unsigned)map_owner_storage.reset_count,
		(unsigned)map_owner_storage.release_count,
		(unsigned)map_owner_storage.invalid_releases);
	printf("HALO_PS2_LOCAL arena name=%s cap=%u used=%u high=%u "
		"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
		render_section_scratch.name, (unsigned)render_section_scratch.cap,
		(unsigned)render_section_scratch.used,
		(unsigned)render_section_scratch.high,
		(unsigned)render_section_scratch.failed_allocations,
		(unsigned)render_section_scratch.reset_count,
		(unsigned)render_section_scratch.release_count,
		(unsigned)render_section_scratch.invalid_releases);
	hcu_map_service_shutdown(&s_map_service);
	if (snapshot_bound)
		hcu_render_snapshot_unbind();
	physical_memory_free();
	__real_free(backing);
	return result;
}
