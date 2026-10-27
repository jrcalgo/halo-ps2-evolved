/* C5 population and team limits: the single source for every C5 module (hcu_bot, hcu_coop_modes,
 * hcu_local_setup, hcu_survival). Do not redefine these numbers elsewhere.
 *
 * Sources (docs/reports/, M4 C5 research, 2026-10-26):
 *   - Seats: CE has HALO_PORT_MAXIMUM_NETWORK_PLAYERS = 16 player datums on PS2
 *     (submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h:14). Humans and bots share them.
 *   - Machines: HALO_PORT_MAXIMUM_NETWORK_MACHINES = 4 on PS2 (halo_ps2_limits.h:15), and each machine holds
 *     MAXIMUM_LOCAL_PLAYERS = 4 players (players.c:508). Overflow calls system_exit (players.c:1190-1200), so
 *     the four local humans live on machine 0 and bots use machines 1-3 only (bots-core report, section 6).
 *   - Teams: CE gives every new player team_index = 1 (players.c:1265). The cooperative split puts the local
 *     humans on team 0 and bots on team 1, set explicitly for both team fields (modes report, section 3).
 *   - Survival: a swarm expands to at most 16 units (MAXIMUM_UNIT_INDICES_PER_SWARM, actors.h:266) and the PS2
 *     actor pool is 256 (HALO_PORT_MAXIMUM_ACTORS, halo_ps2_limits.h). Survival keeps a 64-actor margin
 *     (survival report, sections 2 and 6). */
#ifndef HALO_STREAM_HCU_C5_LIMITS_H
#define HALO_STREAM_HCU_C5_LIMITS_H

/* Player seats (humans + bots) on the PS2 build. */
#define HCU_C5_PLAYER_SEATS 16u

/* Local controller/view slots, all on machine 0 (CE MAXIMUM_LOCAL_PLAYERS). */
#define HCU_C5_LOCAL_HUMAN_SLOTS 4u

/* Bot seats: every seat that is not a local human. */
#define HCU_C5_BOT_SEATS_MAX (HCU_C5_PLAYER_SEATS - HCU_C5_LOCAL_HUMAN_SLOTS)

/* Machines and seats per machine. Bots take machines 1..HCU_C5_BOT_MACHINES, four seats each. */
#define HCU_C5_MACHINE_SEATS 4u
#define HCU_C5_BOT_MACHINES 3u

/* Team indices. Humans are team 0 and bots are team 1; CE's own default (players.c:1265) is 1 and is not
 * relied on. HCU_C5_TEAM_NONE marks a switch with no team split (individual play). */
#define HCU_C5_HUMAN_TEAM 0u
#define HCU_C5_BOT_TEAM 1u
#define HCU_C5_TEAM_NONE 0xffu

/* Survival population bounds (PS2 figures). */
#define HCU_C5_SWARM_MEMBERS_MAX 16u          /* worst units of one swarm (MAXIMUM_UNIT_INDICES_PER_SWARM) */
#define HCU_C5_SWARM_ACTIVE_LIMIT_MAX 12u     /* active enemies while any swarm is present: 12 x 16 = 192 */
#define HCU_C5_ACTOR_POOL_PS2 256u            /* HALO_PORT_MAXIMUM_ACTORS on PS2 */
#define HCU_C5_ACTOR_MARGIN 64u               /* actors kept free of survival reservations */
#define HCU_C5_ACTOR_RESERVE_MAX (HCU_C5_ACTOR_POOL_PS2 - HCU_C5_ACTOR_MARGIN) /* 192 */

/* Compile-time checks: a change to one of the numbers above must keep these true. */
typedef char hcu_c5_check_bot_seats[(HCU_C5_BOT_SEATS_MAX == HCU_C5_BOT_MACHINES * HCU_C5_MACHINE_SEATS) ? 1 : -1];
typedef char hcu_c5_check_machine_0[(HCU_C5_LOCAL_HUMAN_SLOTS <= HCU_C5_MACHINE_SEATS) ? 1 : -1];
typedef char hcu_c5_check_swarm_fit[(HCU_C5_SWARM_ACTIVE_LIMIT_MAX * HCU_C5_SWARM_MEMBERS_MAX <= HCU_C5_ACTOR_RESERVE_MAX) ? 1 : -1];

#endif /* HALO_STREAM_HCU_C5_LIMITS_H */
