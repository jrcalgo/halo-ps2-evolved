/* In-game scoreboard and pause list.
 * The retail widgets live in each multiplayer map (bloodgulch.map and the
 * others): ui\shell\multiplayer_game\pause_game\1p_pause_game,
 * 2p_pause_game and 4p_pause_game. Each is the dialog, the two-item list
 * RESUME GAME / LEAVE GAME, and the A/B button key. Select is Back, which
 * the scoreboard already treats as "hold to show" (Place, Name, and the
 * mode's score column). The widget drawer is not linked, and the Xbox text
 * path does not reach the GS, so this draws those same strings and positions
 * through the parent text batch. */
#include "stream/hcu_ingame_overlay.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* cseries and the game headers declare strnlen and random with the Xbox
 * signatures. newlib already declared them above; hide the Xbox names. */
#define strnlen halo_overlay_hide_strnlen
#define random halo_overlay_hide_random
#include "cseries.h"
#include "platform/video.h"
#include "game/game.h"
#include "game/game_engine.h"
#include "game/players.h"
#include "input/input.h"
#include "memory/data.h"
#undef strnlen
#undef random
#include <kernel.h>
#include <iopcontrol.h>
#include <loadfile.h>
#include <sifrpc.h>

#define SCORE_CAP 8

struct score_row {
	long index;
	long score;
	long team;
	int local;
	char name[13];
	char score_text[12];
};

struct pause_place {
	int space_w, space_h;
	int panel_x, panel_y, panel_w, panel_h;
	int row_x, row_w, row_h, row0_y, row1_y, text_x;
	int footer_x, footer_y;
};

static int s_primed;
static int s_pause;
static int s_row;
static int s_score;
static int s_held_pause;
static int s_prev_start, s_prev_a, s_prev_b, s_prev_up, s_prev_down;
static unsigned s_frame = 0xffffffffu;

static int scale_to(int value, int space, int view)
{
	if (space <= 0) return 0;
	return (int)((long)value * (long)view / (long)space);
}

static void narrow(char *dst, int dst_n, const wchar_t *src)
{
	int i = 0;
	if (dst_n <= 0) return;
	if (!src) {
		dst[0] = '\0';
		return;
	}
	while (i < dst_n - 1 && src[i]) {
		unsigned int c = (unsigned int)src[i];
		dst[i] = (c >= 32u && c < 127u) ? (char)c : '?';
		i++;
	}
	dst[i] = '\0';
}

static void overlay_print(text_batch_t *tb, int view_w, int view_h, int x, int y,
	uint32_t rgb, const char *text)
{
	text_batch_print(tb, x + VIDEO_WIDTH / 2 - view_w / 2,
		y + VIDEO_HEIGHT / 2 - view_h / 2, rgb, text);
}

static void overlay_fill(text_batch_t *tb, int view_w, int view_h, int x, int y,
	int w, int h, uint32_t rgba)
{
	text_batch_fill(tb, x + VIDEO_WIDTH / 2 - view_w / 2,
		y + VIDEO_HEIGHT / 2 - view_h / 2, w, h, rgba);
}

static const char *place_text(int place)
{
	static const char *const names[] = {
		"1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th",
		"9th", "10th", "11th", "12th", "13th", "14th", "15th", "16th"
	};
	if (place < 1) place = 1;
	if (place > 16) place = 16;
	return names[place - 1];
}

static void leave_game(void)
{
	static char elf[] = "cdrom0:\\HPS2_000.01;1";
	char *argv[1];
	argv[0] = elf;
	printf("HALO_PS2_LOCAL pause-leave %s\n", elf);
	fflush(stdout);
	SifInitRpc(0);
	SifIopReset("", 0);
	while (!SifIopSync()) {}
	SifInitRpc(0);
	SifLoadFileInit();
	LoadExecPS2(elf, 1, argv);
	printf("HALO_PS2_FAIL pause-leave returned\n");
}

