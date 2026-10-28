# C3 primary weapon effect contract from retail CE — 2026-10-26

## Provenance and scope

Retail reference: `/home/ai/Documents/Halo/Halo - Combat Evolved.xiso.iso`, SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`. The checked map is `build/retail-maps/decompressed/bloodgulch.map`, SHA-256 `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`, as pinned by the R5 report. Tag paths/IDs and fields below were read from that map using its tag index and `Region` reader; schema/field interpretation is corroborated by the checked-in CE source. IDs are source-map tag IDs; runtime HCP remaps must be followed when making bindings.

## Primary firing effect roots and actual flash assets

Each weapon's trigger 0 firing-effects block (weapon tag `+0x308`, trigger block offset `+500`, firing effect reflexive at trigger `+264`) has one entry, shots lower/upper `1/1`. The six references are `effects[3]` for firing/overheated/empty and `damage_effects[3]`; the normal firing reference is slot 0. The primary projectile tag comes from trigger 0 projectile reference at `+148`.

| Weapon | WEAP tag | Trigger 0 primary projectile | Firing `effe` tag | Authored first-person flash particle(s) and event | Bitmap tag and image data |
|---|---|---|---|---|---|
| Pistol | `weapons\\pistol\\pistol` `0xe35001dc` | `weapons\\pistol\\bullet` `0xe3780204` | `weapons\\pistol\\effects\\fire bullet` `0xe3970223` | Event 1 (camera mode 1, first-person-only) has two side emitters `...\\flash h pistol side` `0xe39b0227` and a center emitter `...\\flash h pistol center` `0xe39d0229`, plus first-person smoke `effects\\particles\\air\\smoke h fp` `0xe34b01d7`. Event 0's muzzle/flash emitters are camera mode 2 (third-person-only). | Flash bitmap `effects\\particles\\flash\\bitmaps\\flash h pistol` `0xe39a0226`, 256×256 A1R5G5B5, 2 mip levels, images 0 and 1. Smoke bitmap `effects\\particles\\air\\bitmaps\\smoke tank cannon` `0xe23e00ca`, DXT3, image 0 128×128 and image 1 64×64. |
| Assault rifle | `weapons\\assault rifle\\assault rifle` `0xe26100ed` | `weapons\\assault rifle\\bullet` `0xe2a2012e` | `weapons\\assault rifle\\effects\\fire bullet` `0xe33b01c7` | Event 2 (camera mode 1, first-person-only) has six one-particle emitters of `effects\\particles\\flash\\flash h ar` `0xe33c01c8`; event 3 adds `...\\flash h ar center` `0xe34001cc`. The early events 0–1 are camera mode 2 (third-person-only). | AR flash bitmap `effects\\particles\\flash\\bitmaps\\flash h ar fp` `0xe33d01c9`, 256×256 A1R5G5B5, 2 mips, images 0 and 1. Center variant uses another element of this same bitmap group. |
| Sniper rifle | `weapons\\sniper rifle\\sniper rifle` `0xe6080494` | `weapons\\sniper rifle\\sniper bullet` `0xe63504c1` | `weapons\\sniper rifle\\effects\\fire bullet` `0xe65904e5` | Event 1 has three `flash h sniper muzzle break` emitters (`0xe65b04e7`) with camera mode 3 (both); three smoke emitters use the same mode. Event 0 is empty of particles. | Muzzle-break particle uses `effects\\particles\\flash\\bitmaps\\fire cloud` `0xe480030c`, 256×256 DXT1, 2 mips, images 0 and 1. |

The particle definitions provide the CE lifespan and rendering contract, not a universal quad size: pistol flash lifetime `0.075s`, radius bounds `1..1`, orientation mode 1; AR flash `0.075s`, bounds `1..1`, orientation 1; AR center flash `0.3s`, bounds `1..1`, orientation 0; sniper muzzle-break `0.1..0.2s`, fade-out `0.3s`, bounds `1..1`, orientation 0. These are `part` tag fields, and each firing emitter independently supplies environment, disposition, camera mode, location index, direction, particle count range, offset, and flags. The CE camera-mode enum is independent 0, first-person-only 1, third-person-only 2, both 3. The AR's first-person events 2–3 have varied directions and offsets; it is not a single muzzle quad. The pistol and sniper emitters likewise include several distinct effects with separate lifetimes and bitmaps.

The firing effect event is also used for ejection and sound. E.g. pistol event 0 `parts` includes pistol fire sound and eject sound at marker locations; its event 2 emits casing particle `effects\\particles\\solid\\casing h pistol` `0xe39e022a` for 10 seconds. A renderer must preserve event index and location index rather than flattening the whole `effe` datum to one representative bitmap.

## Plasma pistol projectile and effect (separate audit)

The earlier table is limited to human pistol, assault rifle and sniper rifle. It does not describe the user's initially visible plasma pistol. In the same pinned Blood Gulch map:

- `proj:weapons\\plasma pistol\\bolt` is `0xe6950521`; its base object `model` reference at tag-data offset `+0x28` is group `mode`, index `NONE`. It is a model-less projectile.
- `effe:weapons\\plasma pistol\\effects\\fire bolt` is `0xe6ab0537` (package output datum 764). Event 0 has seven `part` emitters with camera mode 1 (first-person only); event 1 has the same seven with camera mode 2 (third-person only). Each references live `part` datums: energy flash generic (1), generic-med (1 each, three emitters), smoke white generic (4–6), flash generic-small (1), and smoke white generic (8–12). Its event `parts` block contains sound only; the visible records are emitted through the event's `particles` block.
- The selected projectile dependencies also include `jpt!:weapons\\plasma pistol\\bolt` `0xe6990525`, `mgs2:weapons\\plasma pistol\\bolt` `0xe6980524`, and the authored bitmap `bitm:weapons\\plasma pistol\\bitmaps\\pistol charged contrail` `0xe6b50541`. The last is a bitmap tag, not a `cont` tag. Keep these separate from the `proj` and `effe` datum.

This explains the orange traveling square at source level: `effects.c:halo_ps2_fx_effects_each` publishes the EFFE scheduler datum as a generic request. Its bitmap resolver scans `event.parts` for particle-system parts but not `event.particles`; for this effect it resolves no bitmap. The parent `fx_pass` then draws the EFFE bookkeeping record with its flat orange fallback while CE independently publishes the live particles. The model-less PP bolt is not missing a CE projectile mesh.

The checked projectile model references for the other common weapons have the same distinction. Pistol bullet `0xe3780204`, AR bullet `0xe2a2012e`, shotgun pellet `0xe53503c1`, plasma-rifle bolt `0xe5850411`, and sniper bullet `0xe63504c1` have `model=NONE`. Rocket `0xe5e40470` references `weapons\\rocket launcher\\projectile\\projectile`; needler needle `0xe77f060b` references `weapons\\needler\\projectile\\projectile`. Thus only the latter two have source-defined traveling projectile meshes among these audited tags.

Halo-64's cross-platform object path independently documents that projectiles with neither model nor collision model (bullets, pellets, plasma bolts) have nothing to draw (`submodules/halo-64/source/objects/objects.c:1206`, source SHA-256 `4c81d6a4fed2c32a519cc29a6f6e267c9d74c7bf3383f45799c2159f6fc223d3`). This supports, but does not replace, the direct retail-tag evidence above.

## Impact and decal identity

The primary projectiles use material-response tables (33 entries). They do not share one impact effect or one decal. The selected response chooses a material-specific effect whose `effe` event may contain zero or more `deca` parts and multiple `part` emitters. Representative exact Blood Gulch mappings:

| Material category | Pistol effect | Assault-rifle effect | Sniper effect | Example CE decal part |
|---|---|---|---|---|
| Dirt / sand | Dirt `0xe37a0206` | Dirt `0xe2a70133`; sand `0xe2b2013e` | Dirt `0xe63804c4`; sand `0xe63904c5` | Dirt pistol-hole decal `effects\\decals\\bullet holes\\dirt pistol` (also used by AR/sniper dirt/sand) |
| Stone | `0xe37d0209` | `0xe2b50141` | `0xe63a04c6` | `effects\\decals\\bullet holes\\stone` |
| Snow | `0xe37f020b` | `0xe2c50151` | `0xe63c04c8` | `effects\\decals\\bullet holes\\snow` (AR/sniper) |
| Wood | `0xe380020c` | `0xe2d0015c` | `0xe63d04c9` | Wood effect has no decal part in its first event in the inspected tag; do not synthesize one. |
| Cyborg armor | `0xe38e021a` | `0xe31901a5` | `0xe64d04d9` | `effects\\decals\\blood splats\\blood splat small` and `blood splat` (weapon-specific event composition varies). |

The exact root is the projectile's `material_responses` block, not a global renderer alias. CE schemas define default/potential/detonation effect references per response; `projectile_collision` calls into the material response path in `source/items/projectiles.c`. The inspected pistol/AR/sniper roots point to their own corresponding material response tags. A complete implementation should preserve the resolved effect tag plus material response/event/part identity, then publish the actual spawned decal and particle datums. The sample rows above are examples, not the entire 33-material table.

No separate tracer bitmap reference was found in these three trigger 0 firing-effect entries or their hitscan-style primary projectile roots. The primary projectile tag is still the source for travel, damage, collision response and impact selection. Treat the existence and rendering of a dedicated tracer as unresolved until the exact projectile/fire-effect runtime references are audited; do not invent a tracer resource.

## CE semantics that the PS2 snapshot must preserve

- Trigger shot selection: `weapons.c` selects the trigger's firing-effect element according to its shots-lower/upper state, decrements shots remaining, and dispatches the `effects[effect_type]` tag through `weapon_effect_new`. The weapon firing effect is therefore tied to the actual weapon owner and CE event cadence, not just `c3_weapon_shots_fired`.
- Location attachment: `effect_new_from_object` / `effect_new_attached_from_markers` build one or more effect locations from object markers and, for a local player's first-person weapon, call `first_person_weapon_get_marker_by_name`. `effects.c` tags first-person locations with `_effect_location_first_person_bit` (bit 15) and later resolves their node matrices separately. Keep the per-location matrix/basis and first-person owner/local-player identity.
- Event expansion: `effect_generate_particles` walks every current-event `effect_particles_definition`, honors its disposition, location index, camera mode, time-integrated distribution/count, and makes actual `particle_datum`s. It also calls `effect_generate_parts` for parts such as decals, sounds, lights, and nested effects. Event phase/time and emitter/part index are needed to reproduce the live result.
- View visibility: `render_particles.c` filters live particles using local-player ownership and `dont_draw_first_person` / `dont_draw_third_person` flags, then sets `attached_to_first_person_weapon` for the local viewmodel case. The current PS2 record has no local-player index, these flags, sprite orientation/frame, color, direction/rotation, lifespan/fade, camera mode, or CE location orientation, so it cannot apply this rule.
- Decal orientation: CE decal datum includes surface forward/normal and bitmap index; a material-effect decal is placed by collision/contact semantics. Keep its surface-aligned plane, authored bitmap element, age, and owner/view eligibility. A camera billboard loses the surface relationship.

## Current implementation status and limits

The live-particle snapshot now carries CE flags, first-person owner, direction, color, orientation/rotation, lifespan/fade, sequence/frame, selected sprite bitmap element, sprite UV bounds and registration point. Parent rendering uses the CE-selected sprite and per-view eligibility rather than expanding an effect again. Decal requests now carry CE's already-updated `decal->intensity` alongside raw decal color and native geometry. Snapshot wire version is 11; the decal-specific union branch expands into existing union slack, so the fixed snapshot remains 90,592 B and the three banks remain 271,776 B.

The parent now treats EFFE records as diagnostics rather than drawable primitives. The current work adds CE linked contrail point segments with endpoint geometry, width/color interpolation, sequence/frame bitmap selection and scrolling U/V data. A v9 compile exposed that the CE contrail shader schema has fade mode but no blend-function field; the iterator now records alpha blending as the contrail default and publishes fade separately. The private v8 guest loaded Blood Gulch and reported the 3,812-byte FX descriptor cache and 278,212 bytes of frame-scratch use, but that ELF predates the current v9 blend/geometry changes. The first v9 link attempt caught a schema mismatch in that contrail field and is being rerun after correction. This is not guest-render qualification. Particle-system root/complex-sprite rendering, CE blend modes other than verified alpha/add/alpha-multiply-add, ground-mapped contrails, and material-decal captures remain unqualified; no all-guns visual parity or FPS A/B claim is made here.

## Retail shader modes checked for live FX

For the pinned Blood Gulch map, CE `particle_definition.shader` is the `shader_effect_definition` at particle tag offset `0xB0`; its `framebuffer_blend_function` and `framebuffer_fade_mode` are signed shorts at particle offsets `0xDA` and `0xDC` (shader-relative `0x2A`/`0x2C`). `contrail_shader` has no blend-function field: it stores only fade mode at contrail tag offset `0xB0`. `decal_definition.shader.framebuffer_blend_function` is at decal tag offset `0xC0`; `decal_shader_definition` has no fade-mode field. These schema positions match `particles.h`, `contrail_definitions.h`, `decals.c`, `shader_definitions.h`, and `tag_schema_render.c`.

| Live retail asset | Source datum | Blend enum | Fade enum |
|---|---:|---:|---:|
| Pistol side/center flash `flash h pistol side` / `flash h pistol center` | `0xe39b0227` / `0xe39d0229` | 3 (add) | 0 |
| AR muzzle flash `flash h ar` / `flash h ar center` | `0xe33c01c8` / `0xe34001cc` | 3 (add) | 0 |
| Sniper muzzle break | `0xe65b04e7` | 3 (add) | 0 |
| First-person pistol smoke | `0xe34b01d7` | 0 (alpha) | 0 |
| Plasma-pistol generic energy flash / medium flash / small flash | `0xe31b01a7` / `0xe30a0196` / `0xe5040390` | 3 (add) | 0 |
| Plasma-pistol white energy smoke | `0xe6a80534` | 3 (add) | 0 |
| Pistol and AR casings | `0xe39e022a` / `0xe34201ce` | 0 (alpha) | 0 |
| Plasma-rifle / rocket / needler contrails | `0xe4d70363` / `0xe5ea0476` / `0xe783060f` | alpha (contrail schema default) | 1 (fade when perpendicular) |
| Selected bullet-hole decals (dirt/stone/snow) | `0xe2a90135` / `0xe2b60142` / `0xe2c70153` | 2 (double multiply) | not defined |
| Blood splat decal | `0xe22e00ba` | 1 (multiply) | not defined |

Retail enumeration is alpha=0, multiply=1, double-multiply=2, add=3, subtract=4, component-min=5, component-max=6, alpha-multiply-add=7; fade is none=0, perpendicular=1, parallel=2. The data also contains live particle modes 6 (glass breakable) and 7 (ice) and decal modes 6 (selected blood decals), which need explicit GS support or an unsupported-mode count. Current PS2 bucket states only verify GS mappings for particle/decal modes 0, 3 and 7; modes 1, 2, 4, 5 and 6 are counted and visibly fall back to alpha. Therefore material-decal blend parity is explicitly incomplete.

## Evidence limits

This report establishes tag identities and serialized tag values for the pinned Blood Gulch map, and source contracts from checked-in CE/Halo-64 code. It is not a runtime capture of Xbox muzzle frames or PS2 parity. The R5 ISO/map digest binding applies only to this exact source map. Runtime captures and a matched firing FPS A/B are outstanding.
