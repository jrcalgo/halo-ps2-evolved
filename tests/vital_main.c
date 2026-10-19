#include "game/vital.h"
#include <stdio.h>

static void dump(const char *name, const vital *v)
{
    printf("%s shield %.7f body %.7f stun %d dead %d\n",
        name, v->shield, v->body, v->stun, v->dead);
}

static void shots(vital *v, int count, float amount, int part, float modifier, int headshot)
{
    int i;
    for (i = 0; i < count; i++) vital_hurt(v, amount, part, modifier, headshot);
}

int main(void)
{
    vital v;
    int i;
    vital_init(&v);
    shots(&v, 1, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol1", &v);
    shots(&v, 2, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol3", &v);
    shots(&v, 2, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol5", &v);

    vital_init(&v);
    shots(&v, 1, 25.0f, VITAL_HEAD, 1.5f, 1);
    dump("head_shielded", &v);
    v.shield = 0.0f;
    vital_hurt(&v, 25.0f, VITAL_HEAD, 1.5f, 1);
    dump("head_open", &v);

    vital_init(&v);
    shots(&v, 7, 10.0f, VITAL_BODY, 1.0f, 0);
    dump("rifle7", &v);
    vital_hurt(&v, 10.0f, VITAL_BODY, 1.0f, 0);
    dump("rifle8", &v);

    vital_init(&v);
    vital_hurt(&v, 25.0f, VITAL_BODY, 1.5f, 1);
    for (i = 0; i < 180; i++) vital_tick(&v);
    dump("recharge_wait", &v);
    vital_tick(&v);
    dump("recharge_step", &v);
    vital_init(&v);
    vital_melee(&v);
    dump("melee", &v);
    return 0;
}