/* Widget positions from the map's pause_game screens, in that screen's pixels. */
static void pause_place_for(int view_w, int view_h, struct pause_place *out)
{
	memset(out, 0, sizeof(*out));
	if (view_w * 2 <= VIDEO_WIDTH + 8 && view_h * 2 <= VIDEO_HEIGHT + 8) {
		/* 4p_pause_game is authored in a 320x240 pane. */
		out->space_w = 320; out->space_h = 240;
		out->panel_x = 46; out->panel_y = 46; out->panel_w = 226; out->panel_h = 159;
		out->row_x = 58; out->row_w = 202; out->row_h = 27;
		out->row0_y = 95; out->row1_y = 130; out->text_x = 66;
		out->footer_x = 75; out->footer_y = 180;
	} else if (view_h * 2 <= VIDEO_HEIGHT + 8) {
		/* 2p_pause_game is authored in a 640x240 pane. */
		out->space_w = 640; out->space_h = 240;
		out->panel_x = 206; out->panel_y = 52; out->panel_w = 226; out->panel_h = 159;
		out->row_x = 218; out->row_w = 202; out->row_h = 27;
		out->row0_y = 95; out->row1_y = 130; out->text_x = 226;
		out->footer_x = 235; out->footer_y = 186;
	} else {
		/* 1p_pause_game is authored in 640x480. */
		out->space_w = 640; out->space_h = 480;
		out->panel_x = 206; out->panel_y = 164; out->panel_w = 226; out->panel_h = 159;
		out->row_x = 218; out->row_w = 202; out->row_h = 27;
		out->row0_y = 207; out->row1_y = 242; out->text_x = 226;
		out->footer_x = 235; out->footer_y = 298;
	}
}

static int edge(int down, int *prev)
{
	int pressed = down && !*prev;
	*prev = down;
	return pressed;
}

static void read_pads(int *start, int *back, int *accept, int *cancel, int *up, int *down)
{
	int pad_index;
	*start = *back = *accept = *cancel = *up = *down = 0;
	for (pad_index = 0; pad_index < MAXIMUM_GAMEPADS; pad_index++) {
		const struct gamepad_state *pad = input_get_gamepad_state((short)pad_index);
		if (!pad) continue;
		if (pad->buttons[_gamepad_binary_button_start]) *start = 1;
		if (pad->buttons[_gamepad_binary_button_back]) *back = 1;
		if (pad->buttons[_gamepad_analog_button_a]) *accept = 1;
		if (pad->buttons[_gamepad_analog_button_b]) *cancel = 1;
		if (pad->buttons[_gamepad_binary_button_dpad_up] || pad->sticks[_gamepad_stick_left].y > 16000)
			*up = 1;
		if (pad->buttons[_gamepad_binary_button_dpad_down] || pad->sticks[_gamepad_stick_left].y < -16000)
			*down = 1;
	}
}

static void poll_overlay(void)
{
	int start, back, accept, cancel, up, down;
	if (!game_engine || !player_data || !player_data->valid || !player_data->data)
		return;
	read_pads(&start, &back, &accept, &cancel, &up, &down);
	if (!s_primed) {
		s_primed = 1;
		s_prev_start = start;
		s_prev_a = accept;
		s_prev_b = cancel;
		s_prev_up = up;
		s_prev_down = down;
		s_score = back;
		return;
	}
	s_score = back;
	if (edge(start, &s_prev_start)) {
		if (s_pause) {
			s_pause = 0;
		} else {
			s_pause = 1;
			s_row = 0;
		}
	}
	if (s_pause) {
		if (edge(up, &s_prev_up)) s_row = 0;
		if (edge(down, &s_prev_down)) s_row = 1;
		if (edge(cancel, &s_prev_b)) s_pause = 0;
		if (edge(accept, &s_prev_a)) {
			if (s_row == 0) s_pause = 0;
			else leave_game();
		}
	} else {
		s_prev_up = up;
		s_prev_down = down;
		s_prev_a = accept;
		s_prev_b = cancel;
	}
	if (game_time_initialized()) {
		if (s_pause) {
			game_time_set_paused(TRUE);
			s_held_pause = 1;
		} else if (s_held_pause) {
			game_time_set_paused(FALSE);
			s_held_pause = 0;
		}
	}
}

