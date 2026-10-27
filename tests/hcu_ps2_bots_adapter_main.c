/* Host checks for the pure helpers of the PS2 bot adapter (submodules/halo-ce-universal/port/ps2/src/ps2_bots.c).
 * The Python test extracts the helpers from that file and compiles them here, with the seat constants it reads from
 * the adapter's header. The CE formula that the aim conversion must invert is vector3d_from_euler_angles2d
 * (source/math/real_math.c): i = cos(yaw) cos(pitch), j = sin(yaw) cos(pitch), k = sin(pitch). */
#include <assert.h>
#include <stddef.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

/* ps2_bots_seat_* and the aim conversion, extracted verbatim below */
#include "ps2_bots_pure.inc"

static void check_aim_round_trip(float const aim[3])
{
	float yaw;
	float pitch;
	float length = sqrtf(aim[0] * aim[0] + aim[1] * aim[1] + aim[2] * aim[2]);
	float back[3];

	ps2_bots_aim_to_facing(aim, &yaw, &pitch);
	back[0] = cosf(yaw) * cosf(pitch);
	back[1] = sinf(yaw) * cosf(pitch);
	back[2] = sinf(pitch);
	/* the unit vector comes back, in the same direction */
	assert(fabsf(back[0] - aim[0] / length) < 1e-4f);
	assert(fabsf(back[1] - aim[1] / length) < 1e-4f);
	assert(fabsf(back[2] - aim[2] / length) < 1e-4f);
}

int main(void)
{
	static float const aims[][3] = {
		{ 1.0f, 0.0f, 0.0f },
		{ 0.0f, 1.0f, 0.0f },
		{ -1.0f, 0.0f, 0.0f },
		{ 0.0f, 0.0f, 1.0f },
		{ 0.0f, 0.0f, -1.0f },
		{ 0.3f, -0.7f, 0.2f },
		{ -2.0f, 1.5f, -0.4f },
		{ 0.001f, 0.002f, 5.0f }
	};
	float zero[3] = { 0.0f, 0.0f, 0.0f };
	float yaw = 9.0f;
	float pitch = 9.0f;
	uint32_t bot;
	size_t i;

	for (i = 0; i < sizeof(aims) / sizeof(aims[0]); i++)
		check_aim_round_trip(aims[i]);

	/* a zero aim keeps the facing at zero */
	ps2_bots_aim_to_facing(zero, &yaw, &pitch);
	assert(yaw == 0.0f && pitch == 0.0f);

	/* seats: bot i is player HALO_PS2_BOTS_SLOT_BASE + i on machine 1 + i / 4, never machine 0 */
	for (bot = 0; bot < HCU_BOT_MAX_TEST; bot++) {
		assert(ps2_bots_seat_player(bot) == (long)(SLOT_BASE_TEST + bot));
		assert(ps2_bots_seat_machine(bot) == (long)(1 + bot / SEATS_PER_MACHINE_TEST));
		assert(ps2_bots_seat_machine(bot) >= 1);
		assert(ps2_bots_seat_player(bot) >= SLOT_BASE_TEST);
	}
	assert(ps2_bots_seat_machine(0) == 1);
	assert(ps2_bots_seat_machine(3) == 1);
	assert(ps2_bots_seat_machine(4) == 2);
	assert(ps2_bots_seat_player(7) == 11);

	/* weapon lookup: the core's index of a CE tag, or count when the core does not know it */
	{
		long const tags[] = { 10, 20, 30 };

		assert(ps2_bots_weapon_lookup(tags, 3, 10) == 0);
		assert(ps2_bots_weapon_lookup(tags, 3, 20) == 1);
		assert(ps2_bots_weapon_lookup(tags, 3, 30) == 2);
		assert(ps2_bots_weapon_lookup(tags, 3, 99) == 3);
		assert(ps2_bots_weapon_lookup(tags, 3, -1) == 3);
	}

	/* name slot: the core's name index folded into the pool; an empty pool gives slot 0 */
	assert(ps2_bots_name_slot(45, 40) == 5);
	assert(ps2_bots_name_slot(3, 2) == 1);
	assert(ps2_bots_name_slot(7, 0) == 0);

	printf("ps2_bots adapter: ok\n");
	printf("ps2_bots adapter tests passed\n");
	return 0;
}
