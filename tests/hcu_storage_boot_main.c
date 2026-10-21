#include "stream/hcu_storage_boot.h"

#include <assert.h>
#include <fileXio.h>
#include <sifrpc.h>
#include <stdint.h>
#include <string.h>

const unsigned char halo_iomanx_irx_start[16] = { 1 };
const unsigned char halo_filexio_irx_start[24] = { 2 };
const uint32_t halo_iomanx_irx_size = 16;
const uint32_t halo_filexio_irx_size = 24;

static int have_iomanx, have_legacy_iomanx, have_filexio;
static int zero_search_result;
static int invalid_positive_search_result;
static int fail_iomanx, fail_filexio, fail_init;
static int filexio_server_ready, init_calls, exec_count, bind_calls, delay_calls;
static int lmb_patch_result, fail_prefix_patch, lmb_patch_calls, prefix_patch_calls;
static char exec_names[4][32];

int sbv_patch_enable_lmb(void)
{
	lmb_patch_calls++;
	return lmb_patch_result;
}

int sbv_patch_disable_prefix_check(void)
{
	prefix_patch_calls++;
	return fail_prefix_patch ? -1 : 0;
}

int sceSifBindRpc(SifRpcClientData_t *client, int server_id, int mode)
{
	assert(server_id == FILEXIO_IRX && mode == SIF_RPC_M_NOWAIT);
	bind_calls++;
	client->server = filexio_server_ready ? (void *)1 : NULL;
	return 0;
}

int DelayThread(int delay_us)
{
	assert(delay_us == 10000);
	delay_calls++;
	return 0;
}

int SifSearchModuleByName(const char *name)
{
	if (strcmp(name, "IO/File_Manager") == 0) return have_iomanx ? 1 : invalid_positive_search_result ? 0x40800000 : zero_search_result ? 0 : -1;
	if (strcmp(name, "IOX/File_Manager") == 0) return have_legacy_iomanx ? 5 : invalid_positive_search_result ? 0x40800000 : zero_search_result ? 0 : -1;
	if (strcmp(name, "IOX/File_Manager_Rpc") == 0) return have_filexio ? 2 : invalid_positive_search_result ? 0x40800000 : zero_search_result ? 0 : -1;
	return -1;
}

int SifExecModuleBuffer(void *ptr, uint32_t size, uint32_t arg_len,
	const char *args, int *mod_res)
{
	(void)arg_len; (void)args; (void)mod_res;
	assert(exec_count < 4);
	if (ptr == (void *)halo_iomanx_irx_start) {
		assert(size == halo_iomanx_irx_size);
		strcpy(exec_names[exec_count++], "iomanX");
		if (fail_iomanx) return -1;
		have_iomanx = 1;
		return 3;
	}
	assert(ptr == (void *)halo_filexio_irx_start);
	assert(size == halo_filexio_irx_size);
	strcpy(exec_names[exec_count++], "fileXio");
	if (fail_filexio) return -1;
	have_filexio = 1;
	filexio_server_ready = 1;
	return 4;
}

int file_reader_filexio_init(void)
{
	init_calls++;
	return fail_init ? -1 : 0;
}

static void reset(void)
{
	have_iomanx = have_legacy_iomanx = have_filexio = 0;
	zero_search_result = 0;
	invalid_positive_search_result = 0;
	fail_iomanx = fail_filexio = fail_init = 0;
	filexio_server_ready = init_calls = exec_count = bind_calls = delay_calls = 0;
	lmb_patch_result = fail_prefix_patch = lmb_patch_calls = prefix_patch_calls = 0;
	memset(exec_names, 0, sizeof(exec_names));
}

int main(void)
{
	reset();
	have_iomanx = have_filexio = 1;
	filexio_server_ready = 1;
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 0 && init_calls == 1);
	assert(lmb_patch_calls == 0 && prefix_patch_calls == 0);

	reset();
	have_iomanx = 1;
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 1 && strcmp(exec_names[0], "fileXio") == 0);
	assert(init_calls == 1);
	assert(lmb_patch_calls == 1 && prefix_patch_calls == 1);

	reset();
	have_legacy_iomanx = 1;
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 1 && strcmp(exec_names[0], "fileXio") == 0);

	reset();
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 2);
	assert(strcmp(exec_names[0], "iomanX") == 0);
	assert(strcmp(exec_names[1], "fileXio") == 0);
	assert(init_calls == 1);
	assert(lmb_patch_calls == 1 && prefix_patch_calls == 1);

	/* PCSX2 HLE can return 0x40800000 for an absent module; this is not an
	 * IOP Loadcore module ID and must not suppress the embedded IOMANX load. */
	reset();
	invalid_positive_search_result = 1;
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 2);
	assert(strcmp(exec_names[0], "iomanX") == 0);
	assert(strcmp(exec_names[1], "fileXio") == 0);

	reset();
	fail_iomanx = 1;
	assert(hcu_storage_boot_init() != 0);
	assert(exec_count == 1 && init_calls == 0);

	reset();
	fail_filexio = 1;
	assert(hcu_storage_boot_init() != 0);
	assert(exec_count == 2 && init_calls == 0);

	reset();
	fail_init = 1;
	have_iomanx = have_filexio = 1;
	filexio_server_ready = 1;
	assert(hcu_storage_boot_init() != 0);
	assert(exec_count == 0 && init_calls == 1);

	/* A zero search result is not a loaded-module ID; load both IRXs rather
	 * than entering fileXioInit with no server available to bind. */
	reset();
	zero_search_result = 1;
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 2 && init_calls == 1);

	reset();
	lmb_patch_result = 1; /* already patched or nonstandard launcher image */
	assert(hcu_storage_boot_init() == 0);
	assert(exec_count == 2 && lmb_patch_calls == 1);

	reset();
	fail_prefix_patch = 1;
	assert(hcu_storage_boot_init() != 0);
	assert(exec_count == 0 && init_calls == 0);

	reset();
	have_iomanx = have_filexio = 1;
	assert(hcu_storage_boot_init() != 0);
	assert(init_calls == 0 && bind_calls == 2);
	assert(delay_calls == 200);
	return 0;
}
