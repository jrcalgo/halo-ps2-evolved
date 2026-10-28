/* PS2 glue for the SPU2 player: embedded libsd/sdrdrv IRX images, the sdrdrv
 * remote and the one-time bank upload. The player core is hcu_spu_playback.c. */
#include "stream/hcu_spu_hw.h"

#include <iopheap.h>
#include <kernel.h>
#include <libsdr.h>
#include <loadfile.h>
#include <sifrpc.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "stream/hcu_file_bridge.h"
#include "stream/sha256.h"

#define HCU_SPU_STAGE_BYTES 16384u
#define HCU_SPU_HEADER_BYTES (32u + 32u * HCU_SPU_MAX_SAMPLES)
#define HCU_SPU_SD_INIT_COLD 0
#define HCU_SPU_CORE1 1u
#define HCU_SPU_CORE0 0u

extern const unsigned char halo_libsd_irx_start[];
extern const uint32_t halo_libsd_irx_size;
extern const unsigned char halo_sdrdrv_irx_start[];
extern const uint32_t halo_sdrdrv_irx_size;

/* This PS2SDK's libsdr.a references g_libsdr_cb_data from sdr_cb.o without defining it anywhere, so the
 * static link fails even though only sceSdRemote/sceSdRemoteInit/sceSdTransToIOP are used. The callback
 * machinery (sceSdRemoteCallbackInit and the SdrSet* handlers) is never called; this opaque block only
 * satisfies the reference and is larger than struct libsdr_cb_data (about 4.4 KB). */
char g_libsdr_cb_data[6144] __attribute__((aligned(64)));

static uint8_t s_stage[HCU_SPU_STAGE_BYTES] __attribute__((aligned(64)));
static uint8_t s_header[HCU_SPU_HEADER_BYTES] __attribute__((aligned(16)));
static hcu_spu_sample s_parsed[HCU_SPU_MAX_SAMPLES];
static void *s_iop_stage;
static int s_hw_ready;
static int s_bank_token = -1; /* the verified bank stays open for on-demand sample reads */

static void hw_set_param(uint16_t entry, uint16_t value)
{
	(void)sceSdRemote(1, rSdSetParam, entry, value);
}

static void hw_set_addr(uint16_t entry, uint32_t value)
{
	(void)sceSdRemote(1, rSdSetAddr, entry, value);
}

static void hw_set_switch(uint16_t entry, uint32_t value)
{
	(void)sceSdRemote(1, rSdSetSwitch, entry, value);
}

static uint32_t hw_get_switch(uint16_t entry)
{
	return (uint32_t)sceSdRemote(1, rSdGetSwitch, entry);
}

static int hw_upload(const hcu_spu_sample *sample, uint32_t spu_addr);
static const hcu_spu_hw s_hw = { hw_set_param, hw_set_addr, hw_set_switch, hw_get_switch, hw_upload };

static int load_irx(const char *name, const unsigned char *image, uint32_t size)
{
	int start_result = 0;
	int id = SifExecModuleBuffer((void *)image, size, 0, NULL, &start_result);
	printf("HALO_PS2_LOCAL spu-module name=%s id=%d start=%d\n", name, id, start_result);
	return id > 0 && start_result != 1 ? 0 : -1;
}

int hcu_spu_init(void)
{
	uint32_t voice;
	if (s_hw_ready) return 0;
	if (load_irx("libsd", halo_libsd_irx_start, halo_libsd_irx_size) != 0 ||
		load_irx("sdrdrv", halo_sdrdrv_irx_start, halo_sdrdrv_irx_size) != 0)
		return -1;
	if (sceSdRemoteInit() < 0) {
		printf("HALO_PS2_LOCAL spu-fail stage=remote-init\n");
		return -2;
	}
	(void)sceSdRemote(1, rSdInit, HCU_SPU_SD_INIT_COLD);
	/* CORE1 carries the effect voices to the output; CORE0 is muted like audsrv does. */
	hw_set_param((uint16_t)(HCU_SPU_CORE0 | SD_PARAM_MVOLL), 0);
	hw_set_param((uint16_t)(HCU_SPU_CORE0 | SD_PARAM_MVOLR), 0);
	hw_set_param((uint16_t)(HCU_SPU_CORE1 | SD_PARAM_MVOLL), 0x3FFF);
	hw_set_param((uint16_t)(HCU_SPU_CORE1 | SD_PARAM_MVOLR), 0x3FFF);
	hw_set_switch((uint16_t)(HCU_SPU_CORE1 | SD_SWITCH_VMIXL), 0xFFFFFF);
	hw_set_switch((uint16_t)(HCU_SPU_CORE1 | SD_SWITCH_VMIXR), 0xFFFFFF);
	for (voice = 0; voice < HCU_SPU_VOICES; ++voice) {
		hw_set_param((uint16_t)(HCU_SPU_CORE1 | (voice << 1) | SD_VPARAM_VOLL), 0);
		hw_set_param((uint16_t)(HCU_SPU_CORE1 | (voice << 1) | SD_VPARAM_VOLR), 0);
	}
	hw_set_switch((uint16_t)(HCU_SPU_CORE1 | SD_SWITCH_KOFF), 0xFFFFFF);
	if (SifInitIopHeap() < 0) {
		printf("HALO_PS2_LOCAL spu-fail stage=iop-heap-init\n");
		return -3;
	}
	s_iop_stage = SifAllocIopHeap((int)HCU_SPU_STAGE_BYTES);
	if (!s_iop_stage) {
		printf("HALO_PS2_LOCAL spu-fail stage=iop-heap-alloc\n");
		return -4;
	}
	s_hw_ready = 1;
	printf("HALO_PS2_LOCAL spu-ready iop-stage=%p\n", s_iop_stage);
	return 0;
}

