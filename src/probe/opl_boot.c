/* Incremental OPL virtual-disc probe. Same installed CRT and storage backend
 * as the HCU machine; no pad, audio, network or IOP reset. */
#include "stream/hcu_boot_diag.h"
#include "stream/hcu_storage_boot.h"
#include "stream/file.h"
#include "stream/sha256.h"
#include <debug.h>
#include <kernel.h>
#include <loadfile.h>
#include <sifrpc.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#ifndef HCU_OPL_PROBE_LEVEL
#define HCU_OPL_PROBE_LEVEL 1
#endif

int main(void)
{
 hcu_boot_diag_begin();
 scr_printf("PROBE %d\n", HCU_OPL_PROBE_LEVEL);
#if HCU_OPL_PROBE_LEVEL >= 2
 static const char *const modules[] = {
  "IO/File_Manager", "IOX/File_Manager", "IOX/File_Manager_Rpc",
  "cdvdman", "sio2man", "padman", "mcman", "mcserv"
 };
 unsigned i;
 void *block;
 hcu_boot_diag_stage(HCU_BOOT_MEMORY, 0);
 block = malloc(4096);
 if (!block) hcu_boot_diag_fail(-4);
 scr_printf("EE alloc %08x\n", (unsigned)(uintptr_t)block);
 free(block);
 hcu_boot_diag_stage(HCU_BOOT_SIF, 0);
 SifInitRpc(0);
 SifLoadFileInit();
 for (i = 0; i < sizeof modules / sizeof modules[0]; ++i)
  scr_printf("%s id %d\n", modules[i], SifSearchModuleByName(modules[i]));
 scr_printf("IDs alone do not prove protocol compatibility\n");
#endif
#if HCU_OPL_PROBE_LEVEL >= 3
 {
  static unsigned char data[4096] __attribute__((aligned(64)));
  unsigned char digest[32];
  static const unsigned char expected[32] = {
   0xa3,0xf8,0xab,0x90,0x03,0x01,0x45,0xc5,0x01,0x2a,0x55,0x12,0xd8,0x7d,0xd1,0x87,
   0x8b,0x4a,0x2e,0x1b,0xd0,0x5c,0x05,0x55,0x66,0x13,0xb0,0xfc,0x0a,0x8f,0xee,0x37
  };
  sha256_context hash;
  file_reader_t file;
  uint32_t offset = 0;
  hcu_boot_diag_stage(HCU_BOOT_FILEXIO, 0);
  if (hcu_storage_boot_init() != 0) hcu_boot_diag_fail(-7);
  hcu_boot_diag_stage(HCU_BOOT_DISC, 0);
  if (!file_set_default_root("cdrom:/") ||
      file_reader_open(&file, "PROBE.BIN") != 0) hcu_boot_diag_fail(-81);
  scr_printf("PROBE.BIN bytes %u\n", (unsigned)file.size);
  if (file.size != 16421u) hcu_boot_diag_fail(-83);
  sha256_init(&hash);
  while (offset < file.size) {
   unsigned count = file.size - offset;
   if (count > sizeof data) count = sizeof data;
   if (file_reader_read_at(&file, offset, data, count) != 0) hcu_boot_diag_fail(-82);
   sha256_update(&hash, data, count);
   offset += count;
  }
  file_reader_close(&file);
  sha256_final(&hash, digest);
  if (memcmp(digest, expected, sizeof digest) != 0) hcu_boot_diag_fail(-84);
  scr_printf("SHA256 verified\n");
  for (i = 0; i < sizeof digest; ++i) scr_printf("%02x", digest[i]);
  scr_printf("\n");
  /* Exercise the production backend with unaligned destinations and sector
   * crossings. The final short file chunk was hashed above. */
  {
   static const unsigned offsets[] = {0, 1, 2047, 8191, 16420};
   unsigned range, byte;
   if (file_reader_open(&file, "PROBE.BIN") != 0) hcu_boot_diag_fail(-85);
   for (range = 0; range < sizeof offsets / sizeof offsets[0]; ++range) {
    unsigned count = file.size - offsets[range];
    if (count > 123) count = 123;
    if (file_reader_read_at(&file, offsets[range], data + 1, count) != 0)
     hcu_boot_diag_fail(-86);
    for (byte = 0; byte < count; ++byte) {
     unsigned pos = offsets[range] + byte;
     if (data[1 + byte] != ((pos * 37 + pos / 256) & 255)) hcu_boot_diag_fail(-87);
    }
   }
   if (!file_reader_prefetch_bind(data, sizeof data)) hcu_boot_diag_fail(-88);
   (void)file_reader_prefetch(&file, 0, sizeof data);
   file_reader_close(&file); /* must settle any outstanding DMA before reuse */
   scr_printf("ranges/reopen/prefetch-close complete\n");
  }
 }
#endif
 scr_printf("PROBE COMPLETE; photograph screen\n");
 printf("HALO_OPL_PROBE complete level=%d\n", HCU_OPL_PROBE_LEVEL);
 SleepThread();
 return 0;
}
