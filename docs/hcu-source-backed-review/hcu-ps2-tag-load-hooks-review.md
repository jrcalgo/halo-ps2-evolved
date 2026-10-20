# CE map tag-load hook review

Status: source-traced; all six rooted hooks remain pending M0 disposition.

## Rooted boundary

The exact closure ledger roots these hooks from `scenario_tags_load` and `scenario_tags_unload` in `source/cache/cache_files.c`. The HCU cache path calls them after tag instances are registered and before map load returns (`source/cache/cache_files.c:1332-1353`); unload calls the high-resolution HUD hook before texture-cache close and the menu hook after texture-cache close but before map tag instances are deregistered (`source/cache/cache_files.c:612-645`). Ordering is semantically relevant: these are not interchangeable no-ops.

## Hook semantics and unresolved PS2 owners

| Hook | CE implementation/effect | Why it remains pending |
|---|---|---|
| `hud_hires_tags_loaded` | `port/linux/game/hud_hires_tags.c:138-204` clears and rebuilds per-map bitmap/upscale/sprite lookup tables from loaded tags. | PS2 has no proven high-resolution HUD asset adapter. Omitting it may be safe only if these Linux-port enhancements are excluded and no surviving consumer reads the tables. |
| `hud_hires_tags_unloaded` | `hud_hires_tags.c:216-224` clears lookup counts and forgets sprite placeholders. | Must pair with tag/cache teardown if the corresponding load behavior is retained; stale bitmap pointers are unsafe across map transitions. |
| `menu_tags_loaded` | `port/linux/game/menu_tags.c:2070-2204` conditionally parses PC menu data, allocates arrays, synthesizes tags/widgets, and applies pause/settings patches. | This is PC-menu enhancement state, but can create map tags and changes settings/pause UI. Need explicit PS2 product decision and memory-bounded behavior or a proven unreachable profile. |
| `menu_tags_unloaded` | `menu_tags.c:2216-2219` releases generated menu tags/blocks when loaded. | Lifecycle pairing and cache teardown ordering must be preserved if menu injection is included. |
| `pal_tags_loaded` | `port/linux/game/pal_tags.c:367-390` clears PAL timing state, detects map build region, and rewrites biped/global/weapon/projectile/Warthog tag values for NTSC timing. | This affects first-person animation cadence and gameplay tag values for PAL maps; it cannot be dropped as drawing-only without deciding PAL support and adding parity tests. |
| `powerup_render_bounds_tags_loaded` | `port/linux/game/powerup_render_bounds.c:163-187` iterates equipment tags and enlarges overshield/active-camo render bounds from rigid model geometry. | Changes rendered bounds and may affect visibility/culling. Requires model/BSP owner and a fixture proving bounds and allocation/runtime cost. |

These functions live in the Linux port tree, not in the selected HCU `source/` manifest. The generated PS2 bodies therefore represent omitted port-layer behavior, not evidence that upstream HCU requires these features. Conversely, their source-visible effects prevent treating every hook as harmless: PAL rewriting and menu tag synthesis are state changes; HUD caches retain map-owned pointers; powerup bounds affect culling. The immediate M0 action is to record exact product-profile ownership for each and retain pending status until a negative/positive fixture establishes the choice.

## Acceptance needed to disposition

1. Add source-pinned tests verifying scenario load/unload call order around tag registration and texture-cache close.
2. Decide whether the PS2 target supports PC menu injection, PAL-map timing compensation, and high-resolution HUD replacements. For excluded features, prove the selected PS2 profile cannot enable their consumers and check map-transition cleanup; for retained features, implement bounded state and test it.
3. For PAL support, compare rewritten tag values and first-person frame advancement against CE for representative NTSC/PAL maps. For powerups, compare computed rigid-model radius with the original radius and validate visibility/culling in an integrated map fixture.
4. Pin the exact HCU source revision and regenerate the rooted external set before approval; this report alone does not approve a stub.

## Sources

- `submodules/halo-ce-universal/source/cache/cache_files.c:612-645,1332-1353`
- `submodules/halo-ce-universal/port/linux/game/hud_hires_tags.c:138-224`
- `submodules/halo-ce-universal/port/linux/game/menu_tags.c:2070-2219`
- `submodules/halo-ce-universal/port/linux/game/pal_tags.c:367-390`
- `submodules/halo-ce-universal/port/linux/game/powerup_render_bounds.c:163-187`
- Rooted caller attribution: `docs/hcu-ps2-external-review.json`
