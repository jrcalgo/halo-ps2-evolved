#include "render/bsp_render.h"

int main(void)
{
	return bsp_screen_copy_probe() == 0 && hcu_screen_effect_probe() == 0 ? 0 : 1;
}
