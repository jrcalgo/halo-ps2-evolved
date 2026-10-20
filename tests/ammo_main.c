/* Reads weapons.fp magazines with the same record the play build uses. */
#include "game/play_fp.h"
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(play_fp_ammo) == 80, "magazine record");

int main(int argc, char **argv)
{
    FILE *file;
    char magic[4];
    unsigned short count, rec, maps, ammo_count;
    int i;
    if (argc != 2) return 1;
    file = fopen(argv[1], "rb");
    if (!file) return 1;
    if (fread(magic, 1, 4, file) != 4 || memcmp(magic, "WFP1", 4) != 0 ||
        fread(&count, 2, 1, file) != 1 || fread(&rec, 2, 1, file) != 1 ||
        fseek(file, 8 + (long)count * rec, SEEK_SET) != 0 ||
        fread(magic, 1, 4, file) != 4 || memcmp(magic, "RMP1", 4) != 0 ||
        fread(&maps, 2, 1, file) != 1 ||
        fseek(file, (long)maps * 144, SEEK_CUR) != 0 ||
        fread(magic, 1, 4, file) != 4 || memcmp(magic, "AMO1", 4) != 0 ||
        fread(&ammo_count, 2, 1, file) != 1 || ammo_count != count) {
        fclose(file);
        return 1;
    }
    for (i = 0; i < count; i++) {
        play_fp_ammo ammo;
        gun_def def;
        gun weapon;
        if (fread(&ammo, sizeof ammo, 1, file) != 1) {
            fclose(file);
            return 1;
        }
        memset(&def, 0, sizeof def);
        play_fp_apply_ammo(&def, &ammo);
        gun_init(&weapon, &def);
        printf("clip %d %d %d %d %d %d %d %d\n",
            def.rounds_loaded_maximum, def.rounds_total_initial, def.rounds_reloaded,
            def.rounds_per_shot, def.reload_empty_frames, def.ready_frames,
            def.shotgun_enter_frames, def.uses_magazine);
        printf("held %d %d %d\n", weapon.loaded, weapon.total, def.has_trigger);
        if (i == 5) {
            int tick, fired_tick = -1;
            for (tick = 0; tick < 40; ++tick)
                if (gun_tick(&weapon, &def, 1, 0)) fired_tick = tick;
            if (gun_tick(&weapon, &def, 0, 0)) fired_tick = 40;
            printf("plasma pistol fired_tick=%d shots=%u heat=%.3f\n",
                fired_tick, weapon.shots, weapon.heat);
        } else if (i == 6) {
            int tick, overheats = 0, was_overheated = 0;
            for (tick = 0; tick < 90; ++tick) {
                (void)gun_tick(&weapon, &def, 1, 0);
                if (weapon.overheated && !was_overheated) ++overheats;
                was_overheated = weapon.overheated;
            }
            printf("plasma rifle shots=%u overheats=%d heat=%.3f\n",
                weapon.shots, overheats, weapon.heat);
        }
    }
    fclose(file);
    return 0;
}
