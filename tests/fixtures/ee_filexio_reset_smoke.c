/* Isolated PCSX2/PS2SDK diagnostic only. This intentionally resets the IOP
 * like the pinned SDK FileXio sample; never use it in the OPL/HCU startup. */
#define NEWLIB_PORT_AWARE
#include <fileXio_rpc.h>
#include <io_common.h>
#include <delaythread.h>
#include <iopcontrol.h>
#include <kernel.h>
#include <loadfile.h>
#include <sbv_patches.h>
#include <sifrpc.h>
#include <stdio.h>

extern const unsigned char halo_iomanx_irx_start[];
extern const unsigned int halo_iomanx_irx_size;
extern const unsigned char halo_filexio_irx_start[];
extern const unsigned int halo_filexio_irx_size;

int main(void)
{
	int iomanx_id, filexio_id;
	int iomanx_start = -999, filexio_start = -999;
	int result;
	int fd;
	int length;
	setbuf(stdout, NULL);
	printf("HALO_PS2_FILEXIO_SMOKE entry\n");
	SifInitRpc(0);
	while (!SifIopReset(NULL, 0)) { }
	while (!SifIopSync()) { }
	SifInitRpc(0);
	sbv_patch_enable_lmb();
	sbv_patch_disable_prefix_check();
	printf("HALO_PS2_FILEXIO_SMOKE iomanx-load\n");
	iomanx_id = SifExecModuleBuffer((void *)halo_iomanx_irx_start,
		halo_iomanx_irx_size, 0, NULL, &iomanx_start);
	printf("HALO_PS2_FILEXIO_SMOKE iomanx id=%d start=%d\n",
		iomanx_id, iomanx_start);
	if (iomanx_id <= 0 || iomanx_start != 0) return 1;
	printf("HALO_PS2_FILEXIO_SMOKE filexio-load\n");
	filexio_id = SifExecModuleBuffer((void *)halo_filexio_irx_start,
		halo_filexio_irx_size, 0, NULL, &filexio_start);
	printf("HALO_PS2_FILEXIO_SMOKE filexio id=%d start=%d\n",
		filexio_id, filexio_start);
	if (filexio_id <= 0 || filexio_start != 0) return 2;
	printf("HALO_PS2_FILEXIO_SMOKE init-begin\n");
	result = fileXioInit();
	printf("HALO_PS2_FILEXIO_SMOKE init-result=%d\n", result);
	if (result != 0) return 3;
	printf("HALO_PS2_FILEXIO_SMOKE init-ready\n");
	/* Diagnostic only: validate the PS2 CDVD device/path used by the HCU
	 * reader against the attached test ISO. This remains a reset-based sample,
	 * not the OPL-safe product startup path. */
	fd = fileXioOpen("cdrom:\\MAPS\\UI.MAP;1", FIO_O_RDONLY, 0);
	printf("HALO_PS2_FILEXIO_SMOKE cdrom-open=%d\n", fd);
	if (fd >= 0) {
		length = fileXioLseek(fd, 0, FIO_SEEK_END);
		printf("HALO_PS2_FILEXIO_SMOKE cdrom-size=%d\n", length);
		fileXioClose(fd);
	}
	for (;;) DelayThread(1000000);
}
