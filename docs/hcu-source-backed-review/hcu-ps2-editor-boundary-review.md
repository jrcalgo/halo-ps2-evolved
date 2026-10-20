# M0 source review: editor lifecycle and `game_in_editor`

## Dispositions

Six editor lifecycle hooks are `excluded-proven` for the PS2 local-game profile: `editor_initialize`, `editor_dispose`, `editor_update`, `editor_initialize_for_new_map`, `editor_dispose_from_old_map`, and `editor_should_exit`. The PS2 manifest excludes `source/editor/`, and the CE-provided non-editor `source/editor/editor_stubs.c` implements these exact lifecycle functions as empty bodies or `FALSE` (`:31-66`). The generated platform bodies match those definitions. Their exclusion is narrow: the platform still owns all normal game, map, object, AI, input, and renderer lifecycle calls around them.

`game_in_editor` remains **pending**, not excluded. The CE non-editor stub returns false, but this boolean has a much wider semantic role than the lifecycle hooks: the rooted callers branch object placement/disposal, AI placement and encounter activation, player spawning, effect allocation, director mode, combined PVS, collision logging, map-name/menu behavior, and editor-versus-game camera behavior on it. The generated zero matches expected non-editor operation, but it lacks an explicit PS2-owned state contract and an integrated campaign/map fixture. This is one of the cases where the obvious false value should not be promoted into an approved adapter without evidence.

## Source evidence

The product manifest excludes `source/editor/` (`port/ps2/port.json:39`). The source stubs are exact: editor init/dispose/update and per-map lifecycle calls return immediately, while `editor_should_exit` and `game_in_editor` return false. Their generated PS2 bodies are in `build/hcu-ps2-closure/all/ps2_platform.c:222-230`.

The live `game_in_editor` callers are not confined to editor code. Examples: `game_initialize_for_new_map` runs `ai_place()` only when not in editor (`source/game/game.c:712`); `object_types_place_objects` and `object_types_place_all` gate normal scenario object placement (`source/objects/object_types.c:1049,1183`); `encounters.c:4079-4110` treats editor mode as forcing encounter activation; `effects.c:1498` gates effect allocation; `players.c:1805,4802` changes local player setup/respawn; `main.c:3438-3473` sets initial map/menu state; and `director.c:531,958` chooses editor camera/mode. The false local profile is likely right, but these edges need one tested game-load fixture before the state adapter is approved.

## Regression guard

The new test confirms the six generated lifecycle bodies match CE's stub contract and the manifest still excludes the editor subsystem. A separate assertion locks `game_in_editor` to pending and verifies representative AI/object/player/main consumers remain in the source audit. It does not claim that a map/campaign has been loaded through these branches.
