#include "../submodules/halo-ps2/engine/src/stream/iso9660_name.h"

#include <stdio.h>
#include <string.h>

static int expect(const char *input, const char *want)
{
	char buffer[256];
	if (strlen(input) >= sizeof(buffer)) return 1;
	memcpy(buffer, input, strlen(input) + 1u);
	iso9660_alias_cdrom_path(buffer);
	iso9660_level2_limit_path(buffer);
	if (strcmp(buffer, want) != 0) {
		fprintf(stderr, "got %s\nwant %s\n", buffer, want);
		return 1;
	}
	return 0;
}

int main(void)
{
	int failed = 0;
	failed |= expect("cdrom:\\MAPS\\UI.MAP", "cdrom:\\MAPS\\UI.MAP");
	failed |= expect("cdrom:\\BUILD\\M2-C2-R3-SELECTED-PACKAGES\\PKG\\"
		"BLOODGULCH_MOUNTED_GUNNER_4P4BOT\\"
		"BLOODGULCH_MOUNTED_GUNNER_4P4BOT.HCP",
		"cdrom:\\BGPKG.HCP");
	failed |= expect("cdrom:\\BUILD\\M2-C2-R3-SELECTED-PACKAGES\\PKG\\"
		"BLOODGULCH_MOUNTED_GUNNER_4P4BOT\\OTHER.DAT",
		"cdrom:\\BUILD\\M2-C2-R3-SELECTED-PACKAGES\\PKG\\"
		"BLOODGULCH_MOUNTED_GUNNER_4P4B\\OTHER.DAT");
	failed |= expect("HPS2_000.01", "HPS2_000.01");
	failed |= expect("cdrom:\\BUILD\\RETAIL-MAPS\\DECOMPRESSED\\BEAVERCREEK.MAP",
		"cdrom:\\BEAVER.MAP");
	failed |= expect("cdrom:\\BUILD\\RETAIL-MAPS\\DECOMPRESSED\\C40.MAP",
		"cdrom:\\MAPS\\C40.MAP");
	return failed;
}
