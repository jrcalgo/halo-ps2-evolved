#include "stream/hcu_bot.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define HCU_BOT_WEAPON_NONE_TEST 0xffu

/* A scripted world: collision is a flag (1 clear, 0 walled), the path returns a fixed waypoint, the objective
 * is optional. The percepts are set by each test. */
typedef struct test_world {
	int clear;
	int path_ok;
	float path_next[3];
	int objective_ok;
	float objective_goal[3];
	int path_calls;
} test_world;

static int t_line_clear(void *ctx, const float from[3], const float to[3])
{
	test_world *w = (test_world *)ctx;
	(void)from;
	(void)to;
	return w->clear;
}

static int t_path_step(void *ctx, uint32_t bot, const float from[3], const float goal[3], float next[3])
{
	test_world *w = (test_world *)ctx;
	(void)bot;
	(void)from;
	(void)goal;
	w->path_calls++;
	if (w->path_ok) {
		next[0] = w->path_next[0];
		next[1] = w->path_next[1];
		next[2] = w->path_next[2];
	}
	return w->path_ok;
}

static int t_objective(void *ctx, uint32_t bot, float goal[3])
{
	test_world *w = (test_world *)ctx;
	(void)bot;
	if (w->objective_ok) {
		goal[0] = w->objective_goal[0];
		goal[1] = w->objective_goal[1];
		goal[2] = w->objective_goal[2];
	}
	return w->objective_ok;
}

static void world_init(hcu_bot_world *world, test_world *tw)
{
	uint32_t k;
	memset(world, 0, sizeof *world);
	memset(tw, 0, sizeof *tw);
	tw->clear = 1;
	for (k = 0; k < HCU_BOT_PLAYER_SLOTS; k++) {
		/* Every player starts dead: a test places the players it uses with set_pos. */
		world->players[k].alive = 0;
		world->players[k].team = HCU_BOT_TEAM_NONE;
		world->players[k].weapon = HCU_BOT_WEAPON_NONE_TEST;
		world->players[k].other_weapon = HCU_BOT_WEAPON_NONE_TEST;
	}
	world->line_clear = t_line_clear;
	world->path_step = t_path_step;
	world->objective = t_objective;
	world->ctx = tw;
}

static void set_pos(hcu_bot_world *world, uint32_t player, float x, float y, float z)
{
	world->players[player].alive = 1;
	world->players[player].pos[0] = x;
	world->players[player].pos[1] = y;
	world->players[player].pos[2] = z;
}

static hcu_bot_config config(uint32_t seed, uint8_t count, uint8_t skill)
{
	hcu_bot_config c;
	memset(&c, 0, sizeof c);
	c.seed = seed;
	c.count = count;
	c.skill = skill;
	return c;
}

static int weapon_index(const char *name)
{
	uint32_t i;
	for (i = 0; i < hcu_bot_weapon_count(); i++) {
		if (strcmp(hcu_bot_weapon_name(i), name) == 0) {
			return (int)i;
		}
	}
	return -1;
}

static void test_config(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(1234u, 9, HCU_BOT_SKILL_NORMAL);
	assert(hcu_bot_init(&state, &c) == -1);
	c.count = HCU_BOT_MAX;
	c.skill = HCU_BOT_SKILL_COUNT;
	assert(hcu_bot_init(&state, &c) == -1);
	c.skill = HCU_BOT_SKILL_LEGENDARY;
	assert(hcu_bot_init(&state, &c) == 0);
	assert(state.count == HCU_BOT_MAX);
	assert(HCU_BOT_PLAYER_SLOT_BASE == HCU_BOT_LOCAL_SLOTS);
	assert(HCU_BOT_PLAYER_SLOTS == HCU_BOT_LOCAL_SLOTS + HCU_BOT_MAX);
	assert(hcu_bot_weapon_count() == 10);
	assert(hcu_bot_weapon_name(10) == NULL);
	printf("config: ok\n");
}

static void test_rng(void)
{
	hcu_bot_rng a, b, c;
	uint32_t i;
	int differs = 0;
	hcu_bot_rng_seed(&a, 77u, 0u);
	hcu_bot_rng_seed(&b, 77u, 0u);
	hcu_bot_rng_seed(&c, 77u, 1u);
	for (i = 0; i < 64; i++) {
		uint32_t va = hcu_bot_rng_next(&a);
		uint32_t vb = hcu_bot_rng_next(&b);
		uint32_t vc = hcu_bot_rng_next(&c);
		assert(va != 0u);
		assert(va == vb);
		if (va != vc) {
			differs = 1;
		}
	}
	assert(differs);
	hcu_bot_rng_seed(&a, 0u, 0u);
	assert(a.state != 0u);
	printf("rng: ok\n");
}