static int upload_chunk(const uint8_t *data, uint32_t bytes, uint32_t spu_addr)
{
	uint32_t padded = (bytes + 63u) & ~63u;
	if (padded > bytes) memset(s_stage + bytes, 0, padded - bytes);
	if (sceSdTransToIOP(s_stage, s_iop_stage, padded, 1) < 0) return -1;
	(void)sceSdRemote(1, rSdVoiceTrans, 0, SD_TRANS_WRITE | SD_TRANS_MODE_DMA,
		(u8 *)s_iop_stage, spu_addr, padded);
	(void)sceSdRemote(1, rSdVoiceTransStatus, 0, 1);
	(void)data;
	return 0;
}

static int read_exact(int token, void *dst, uint32_t bytes)
{
	unsigned long got = 0;
	return hcu_file_bridge_read(token, dst, bytes, &got) && got == bytes;
}

/* Reads one sample from the verified bank file and uploads it to SPU2 RAM. */
static int hw_upload(const hcu_spu_sample *sample, uint32_t spu_addr)
{
	uint32_t done = 0;
	if (s_bank_token < 0) return -1;
	if (hcu_file_bridge_seek(s_bank_token, (long)sample->bank_offset, 0) != (long)sample->bank_offset) return -2;
	while (done < sample->bytes) {
		uint32_t n = sample->bytes - done < HCU_SPU_STAGE_BYTES ? sample->bytes - done : HCU_SPU_STAGE_BYTES;
		if (!read_exact(s_bank_token, s_stage, n)) return -3;
		if (upload_chunk(s_stage, n, spu_addr + done) != 0) return -4;
		done += n;
	}
	return 0;
}

int hcu_spu_load_bank(const char *path)
{
	unsigned long size = 0;
	int token;
	uint32_t count = 0, data_off = 0, data_end = 0, header_bytes, remaining, spu_addr, uploaded = 0;
	sha256_context sha;
	uint8_t digest[32], trailer[32];
	if (!s_hw_ready) return -1;
	token = hcu_file_bridge_open(path, &size);
	if (token < 0) {
		printf("HALO_PS2_LOCAL spu-fail stage=bank-open path=%s\n", path);
		return -2;
	}
	header_bytes = size < HCU_SPU_HEADER_BYTES ? (uint32_t)size : HCU_SPU_HEADER_BYTES;
	if (!read_exact(token, s_header, header_bytes)) goto fail_read;
	if (hcu_spu_bank_parse(s_header, (uint32_t)size, s_parsed, HCU_SPU_MAX_SAMPLES, &count, &data_off, &data_end) != 0 ||
		data_off > header_bytes) {
		printf("HALO_PS2_LOCAL spu-fail stage=bank-parse size=%lu\n", size);
		hcu_file_bridge_close(token);
		return -3;
	}
	sha256_init(&sha);
	sha256_update(&sha, s_header, data_off);
	if (hcu_file_bridge_seek(token, (long)data_off, 0) != (long)data_off) goto fail_read;
	remaining = data_end - data_off;
	spu_addr = HCU_SPU_RAM_BASE;
	while (remaining) {
		uint32_t n = remaining < HCU_SPU_STAGE_BYTES ? remaining : HCU_SPU_STAGE_BYTES;
		if (!read_exact(token, s_stage, n)) goto fail_read;
		sha256_update(&sha, s_stage, n);
		/* The whole file is read to verify it; only the leading part that fits SPU2 RAM is uploaded now. */
		if (spu_addr < HCU_SPU_RAM_END) {
			uint32_t up = n < HCU_SPU_RAM_END - spu_addr ? n : HCU_SPU_RAM_END - spu_addr;
			if (upload_chunk(s_stage, up, spu_addr) != 0) goto fail_read;
			uploaded += up;
		}
		spu_addr += n;
		remaining -= n;
	}
	sha256_final(&sha, digest);
	if (!read_exact(token, trailer, 32) || memcmp(digest, trailer, 32) != 0) {
		/* SPU2 RAM holds unverified bytes; never attach, never key on. */
		printf("HALO_PS2_LOCAL spu-fail stage=bank-digest uploaded=%u\n", (unsigned)uploaded);
		hcu_file_bridge_close(token);
		return -4;
	}
	if (s_bank_token >= 0) hcu_file_bridge_close(s_bank_token);
	s_bank_token = token;
	hcu_spu_attach(&s_hw, s_parsed, count);
	hcu_spu_note_uploaded(uploaded);
	printf("HALO_PS2_LOCAL spu-bank-ready samples=%u uploaded=%u spu-end=0x%x\n",
		(unsigned)count, (unsigned)uploaded, (unsigned)spu_addr);
	return 0;
fail_read:
	printf("HALO_PS2_LOCAL spu-fail stage=bank-read\n");
	hcu_file_bridge_close(token);
	return -5;
}
