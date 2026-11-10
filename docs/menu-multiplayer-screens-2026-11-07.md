# Retail multiplayer screens in the PS2 menu (2026-11-07)

The PS2 multiplayer menu now follows the retail Xbox flow and uses the retail art from `ui.map`.

## Flow

Title -> **type list** -> controllers -> **map** -> **game type** -> lobby (enlisted players) -> start.

| Retail row | PS2 |
|---|---|
| QUICK START | removed (2026-11-10): it only replays a cooperative game, which this port does not have |
| COOPERATIVE PLAY | removed (2026-11-10): the port has no campaign |
| SPLIT SCREEN | controllers, map, game type, lobby |
| ONLINE (was SYSTEM LINK PLAY) | shown dim; not implemented yet |
| EDIT GAMETYPES | game type list, then the rules pages and SAVE GAME TYPE, no map or players needed |

Circle steps back one page. The cursor skips the dim ONLINE row. Cross now selects in the lobby; before, only Start did.

## Art

`tools/build_hcu_menu_assets.py` writes `halo_ce_mp_ui.bin` (magic `HMUI`, between the moon and the camera path in
`menu_textures.bin`). Headers and pictures are PSMT8 with one palette each, 415,760 bytes in all.

* Ten headers (384x48, retail 512x64 at 0.75): multiplayer, select profile, select map, select gametype, step 2 set game
  rules, rules, player options, item options, indicator options, enlisted players.
* Seven pictures (256x128): split screen, edit gametypes, and the rules, player, item, indicator and save pictures.
* VRAM: pages 230-282 plus the palette page 282; `MENU_TEXTURE_PAGES` is 283 of 288.
* A package without the `HMUI` block still works: pages fall back to text titles.

The map and game type pictures keep their art in the top-left 140x114 of the retail 256x128 bitmap. The atlas now crops to
that box, so the pictures fill their tile instead of showing black on the right.

## Not done

* The post-game carnage report (`postgame_carnage_report`, 1024x512) needs match results from the game, not the menu.
* The settings-side screens (profiles, controls) still use the old frame and text titles.
* The save-game-type page keeps a text title; no retail header fits it.