static void test_roster(void)
{
	hcu_bot_state state;
	uint32_t seed;
	for (seed = 0; seed < 640u; seed++) {
		uint32_t i, j;
		hcu_bot_config c = config(seed, HCU_BOT_MAX, HCU_BOT_SKILL_HEROIC);
		assert(hcu_bot_init(&state, &c) == 0);
		for (i = 0; i < HCU_BOT_MAX; i++) {
			assert(state.slots[i].name < HCU_BOT_NAME_COUNT);
			for (j = 0; j < i; j++) {
				assert(state.slots[i].name != state.slots[j].name);
			}
		}
	}
	{
		hcu_bot_config c = config(5u, 4, HCU_BOT_SKILL_EASY);
		c.team_mode = 1;
		c.bot_team = 1;
		assert(hcu_bot_init(&state, &c) == 0);
		assert(state.slots[0].team == 1 && state.slots[3].team == 1);
	}
	printf("roster: ok\n");
}

static void test_combat_and_fire_style(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(99u, 1, HCU_BOT_SKILL_LEGENDARY);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	int auto_weapon = weapon_index("weapons\\assault rifle\\assault rifle");
	uint32_t tick;
	assert(auto_weapon >= 0);
	assert(hcu_bot_init(&state, &c) == 0);
	world_init(&world, &tw);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
	set_pos(&world, 0u, 5.f, 0.f, 0.f);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)auto_weapon;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].has_weapon = 1;
	hcu_bot_think(&state, &world, out);
	assert(out[0].trigger == 1); /* automatic: held */
	assert(out[0].aim[0] > 0.f);
	assert(state.slots[0].target == 0u);

	/* Semi-automatic: the trigger alternates over a burst, then pauses. */
	{
		int pistol = weapon_index("weapons\\pistol\\pistol");
		int ones = 0;
		int zero_run = 0;
		int longest_pause = 0;
		assert(pistol >= 0);
		hcu_bot_state s2;
		hcu_bot_config c2 = config(3u, 1, HCU_BOT_SKILL_EASY);
		assert(hcu_bot_init(&s2, &c2) == 0);
		world_init(&world, &tw);
		set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
		set_pos(&world, 0u, 8.f, 0.f, 0.f); /* within the pistol's range */
		world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)pistol;
		for (tick = 0; tick < 120; tick++) {
			hcu_bot_think(&s2, &world, out);
			if (out[0].trigger) {
				ones++;
				zero_run = 0;
			} else {
				zero_run++;
				if (zero_run > longest_pause) {
					longest_pause = zero_run;
				}
			}
		}
		assert(ones > 0);
		assert(longest_pause >= 30); /* easy's pause is 34 ticks */
	}
	printf("combat: ok\n");
}

