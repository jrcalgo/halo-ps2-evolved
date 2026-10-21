#include "stream/hcu_storage_boot.h"

#include "stream/file.h"

#define NEWLIB_PORT_AWARE
#include <fileXio.h>
#include <delaythread.h>
#include <kernel.h>
#include <loadfile.h>
#include <sifrpc.h>
#include <sbv_patches.h>
#include <stdint.h>
#include <stdio.h>

#ifdef HALO_PS2_VERBOSE_BOOT
#define HCU_TRACE(...) printf(__VA_ARGS__)
#else
#define HCU_TRACE(...) ((void)0)
#endif

/* These IRX images are embedded from the active PS2SDK installation by the
 * HCU gameplay build. Loading is conditional so OPL's existing IOP services
 * and storage stack are preserved. Names are the IRX_ID strings from the
 * pinned PS2SDK iomanX.c and fileXio_iop.c. */
extern const unsigned char halo_iomanx_irx_start[];
extern const uint32_t halo_iomanx_irx_size;
extern const unsigned char halo_filexio_irx_start[];
extern const uint32_t halo_filexio_irx_size;

#define HCU_FILEXIO_BIND_POLLS 100
#define HCU_FILEXIO_BIND_DELAY_US 10000
#define HCU_MAX_IOP_MODULE_ID 0xFFFF

/* IOP Loadcore stores module indices in a 16-bit field. PCSX2's HLE
 * SearchModuleByName has been observed returning 0x40800000 for a missing
 * module; accepting any positive integer mistakes that sentinel for a live
 * IOMANX instance and makes the subsequent FILEXIO load fail. */
static int valid_module_id(int module_id)
{
	return module_id > 0 && module_id <= HCU_MAX_IOP_MODULE_ID;
}

/* PS2SDK's blocking fileXioInit can wait forever if the IOP server never
 * registers. Probe asynchronously first so a bad module/service state is a
 * bounded startup error instead of a frozen machine. */
static int filexio_server_ready(int *bind_result_out)
{
	static SifRpcClientData_t probe;
	int poll, result;
	result = sceSifBindRpc(&probe, FILEXIO_IRX, SIF_RPC_M_NOWAIT);
	if (bind_result_out) *bind_result_out = result;
	if (result < 0) return result;
	for (poll = 0; poll < HCU_FILEXIO_BIND_POLLS; ++poll) {
		if (probe.server) return 1;
		DelayThread(HCU_FILEXIO_BIND_DELAY_US);
	}
	return 0;
}

static int ensure_module(const char *name, const char *legacy_name,
	const unsigned char *image, size_t image_size)
{
	int id, module_start_result = 0, legacy_id;
	HCU_TRACE("HALO_PS2_LOCAL storage-search %s\n", name);
	id = SifSearchModuleByName(name);
	HCU_TRACE("HALO_PS2_LOCAL storage-search-done %s id=%d\n", name, id);
	/* PS2SDK's SearchModuleByName returns a positive module ID on success.
	 * The value 0 is not a valid loaded module ID (the IOP implementation uses
	 * it as the empty/not-found sentinel before returning its error code), and
	 * accepting it can skip loading an RPC server that fileXioInit then waits
	 * for forever in sceSifBindRpc. */
	if (valid_module_id(id)) {
		printf("HALO_PS2_LOCAL storage-module-reused name=%s id=%d\n", name, id);
		return 0;
	}
	/* Some IOMANX builds retain the legacy IRX_ID namespace. */
	if (legacy_name) {
		HCU_TRACE("HALO_PS2_LOCAL storage-search-legacy %s\n", legacy_name);
		legacy_id = SifSearchModuleByName(legacy_name);
		if (valid_module_id(legacy_id)) {
			printf("HALO_PS2_LOCAL storage-module-reused name=%s id=%d\n",
				legacy_name, legacy_id);
			return 0;
		}
	}
	if (!image || image_size == 0 || image_size > UINT32_MAX) return -1;
	HCU_TRACE("HALO_PS2_LOCAL storage-load-begin %s bytes=%u\n", name,
		(unsigned)image_size);
	id = SifExecModuleBuffer((void *)image, (u32)image_size, 0, NULL,
		&module_start_result);
	printf("HALO_PS2_LOCAL storage-module-loaded name=%s id=%d start=%d\n",
		name, id, module_start_result);
	HCU_TRACE("HALO_PS2_LOCAL storage-load-result %s id=%d start=%d\n",
		name, id, module_start_result);
	if (id <= 0 || module_start_result != 0)
		return -1;
	HCU_TRACE("HALO_PS2_LOCAL storage-load-done %s\n", name);
	/* The SDK contract says this positive ID means the module was loaded and
	 * its _start result was returned through module_start_result. The search
	 * RPC is not reliable in the PCSX2 HLE path (it reports 0 for this module),
	 * so do not reject a successful load based on that secondary lookup. */
	return 0;
}

int hcu_storage_boot_init(void)
{
	int lmb_patch_result, bind_result, server_result;
	/* Reuse an OPL/launcher-provided RPC server before touching its IOP state. */
	printf("HALO_PS2_LOCAL storage-filexio-bind-probe\n");
	server_result = filexio_server_ready(&bind_result);
	printf("HALO_PS2_LOCAL storage-filexio-bind-result phase=initial status=%d rpc=%d\n",
		server_result, bind_result);
	if (server_result > 0) {
		printf("HALO_PS2_LOCAL storage-filexio-existing-server\n");
		if (file_reader_filexio_init() != 0) {
			printf("[err] FILEXIO client initialization failed\n");
			return -1;
		}
		printf("HALO_PS2_LOCAL storage-filexio-rpc-ready\n");
		return 0;
	}
	/* PS2SDK's FileXio sample installs these no-reset IOP loadfile patches
	 * before SifExecModuleBuffer. The LMB patch's return 1 means the expected
	 * ROM pattern was not found (some launchers already patch/replace it); only
	 * a negative result is an actual patch-service failure. */
	lmb_patch_result = sbv_patch_enable_lmb();
	if (lmb_patch_result < 0 || sbv_patch_disable_prefix_check() != 0) {
		printf("[err] cannot prepare IOP module loading (LMB=%d)\n",
			lmb_patch_result);
		return -1;
	}
	if (ensure_module("IO/File_Manager", "IOX/File_Manager",
		halo_iomanx_irx_start,
		(size_t)halo_iomanx_irx_size) != 0) {
		printf("[err] IOMANX unavailable; preserving current IOP state\n");
		return -1;
	}
	if (ensure_module("IOX/File_Manager_Rpc", NULL,
		halo_filexio_irx_start,
		(size_t)halo_filexio_irx_size) != 0) {
		printf("[err] FILEXIO unavailable; preserving current IOP state\n");
		return -1;
	}
	printf("HALO_PS2_LOCAL storage-filexio-bind-probe-after-load\n");
	server_result = filexio_server_ready(&bind_result);
	printf("HALO_PS2_LOCAL storage-filexio-bind-result phase=post-load status=%d rpc=%d\n",
		server_result, bind_result);
	if (server_result <= 0) {
		printf("[err] FILEXIO RPC server did not bind within 1 second (status=%d rpc=%d)\n",
			server_result, bind_result);
		return -1;
	}
	printf("HALO_PS2_LOCAL storage-filexio-rpc-begin\n");
	if (file_reader_filexio_init() != 0) {
		printf("[err] FILEXIO RPC initialization failed\n");
		return -1;
	}
	printf("HALO_PS2_LOCAL storage-filexio-rpc-ready\n");
	return 0;
}