static int collect_rows(struct score_row *rows, int cap, int team_filter)
{
	struct data_iterator iterator;
	struct player_datum *player;
	int count = 0;
	data_iterator_new(&iterator, player_data);
	while ((player = (struct player_datum *)data_iterator_next(&iterator)) != NULL) {
		struct score_row *row;
		wchar_t score_wide[32];
		int i;
		if (player->quit_out_of_game) continue;
		if (team_filter >= 0 && player->team_index != team_filter) continue;
		if (count >= cap) continue;
		row = &rows[count];
		memset(row, 0, sizeof(*row));
		row->index = iterator.datum_index;
		row->team = player->team_index;
		row->local = player->local_player_index >= 0;
		narrow(row->name, (int)sizeof row->name, player->name);
		if (!row->name[0]) memcpy(row->name, "Player", 7);
		row->score = 0;
		if (game_engine->get_player_score)
			row->score = game_engine->get_player_score(row->index, _get_score_individual);
		score_wide[0] = 0;
		if (game_engine->format_player_score)
			game_engine->format_player_score(row->index, score_wide);
		narrow(row->score_text, (int)sizeof row->score_text, score_wide);
		if (!row->score_text[0])
			snprintf(row->score_text, sizeof row->score_text, "%ld", row->score);
		i = count;
		while (i > 0 && rows[i - 1].score < rows[i].score) {
			struct score_row swap = rows[i - 1];
			rows[i - 1] = rows[i];
			rows[i] = swap;
			i--;
		}
		count++;
	}
	return count;
}

static void draw_rows(text_batch_t *tb, int view_w, int view_h, int x, int y,
	const struct score_row *rows, int count, const char *score_header, int teams)
{
	char line[40];
	int i, place = 1;
	snprintf(line, sizeof line, "%-4s %-11s %s", "Place", "Name", score_header);
	overlay_print(tb, view_w, view_h, x, y, 0xB0B0B0u, line);
	for (i = 0; i < count; i++) {
		uint32_t rgb = 0xE8E8E8u;
		if (i > 0 && rows[i].score != rows[i - 1].score) place = i + 1;
		if (teams)
			rgb = rows[i].team == 0 ? 0xE05050u : 0x5080E8u;
		if (rows[i].local) rgb = 0xFFFFFFu;
		snprintf(line, sizeof line, "%-4s %-11s %s", place_text(place), rows[i].name, rows[i].score_text);
		overlay_print(tb, view_w, view_h, x, y + (i + 1) * TEXT_CELL_H, rgb, line);
	}
}