static void test_team_and_occlusion(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(42u, 2, HCU_BOT_SKILL_NORMAL);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	int rocket = weapon_index("weapons\\rocket launcher\\rocket launcher");
	int assault = weapon_index("weapons\\assault rifle\\assault rifle");
	assert(rocket >= 0 && assault >= 0);

	/* Team game: bot 0 (team 1) with a teammate (bot 1) between it and the only enemy (human, team 0). The bot
	 * must aim past the teammate at the enemy, and never fire at the teammate. */
	c.team_mode = 1;
	c.bot_team = 1;
	assert(hcu_bot_init(&state, &c) == 0);
	world_init(&world, &tw);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].team = 1;
	world.players[HCU_BOT_PLAYER_SLOT_BASE + 1].team = 1;
	world.players[0].team = 0;
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE + 1, 2.f, 0.f, 0.f);
	set_pos(&world, 0u, 6.f, 0.f, 0.f);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)assault;
	hcu_bot_think(&state, &world, out);
	assert(state.slots[0].target == 0u);
	assert(out[0].aim[0] > 5.5f && out[0].aim[0] < 6.5f); /* aims at the enemy, not the teammate */

	/* A teammate alone is never a target. */
	world_init(&world, &tw);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].team = 1;
	world.players[HCU_BOT_PLAYER_SLOT_BASE + 1].team = 1;
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE + 1, 3.f, 0.f, 0.f);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)assault;
	hcu_bot_think(&state, &world, out);
	assert(out[0].trigger == 0);
	assert(state.slots[0].target == 0xffu);
	assert(out[0].aim[0] == 0.f && out[0].aim[1] == 0.f && out[0].aim[2] == 0.f);

	/* Occlusion: the enemy is out of sight. No trigger; the bot steers by CE's waypoint, not the straight line. */
	{
		hcu_bot_state s2;
		hcu_bot_config c2 = config(8u, 1, HCU_BOT_SKILL_NORMAL);
		assert(hcu_bot_init(&s2, &c2) == 0);
		world_init(&world, &tw);
		set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
		set_pos(&world, 0u, 6.f, 0.f, 0.f);
		world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)assault;
		tw.clear = 0;
		tw.path_ok = 1;
		tw.path_next[0] = 0.f;
		tw.path_next[1] = 5.f;
		tw.path_next[2] = 0.f;
		hcu_bot_think(&s2, &world, out);
		assert(out[0].trigger == 0);
		assert(s2.slots[0].target_visible == 0);
		assert(tw.path_calls > 0);
		assert(out[0].stick[0] == 0.f && out[0].stick[1] > 0.99f); /* waypoint direction, not (1, 0) */
	}
	printf("team: ok\n");
	printf("occlusion: ok\n");

	/* Pickups: an unarmed-by-score weapon in reach is not taken; a better one is walked to and taken. */
	{
		hcu_bot_state s3;
		hcu_bot_config c3 = config(11u, 1, HCU_BOT_SKILL_NORMAL);
		hcu_bot_world w3;
		test_world t3;
		int pistol = weapon_index("weapons\\pistol\\pistol");
		assert(hcu_bot_init(&s3, &c3) == 0);
		world_init(&w3, &t3);
		set_pos(&w3, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
		w3.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = (uint8_t)pistol; /* score 8 */
		w3.pickups[0].valid = 1;
		w3.pickups[0].weapon = (uint8_t)rocket; /* score 9: better */
		w3.pickups[0].pos[0] = 0.f;
		w3.pickups[0].pos[1] = 4.f;
		w3.pickups[0].pos[2] = 0.f;
		hcu_bot_think(&s3, &w3, out);
		assert(out[0].stick[0] == 0.f && out[0].stick[1] > 0.99f);
		assert(out[0].action == 0);
		w3.pickups[0].pos[1] = 0.f;
		w3.pickups[0].pos[0] = 0.2f;
		hcu_bot_think(&s3, &w3, out);
		assert(out[0].action == 1);

		w3.pickups[0].weapon = (uint8_t)weapon_index("weapons\\sniper rifle\\sniper rifle"); /* score 8: not better */
		w3.pickups[0].pos[0] = 0.f;
		w3.pickups[0].pos[1] = 4.f;
		hcu_bot_think(&s3, &w3, out);
		assert(out[0].action == 0);
		assert(out[0].stick[1] == 0.f);
	}
	printf("pickup: ok\n");
}

static void test_weapon_handling(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(21u, 1, HCU_BOT_SKILL_NORMAL);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	assert(hcu_bot_init(&state, &c) == 0);
	world_init(&world, &tw);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon = 3;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].weapon_empty = 1;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].other_weapon = 5;
	hcu_bot_think(&state, &world, out);
	assert(out[0].swap == 1);
	assert(out[0].reload == 0);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].other_weapon = HCU_BOT_WEAPON_NONE_TEST;
	hcu_bot_think(&state, &world, out);
	assert(out[0].reload == 1);
	assert(out[0].swap == 0);
	printf("weapons: ok\n");
}

