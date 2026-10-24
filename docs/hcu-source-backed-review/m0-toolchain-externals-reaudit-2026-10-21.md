# M0 report-only review: 41 pending toolchain externals

Date: 2026-10-21. This is a source/provider audit of exactly the 41 rows in
`hcu-ps2-external-review.json` whose current classification is `toolchain` and
disposition is `pending`. It recommends dispositions; it does not approve rows
or modify the ledger, source, plan, or build.

## Exact evidence identity

Reviewed closure: `build/hcu-ps2-closure/all-no-bootstrap-memory/`.

| Artifact/input | Identity |
|---|---|
| `rooted.o` | SHA-256 `cdbc2a9638054143608a50d3d18576411186840990bc2842df8cdcf6e710eaf8` |
| `result.json` | SHA-256 `84ec8b79e0246929adeac76d8e260dc98b4f8516943e933460478e20974a7846` |
| ledger | SHA-256 `f5444737dafe78854cd895d357c26f1e2e60e71df2e4b8ca3c96c5d1273933f5` |
| map / linked diagnostic ELF | `halo-local.map` SHA-256 `af9ad46da71867951533b23c7705d76c173a8b736a59313f39f0d0f858766bf2`; `halo-local.elf` SHA-256 `4e1f9aecb52165531b380d4a9d955789166014cd3bbc5799af5a46fdac888ef2` |
| closure totals | 370 compiled units, 0 failed units, 341 selected sources, 322 rooted live externals |
| HCU source pin | `submodules/halo-ce-universal` HEAD `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| toolchain source pins | EE GCC `df77d03bc1bd5765b40de554918a5ff541202548`; Newlib `8881dc4b138f0561596980ac9a481c7e638aebd0`; see `config/toolchain-sources.json` |
| archive identity | `libgcc.a` SHA-256 `301ee093e36867ebbabf460745a881548d4d68f457828033dada6d1079549046`; EE `libc.a` SHA-256 `24ff16cd8a2cfbdd8960699b173bdc21fadc51f2df1cc2ff0fc433a4b745b51b`; EE `libm.a` SHA-256 `b7069a907b2d5b332246604d4c52433a14b816e50aca38d80f60fc7991a7f4bc` |
| project CRT provider | `port/ps2/src/ps2_crt.c`, object SHA-256 `3ba5347155f0053356646abbb5cfcde0f714a4b54abff031d458d83c11333e54` |

The ledger root equals the requested `rooted.o` hash. I compared the 41
ledger caller-section arrays to the corresponding `result.json` rooted
externals: 41/41 exact matches, no missing names. I recalculated all caller
source hashes against the pinned HCU checkout: 0 missing files and 0 hash
mismatches. The link map confirms the selected archive members below; the
PS2 CRT symbols resolve to `ps2_crt.o`. These checks establish provenance and
selection, not behavioral equivalence. `halo-local.elf` is the macro-free,
no-bootstrap closure diagnostic, not proof of a playable production image.

## Row-by-row audit

The caller examples below are exact rooted function names; the authoritative
complete caller section/source/hash sets remain in the JSON ledger and
`result.json`. Provider abbreviations: `GCC` is the named `libgcc.a` member,
`Newlib` is the named EE `libc.a`/`libm.a` member in the map, and `CRT` is the
PS2 `ps2_crt.o` implementation. “Pure candidate” means a normal deterministic
library contract is plausible; it does not waive CE call-site bounds,
ordering, floating-point, or cadence checks. Every row remains pending.

| Symbol | Selected PS2 provider | Rooted callers (count; representative exact callers) | Recommended disposition/evidence still needed |
|---|---|---|---|
| `__adddf3` | GCC `_addsub_df.o` | 6: `object_new`, `vehicle_update`, `unit_grenade_throw_keep_legs_moving`, `render_camera_build_frustum` | Keep pending; IEEE double edge vectors plus deterministic gameplay/collision comparison. |
| `__divdf3` | GCC `_div_df.o` | 12: `biped_update_physics`, `collision_test_vector`, `physics_update_new`, `main_loop` | Keep pending; zero, subnormal, overflow, NaN and signed-zero cases; measure hot EE callers. |
| `__extendsfdf2` | GCC `_sf_to_df.o` | 240: AI, animation, physics, collision, weapons, effects and camera paths (`actor_combat_update`, `biped_update`, `projectile_update`) | Keep pending; ubiquitous source promotion means a broad parity/cost gate, not a one-function smoke test. |
| `__fixdfsi` | GCC `_df_to_si.o` | 4: `fast_ftol`, `real_a_rgb_color_to_pixel32`, `real_argb_color_to_pixel32`, `dsound_volume_from_gain` | Keep pending; integer conversion boundaries/rounding and exact color/gain vectors. |
| `__floatdidf` | GCC `_floatdidf.o` | 1: `main_loop` | Keep pending; 64-bit tick/time conversion precision and range vectors. |
| `__floatdisf` | GCC `_floatdisf.o` | 2: `main_loop`, `object_compute_function_values` | Keep pending; large integer narrowing and source-order parity vectors. |
| `__gtdf2` | GCC `_gt_df.o` | 5: `evaluate_piecewise_linear_function`, `item_align_to_normal_and_point`, `unit_ping_animation` | Keep pending; ordered/unordered comparisons including NaN and boundary values. |
| `__muldf3` | GCC `_mul_df.o` | 15: `physics_compute_new`, `physics_update`, `bsp3d_test_pill_recursive`, `vehicle_update` | Keep pending; IEEE edge vectors and EE cost on simulation/collision hot paths. |
| `__truncdfsf2` | GCC `_df_to_sf.o` | 163: `biped_update_physics`, `collision_test_vector`, `projectile_update`, `vehicle_update` and broad AI/render/math paths | Keep pending; narrowing/overflow/subnormal vectors and state-hash comparisons. Do not replace with single-precision math absent parity evidence. |
| `_snprintf` | CRT `ps2_crt.o` → Newlib `vsnprintf` | 13: `unit_describe_speech`, `ai_debug_describe_actor`, `create_mutex`, `input_abstraction_update` | Keep pending; test CE/MSVC truncation and return-count contract, NUL termination, count 0/1, formats, and caller buffer offsets. `source/input/input_xbox.c:663-675` is a live bounded text path; `port/ps2/src/ps2_crt.c:48-57` forwards to Newlib. |
| `_stricmp` | CRT `ps2_crt.o` | 27: `ai_index_from_string`, `alphabetize`, `unit_describe_speech`, animation/name lookup | Candidate pure contract test; ASCII-only fold is intentional in [`ps2_crt.c:10-27`](../../submodules/halo-ce-universal/port/ps2/src/ps2_crt.c#L10); verify high-bit bytes, null/empty inputs per callers, and compare CE ordering/name lookup. |
| `_strnicmp` | CRT `ps2_crt.o` | 4: `encounter_definition_get_platoon_by_name`, `encounter_definition_get_squad_by_name`, `hs_tokens_enumerate_add_string` | Candidate pure contract test; see [`ps2_crt.c:30-40`](../../submodules/halo-ce-universal/port/ps2/src/ps2_crt.c#L30); verify `count==0`, early NUL, prefix equality, high bytes, and CE token/identifier lookup. |
| `acos` | Newlib `libm_a-w_acos.o` | 10: `actor_move_update`, `aim_assist_compute_target`, `angle_between_normals3d` | Keep pending; domain/NaN/infinity and near-endpoint vectors plus simulation parity/cost. |
| `atan2` | Newlib `libm_a-w_atan2.o` | 16: `actor_visibility_at_point`, `convex_hull2d`, `euler_angles2d_from_vector3d`, teleporter logic | Keep pending; all quadrants, signed zeros, axes, infinities and NaNs; angle wrap impacts aim/camera/gameplay. |
| `cos` | Newlib `libm_a-s_cos.o` | 47: `actor_move_update`, `matrix4x3_rotation_from_angles`, `projectile_update`, `vehicle_update` | Keep pending; canonical-angle/large-angle accuracy and repeated-transform parity; hot-path profile. |
| `exit` | Newlib `libc_a-exit.o` | 1: `halt_and_catch_fire` | Keep pending and treat as fatal-control-flow, not harmless library code. CE `halt_and_catch_fire` runs its fatal loop and then calls `exit(0)` at [`main.c:3149-3288`](../../submodules/halo-ce-universal/source/main/main.c#L3149); prove no return/resume after fatal, cleanup/termination behavior and controlled guest diagnostic. |
| `fclose` | Newlib `libc_a-fclose.o` | 11: `cheats_load`, `console_startup`, `debug_dump_memory_by_file`, `director_load_camera` | Keep pending; real descriptor release, flush/error propagation, invalid/double close and repeat cycles on every storage profile. For an active write/read path see [`objects.c:979-1033`](../../submodules/halo-ce-universal/source/objects/objects.c#L979). |
| `fflush` | Newlib `libc_a-fflush.o` | 4: `build_structure_lens_flares`, `game_state_allocation_record`, `main_frame_rate_debug`, `write_to_error_file` | Keep pending; it mutates/flushes stream state and may fail; verify target sink, close interaction and failure reporting. A periodic file flush is in [`profile.c:1888-1889`](../../submodules/halo-ce-universal/source/cseries/profile.c#L1888). |
| `floor` | Newlib `libm_a-s_floor.o` | 13: `animation_get_keyframe_rotation`, `animation_get_keyframe_translation`, `breakable_surface_effect` | Keep pending; negative integer boundaries, signed zero, NaN/infinity and animation/effect tick parity. |
| `fmod` | Newlib `libm_a-w_fmod.o` | 12: `aiming_screen_apply`, `first_person_weapons_update`, `glow_time_wrap_down`, `object_compute_function_values` | Keep pending; sign-of-dividend, zero divisor, infinities/NaN and periodic animation/HUD wrap behavior. |
| `fopen` | Newlib `libc_a-fopen.o` → `_open_r`/PS2SDK FileIO | 12: `cheats_load`, `console_startup`, `director_load_camera`, `main_load_last_solo_map` | Keep pending; active I/O and paths/modes. `main_load_last_solo_map` opens `z:\last_solo.txt` for read at [`main.c:1887-1913`](../../submodules/halo-ce-universal/source/main/main.c#L1887). Audit CE `d:\`/`z:\`/relative roots, read/write/append, OPL/optical mounts, failed-open guards and descriptor exhaustion. This is distinct from the bounded read-only parent cache bridge. |
| `fprintf` | Newlib `libc_a-fprintf.o` | 9: `debug_dump_memory_by_file`, `director_save_camera`, `game_state_allocation_record`, `hs_doc` | Keep pending; file sink/format/truncation/write failure. `hs_doc` and debug dump callers need failed-open audit; no evidence from stdout tests. |
| `fputc` | Newlib `libc_a-fputc.o` | 1: `objects_dump_memory` | Keep pending; verify returned byte/error and stream state in the same file-output lifecycle. |
| `fputs` | Newlib `libc_a-fputs.o` | 2: `build_structure_lens_flares`, `objects_dump_memory` | Keep pending; test full write/error, no implicit newline and proper error propagation. |
| `fread` | Newlib `libc_a-fread.o` | 1: `main_load_last_solo_map` | Keep pending; short read/EOF/error, record validation and path selection can change startup’s selected map. The fixed 256-byte local buffer, 255-byte read, close, and NUL termination are visible at [`main.c:1890-1906`](../../submodules/halo-ce-universal/source/main/main.c#L1890). |
| `memchr` | Newlib `libc_a-memchr.o` | 4: `cache_file_header_verify`, `string_valid`, `validate_fields`, `validation_message` | Candidate pure byte-search contract test; include NUL/high-byte, zero count, no-match and exact end boundary; validate each caller length. |
| `memcmp` | Newlib `libc_a-memcmp.o` | 5: `csmemcmp`, `ps2_cbsp_open_parts`, `ps2_ctag_open`, `ps2_ctag_open_parts`, `ps2_input_publish_state` | Candidate pure byte-order contract test, but keep pending until exact lengths are bounded and the ledger/report conflict with older “approved” memory review is reconciled. Include byte values >127 and zero count. |
| `memcpy` | Newlib `libc_a-memcpy.o` | 136: includes `XInputGetState`, AI actions, render and data conversion/copy callers | Keep pending; implementation is not `memmove`. CE’s wrapper simply forwards at [`cseries.c:596-605`](../../submodules/halo-ce-universal/source/cseries/cseries.c#L596); prove non-overlap and valid byte counts for every rooted call site or fix unsafe callers; prioritize input snapshots and stateful structures. |
| `memset` | Newlib `libc_a-memset.o` | 40: game-variant builders, `XInputGetState`, cache/tag open and PS2 input publication | Candidate pure fill contract test; verify byte conversion and exact extents for state init/clear. Keep pending until old approval claims are reconciled with the current-root row. |
| `printf` | Newlib `libc_a-printf.o` | 10: `cache_file_open`, `cache_file_read`, `display_assert`, `halt_and_catch_fire`, `shell_initialize` | Keep pending; stdout routing/flush/format and assertion/fatal diagnostics must be observable on target; not interchangeable with `fprintf`. |
| `puts` | Newlib `libc_a-puts.o` | 7: `game_load`, `game_precache_new_map`, `halo_shell_main`, `main_load_ui_scenario` | Keep pending; prove stdout sink, appended newline, and visible failure/status messages in guest. |
| `qsort` | Newlib `libc_a-qsort.o` | 12: `actor_perception_update`, `aim_assist`, `create_local_players`, `hs_rebuild_source` | Keep pending; audit comparators for strict ordering/tie behavior and whether equal-key order influences AI target choice, aim assist, player order or script output. Object dump sorting is explicit at [`objects.c:979-984`](../../submodules/halo-ce-universal/source/objects/objects.c#L979); verify in-place bounds and target stack usage. |
| `rint` | Newlib `libm_a-s_rint.o` | 3: `fast_ftol`, `real_a_rgb_color_to_pixel32`, `real_argb_color_to_pixel32` | Keep pending; test current EE rounding mode and half-way, negative, saturation/NaN cases; color and integer conversions are observable. |
| `sin` | Newlib `libm_a-s_sin.o` | 45: `actor_move_update`, `matrix4x3_rotation_from_angles`, `projectile_update`, `vehicle_update` | Keep pending; range-reduction and accuracy for large angles, determinism, hot simulation cost and source-parity transform vectors. |
| `snprintf` | Newlib `libc_a-snprintf.o` | 9: `hs_compile_and_evaluate_command`, `hs_inspect_string`, `object_new`, `validation_message` | Keep pending; format subset, `%` types, truncation, NUL and required-length return; audit the capacities/offsets of all destinations. |
| `sprintf` | Newlib `libc_a-sprintf.o` | 44: HaloScript parsing/inspection, AI descriptions, `game_state_read_core`, `dsound_end_scene` | Keep pending; unbounded API plus caller-owned buffers and format ABI make this unsafe until destination-size proofs or bounded replacements are reviewed. |
| `sqrt` | Newlib `libm_a-w_sqrt.o` | 66: `biped_update_physics`, `collision_*`, `distance3d`, AI/pathfinding, `projectile_aim_ballistic` | Keep pending; zero/negative/subnormal/large inputs and numerical parity; profile EE collision/AI hot paths. Do not assume hardware single-precision substitution. |
| `strchr` | Newlib `libc_a-strchr.o` | 6: `double_byte_character`, `error`, `hs_compile_and_evaluate_command`, `unit_describe_speech` | Candidate pure contract test; test search for NUL, signed/high byte conversion and NUL-terminated input bounds. |
| `strcpy` | Newlib `libc_a-strcpy.o` | 5: `ai_communication_event`, `dsound_end_scene`, `hs_inspect_boolean`, `interrupt_time_error` | Keep pending; unbounded copy, inspect each destination capacity and overlapping/invalid-input assumptions; provider identity cannot establish memory safety. |
| `strrchr` | Newlib `libc_a-strrchr.o` | 9: `ai_index_from_string`, `console_complete`, `tag_name_strip_path`, `object_cause_damage` | Candidate pure contract test only after caller bounds; cover searching NUL, no match, repeated separators and path-root interpretation. |
| `strstr` | Newlib `libc_a-strstr.o` | 14: `ai_debug_update`, `game_engine_variant_vehicle_type`, `main_get_solo_level_from_name`, `vehicle_scripting_find_available_seats` | Candidate pure contract test; verify case-sensitive substring semantics and caller interpretation, especially name/path selection. |

## Findings that affect M0 disposition

1. **Pure algorithms are lower-risk, not self-approving.** `memchr`, `memcmp`,
   `memset`, bounded string searches and the conversion helpers can be tested
   as deterministic contracts. `memcpy`, `strcpy`, and `sprintf` are unsafe to
   approve from archive identity because their APIs assume caller-owned
   lengths/capacities. `qsort` is pure in isolation but ordering/ties are
   behaviorally significant in AI and aim selection.
2. **The nine software-double helpers are active gameplay/render dependencies.**
   Current roots show 240 `__extendsfdf2` caller functions and 163
   `__truncdfsf2`; `__adddf3`, `__muldf3`, and `__divdf3` reach collision,
   movement, vehicles, and camera. This is evidence to preserve source numeric
   semantics and measure EE cost, not permission to substitute float math.
3. **stdio has machine state and path policy.** Newlib `FILE` operations resolve
   below stdio to `_open_r`/PS2SDK FileIO, not the parent’s fixed-slot
   read-only cache reader. The live CE roots include `d:\`/relative-file
   behavior and writes/appends. OPL mounts and path translation, error
   handling, descriptor lifetime, and stdout routing require guest tests.
4. **Fatal exit is control flow.** `exit` has one rooted CE caller,
   `halt_and_catch_fire`; its contract must terminate/fail-stop and must never
   return into corrupted simulation.
5. **Cross-report status conflict exists.** Current-root `memcmp` and `memset`
   are pending while older `hcu-ps2-libc-memory-review.md` says approved.
   Treat it as a refresh/reconciliation issue. This report does not authorize
   restoring the earlier state without root-matched tests.

## Recommended test package before any row is approved

- Add a rooted-symbol regression binding this report/ledger to the exact root
  hash and checking all 41 exact caller sets and source hashes on refresh.
- For `libgcc`/`libm`, run target-compiled deterministic vectors for IEEE edge
  cases and representative CE routines (movement, collision, projectile,
  color, animation), then compare fixed-tick state/results to the source
  oracle. Include an EE cycle budget for the hot math callers.
- For byte/string/memory/sort routines, exercise zero length/count, boundaries,
  high-bit bytes, overlap preconditions, comparator ties, and CE call-site
  buffer-size invariants. Add exhaustive caller-bound evidence for
  `memcpy`/`strcpy`/`sprintf`.
- For stdio and stdout, use guest tests on each supported optical and OPL
  storage profile; include failed open, short read/write, EOF, flush, close,
  repeated open/close, descriptor exhaustion, append, unsupported Xbox paths,
  and observable logging. A host fake alone cannot qualify mounted devices.
- Exercise `exit` in an isolated guest test that records the fatal marker and
  proves no gameplay tick or return path follows.

No implementation or test suite was modified. The audit itself used artifact
hashing, a programmatic comparison of all caller/source metadata, and
inspection of the combined link map, PS2 CRT, and representative rooted HCU
callers. I also ran `python3 -m pytest -q tests/test_hcu_external_review.py`:
it reports 59 failed and 16 passed. Multiple failures show that this test file
still expects older toolchain rows (including several arithmetic and memory
helpers) to be `implemented`, while the current-root ledger correctly has
refreshed them to `pending`; the generic fixture also assumes the 15 approved
`network_coop_note_*` rows exist. This suite therefore currently conflicts
with the fresh ledger state and cannot be used as evidence that these 41 rows
pass. Tests should be reconciled to the current root and dispositions, then
rerun. All 41 rows remain pending; this report is not an M0 gate closure.

## Halo-64 comparison boundary

Halo-64 can inform how to isolate platform adapters, but it cannot establish
the EE Newlib/GCC behavior, CE call-site expectations, PS2 FileIO/OPL mount
semantics, double-math cost, or correct failure behavior here. Do not copy
N64 reductions or infer safety from its stubs; these rows are actual selected
toolchain/CRT providers used by the current HCU closure.

## Root revalidation addendum — 2026-10-21 (new production closure)

The preceding audit records the original review-time root. This dated
addendum revalidates those same 41 rows against the subsequently rebuilt
production closure; it supersedes the earlier identity for currentness checks
without altering the historical report or ledger.

| Artifact | New identity |
|---|---|
| production `rooted.o` | SHA-256 `30b2a4a34c493441869f3e8128ba00405c64d8326c3047d6f505e355bea9f88a` |
| production `result.json` | SHA-256 `58920f92393c15ce177b60dc608cf602b697f1fc0e2f85f34304b1f0b1082c78` |
| current external ledger | SHA-256 `dc023443bf2592e22f26df193589163e0296605b3cf5dbc6301bf067341a9bbf`; its `rooted_sha256` exactly matches the new root |
| current link map / ELF | `halo-local.map` SHA-256 `665bf22c84242bb5345ef5f33593ec436f51623a987674a0dfca54c7308f4808`; `halo-local.elf` SHA-256 `175597376cceb8365110ce65ce4307c9b2f2583ce88cba4089e5e00ac4a54214` |
| closure totals | 370 compiled units, 0 failed units, 322 rooted live externals |

Revalidation results:

- **Membership unchanged:** the report’s 41 reviewed toolchain names equal
  the current ledger’s 41 `toolchain` + `pending` names; all 41 occur in the
  new `result.json` rooted external set. No symbol was added, removed, or
  replaced. Changed rows: **none**.
- **Caller sections unchanged:** all 41 current ledger `caller_sections`
  arrays match the new closure’s arrays exactly. Changed rows: **none**.
- **Caller source hashes unchanged and current:** all 1,682 caller-source
  hash entries across the 41 rows resolve in the checked-out HCU tree and
  match its current file bytes. Changed/stale files and rows: **none**.
- **Selected providers unchanged:** inspecting the new map’s defining text
  sections for all 41 symbols reproduces the provider table above: nine GCC
  `libgcc.a` arithmetic/conversion members, three `ps2_crt.o` adapters, eight
  `libm.a` functions, and the remaining 21 Newlib `libc.a` members. Provider
  selection changes: **none**.

Therefore the symbol-by-symbol semantics and recommended evidence in the
report remain applicable to this new root. This is strictly a provenance and
closure revalidation: it does not approve a disposition, establish target
runtime parity, or close M0. The external-review pytest failures recorded
above remain an independent test/ledger reconciliation issue.