static void draw_scoreboard(text_batch_t *tb, int view_w, int view_h)
{
	struct score_row rows[SCORE_CAP];
	struct score_row red[SCORE_CAP];
	struct score_row blue[SCORE_CAP];
	wchar_t header_wide[32];
	char header[12];
	int teams = game_engine_has_teams();
	int wide = teams && view_w >= 400;
	int count = 0, red_n = 0, blue_n = 0, col_w, block_w, block_h, left, top, shown, title;
	header_wide[0] = 0;
	if (game_engine->format_score_name)
		game_engine->format_score_name(header_wide);
	narrow(header, (int)sizeof header, header_wide);
	if (!header[0]) memcpy(header, "Score", 6);
	if (wide) {
		red_n = collect_rows(red, SCORE_CAP, 0);
		blue_n = collect_rows(blue, SCORE_CAP, 1);
		shown = red_n > blue_n ? red_n : blue_n;
	} else {
		count = collect_rows(rows, SCORE_CAP, -1);
		shown = count;
	}
	if (shown <= 0) return;
	title = (teams && game_engine->get_player_score) ? TEXT_CELL_H : 0;
	col_w = 26 * TEXT_CELL_W;
	block_h = title + (shown + 1) * TEXT_CELL_H + 8;
	block_w = wide ? col_w * 2 + 16 : col_w;
	left = (view_w - block_w) / 2;
	top = (view_h - block_h) / 2;
	if (left < 4) left = 4;
	if (top < 4) top = 4;
	overlay_fill(tb, view_w, view_h, left - 4, top - 4, block_w + 8, block_h + 4, 0xC0081018u);
	if (teams && game_engine->get_player_score) {
		char title_text[24];
		snprintf(title_text, sizeof title_text, "Red %ld", game_engine_get_team_score(0));
		overlay_print(tb, view_w, view_h, left, top, 0xE05050u, title_text);
		snprintf(title_text, sizeof title_text, "Blue %ld", game_engine_get_team_score(1));
		overlay_print(tb, view_w, view_h, left + (wide ? col_w + 16 : 14 * TEXT_CELL_W),
			top, 0x5080E8u, title_text);
		top += TEXT_CELL_H;
	}
	if (wide) {
		draw_rows(tb, view_w, view_h, left, top, red, red_n, header, 1);
		draw_rows(tb, view_w, view_h, left + col_w + 16, top, blue, blue_n, header, 1);
	} else {
		draw_rows(tb, view_w, view_h, left, top, rows, count, header, teams);
	}
}

static void draw_pause(text_batch_t *tb, int view_w, int view_h)
{
	struct pause_place place;
	int x, y, w, h, row_y, text_y;
	const char *labels[2];
	int item;
	labels[0] = "RESUME GAME";
	labels[1] = "LEAVE GAME";
	pause_place_for(view_w, view_h, &place);
	x = scale_to(place.panel_x, place.space_w, view_w);
	y = scale_to(place.panel_y, place.space_h, view_h);
	w = scale_to(place.panel_w, place.space_w, view_w);
	h = scale_to(place.panel_h, place.space_h, view_h);
	if (w < 8) w = 8;
	if (h < 8) h = 8;
	overlay_fill(tb, view_w, view_h, x, y, w, h, 0xE0102038u);
	for (item = 0; item < 2; item++) {
		int raw_y = item == 0 ? place.row0_y : place.row1_y;
		row_y = scale_to(raw_y, place.space_h, view_h);
		if (item == s_row) {
			overlay_fill(tb, view_w, view_h,
				scale_to(place.row_x, place.space_w, view_w), row_y,
				scale_to(place.row_w, place.space_w, view_w),
				scale_to(place.row_h, place.space_h, view_h),
				0xC0305070u);
		}
		text_y = row_y + (scale_to(place.row_h, place.space_h, view_h) - TEXT_CELL_H) / 2;
		overlay_print(tb, view_w, view_h,
			scale_to(place.text_x, place.space_w, view_w), text_y,
			item == s_row ? 0xFFFFFFu : 0x9AA0A8u, labels[item]);
	}
	overlay_print(tb, view_w, view_h,
		scale_to(place.footer_x, place.space_w, view_w),
		scale_to(place.footer_y, place.space_h, view_h),
		0xC8C8C8u, "O =CANCEL   X =SELECT");
}

void hcu_ingame_overlay_draw(text_batch_t *tb, int view_w, int view_h,
	unsigned view_index, unsigned frame)
{
	int show_score;
	(void)view_index;
	if (!tb || view_w <= 0 || view_h <= 0) return;
	if (!game_engine || !player_data || !player_data->valid) return;
	if (frame != s_frame) {
		s_frame = frame;
		poll_overlay();
	}
	show_score = s_score;
	if (view_index == 0 && (s_pause || show_score)) {
		static int s_logged;
		if (!s_logged) {
			s_logged = 1;
			printf("HALO_PS2_LOCAL overlay score=%d pause=%d\n", show_score, s_pause);
		}
	}
	if (s_pause) draw_pause(tb, view_w, view_h);
	if (show_score) draw_scoreboard(tb, view_w, view_h);
}