static void test_lifecycle(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(64u, 2, HCU_BOT_SKILL_HEROIC);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	float spawn[3] = { 1.f, 2.f, 3.f };
	uint64_t before;
	assert(hcu_bot_init(&state, &c) == 0);
	world_init(&world, &tw);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE, 0.f, 0.f, 0.f);
	set_pos(&world, HCU_BOT_PLAYER_SLOT_BASE + 1, 9.f, 0.f, 0.f);
	set_pos(&world, 0u, 4.f, 0.f, 0.f);
	hcu_bot_think(&state, &world, out);
	before = hcu_bot_hash(&state);
	hcu_bot_note_death(&state, 0u, HCU_BOT_PLAYER_SLOT_BASE + 1);
	assert(state.slots[0].alive == 0);
	assert(state.slots[0].deaths == 1);
	assert(state.slots[1].kills == 1);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].alive = 0;
	hcu_bot_think(&state, &world, out);
	assert(out[0].trigger == 0 && out[0].reload == 0 && out[0].melee == 0 && out[0].stick[0] == 0.f);
	assert(hcu_bot_hash(&state) != before);
	hcu_bot_note_spawn(&state, 0u, spawn);
	world.players[HCU_BOT_PLAYER_SLOT_BASE].alive = 1;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].pos[0] = 1.f;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].pos[1] = 2.f;
	world.players[HCU_BOT_PLAYER_SLOT_BASE].pos[2] = 3.f;
	assert(state.slots[0].spawns == 1);
	assert(state.slots[0].alive == 1);
	assert(state.slots[0].name == hcu_bot_name_index(64u, 0u)); /* a respawn keeps the name */
	printf("death/respawn: ok\n");
}

static void test_determinism(void)
{
	hcu_bot_state a, b, other;
	hcu_bot_config c = config(2026u, 4, HCU_BOT_SKILL_LEGENDARY);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	hcu_bot_action outb[HCU_BOT_MAX];
	uint32_t tick;
	int rocket = weapon_index("weapons\\rocket launcher\\rocket launcher");
	int assault = weapon_index("weapons\\assault rifle\\assault rifle");
	c.team_mode = 0;
	assert(hcu_bot_init(&a, &c) == 0);
	assert(hcu_bot_init(&b, &c) == 0);
	c.seed = 2027u;
	assert(hcu_bot_init(&other, &c) == 0);
	world_init(&world, &tw);
	for (tick = 0; tick < 300; tick++) {
		uint32_t k;
		/* A scripted world: players drift on fixed paths. Identical inputs must give identical hashes. */
		for (k = 0; k < HCU_BOT_PLAYER_SLOTS; k++) {
			world.players[k].alive = 1;
			world.players[k].pos[0] = (float)k * 3.f + (float)(tick % 17) * 0.05f;
			world.players[k].pos[1] = (float)(tick % 11) * 0.1f - (float)k;
			world.players[k].pos[2] = 0.f;
			world.players[k].weapon = (uint8_t)(k < HCU_BOT_PLAYER_SLOT_BASE ? 0xffu : (uint32_t)(k % 2 ? assault : rocket));
			world.players[k].weapon_empty = (uint8_t)(tick % 97 == 0 && k == HCU_BOT_PLAYER_SLOT_BASE);
		}
		world.pickups[0].valid = 1;
		world.pickups[0].weapon = (uint8_t)rocket;
		world.pickups[0].pos[0] = 4.f;
		hcu_bot_think(&a, &world, out);
		hcu_bot_think(&b, &world, outb);
		assert(memcmp(out, outb, sizeof out) == 0);
		assert(hcu_bot_hash(&a) == hcu_bot_hash(&b));
	}
	assert(hcu_bot_hash(&a) != hcu_bot_hash(&other));
	{
		uint64_t h = hcu_bot_hash(&a);
		a.slots[2].rng.state ^= 1u;
		assert(hcu_bot_hash(&a) != h);
		a.slots[2].rng.state ^= 1u;
		assert(hcu_bot_hash(&a) == h);
	}
	printf("determinism: ok\n");
	printf("hash: ok\n");
}

static void test_slots_and_no_bots(void)
{
	hcu_bot_state state;
	hcu_bot_config c = config(7u, 0, HCU_BOT_SKILL_NORMAL);
	hcu_bot_world world;
	test_world tw;
	hcu_bot_action out[HCU_BOT_MAX];
	assert(hcu_bot_init(&state, &c) == 0);
	world_init(&world, &tw);
	hcu_bot_think(&state, &world, out);
	assert(state.count == 0);
	assert(tw.path_calls == 0);
	printf("slots: ok\n");
}

int main(void)
{
	test_config();
	test_rng();
	test_roster();
	test_combat_and_fire_style();
	test_team_and_occlusion();
	test_weapon_handling();
	test_lifecycle();
	test_determinism();
	test_slots_and_no_bots();
	printf("hcu_bot tests passed\n");
	return 0;
}
