# CE mod hook and script roots

Status: all five rooted mod hooks remain pending. The CE Linux-port implementation is not selected in the PS2 manifest, and no PS2 product decision or cache owner proves these calls safely ignorable.

## Behavior trace

`port/linux/game/mods.c` describes a local resource-pack layer: per-map mod files replace map tag definitions for strings, bitmaps, sounds, and models. It explicitly states simulation-critical tag data is not replaced, and network peers need not share the cosmetic/resource changes (`mods.c:1-26`). That still means the mod hooks are persistent tag/cache state, not merely console output.

| Root | CE behavior | Unresolved PS2 risk |
|---|---|---|
| `mods_tags_loaded` | Records map identity/enabled state, refreshes discovery generation, and applies available replacement assets (`mods.c:238-269`). | Requires bounded map-owned replacement state and correct ordering after tag instances are installed. |
| `mods_tags_unloaded` | Calls `mods_let_go(TRUE)`, which tears down sound/bitmap/model/string replacement state and restores map model definitions (`mods.c:272-295`). | Must run after texture/sound cache close but before map tag removal; skipping can retain pointers or modified definitions across maps. |
| `mods_enable` | Toggles active state, rescans when enabling, restores or reapplies mod definitions (`mods.c:344-362`). | Script-visible mutation of what content is played; must be supported intentionally or excluded with a script/profile proof. |
| `mods_reload` | Rescans and updates replacement resources for the loaded map, with console status (`mods.c:301-320`). | Reload changes active content and cache ownership; no safe empty fallback established. |
| `mods_list` | Enumerates installed mods and reports active counts/state to console (`mods.c:364-407`). | Primarily diagnostic, but needs a concrete PS2 discovery provider or an explicit unsupported-command result; do not report success with fabricated empty state. |

The manifest contains no `mods.c`/mod-resource provider selection (`port/ps2/port.json`), while `source/cache/cache_files.c` calls `mods_tags_loaded` in both the UI/menu map path and ordinary map path and calls `mods_tags_unloaded` during scenario teardown (`cache_files.c:631-633,1249-1251,1360-1362`). Therefore, a blanket no-op means no resource mods even if future PS2 campaign packages contain such files. User product goals include CE mod/campaign compatibility, so this feature boundary should be resolved before M0 closure rather than silently categorized as excluded.

## Required disposition evidence

1. Decide whether PS2 supports the CE Linux-port resource override format, and distinguish it from loading an entire Custom Edition campaign/tag cache.
2. If retained, implement a PS2 path-provider and bounded resource caches; test map->UI->map transitions, enable/disable, reload during a loaded map, malformed assets, and map-tag restoration.
3. If deliberately excluded at this stage, prove the runtime/HS exposure is disabled or returns a specific unsupported result and record the product-scope decision. Do not equate `mods_list`'s informational role with the other four stateful hooks.
4. Validate the actual teardown ordering against `scenario_tags_unload`: sound and texture cache closure precede mod release, then map-tag deregistration follows.

## Sources

- `submodules/halo-ce-universal/port/linux/game/mods.c:1-26,238-320,344-407`
- `submodules/halo-ce-universal/source/cache/cache_files.c:612-645,1238-1253,1355-1365`
- `submodules/halo-ce-universal/source/hs/hs.c:11707-11748,12188-12190`
- `submodules/halo-ce-universal/port/ps2/port.json`
- Rooted identities: `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
