#include <kernel.h>
#include <libcdvd.h>
#include <sifrpc.h>
#include <stdio.h>

int main(void)
{
	static const char *const paths[] = {
		"\\MAPS\\UI.MAP;1", "/MAPS/UI.MAP;1", "MAPS\\UI.MAP;1",
		"MAPS/UI.MAP;1", "\\MAPS\\UI.MAP", "UI.MAP;1",
		"\\PACKAGES\\MENU_AUDIO.HSB;1", "/PACKAGES/MENU_AUDIO.HSB;1"
	};
	unsigned i;
	SifInitRpc(0);
	printf("HCU_CDPROBE init=%d\n", sceCdInit(SCECdINIT));
	for (i = 0; i < sizeof(paths) / sizeof(paths[0]); ++i) {
		sceCdlFILE info;
		int found = sceCdSearchFile(&info, paths[i]);
		printf("HCU_CDPROBE path=%s found=%d lsn=%u size=%u\n", paths[i],
			found, found ? info.lsn : 0u, found ? info.size : 0u);
	}
	SleepThread();
	return 0;
}
