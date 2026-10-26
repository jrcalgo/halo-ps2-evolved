# M4 C4: schema ELF pin re-derivation (2026-10-26)

## Why the pin cannot be restored

Pinned schema ELF `56cd9fb82c4729b6870972c8d8be36fab78916ff1fa2026c5e22bf7cfe263037`
(`build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf`, produced by
`python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory`) is not on disk
(`find / -name '*.elf' -o -name '*.bin'` sha256 scan: no match). That path was overwritten on
2026-10-24 16:50 by a rebuild, now `b1d3c7b0af253988aab8fc60a7a7618bb03435111784ddf784dd50f5d39280c5`.

Rebuild from the recorded source was attempted by evidence, not by guess. The closure ledger
(`m2-step7-step8-closure-ledger-2026-10-22.json`, `schema_build_units.source_and_object_hashes`) records the
SHA-256 of all 371 compiled units of the 56cd9fb8 build. 335 match the current CE tree; 36 do not. For each of the 36
files, every commit in `submodules/halo-ce-universal` history (`git log --all`) was searched for a blob with the
recorded hash: `source/objects/objects.c` and `source/saved games/game_state.c` match no commit at all, and the
intersection over all 36 files is empty. The 56cd9fb8 ELF was therefore built from uncommitted working-tree state that no
commit contains; it cannot be reproduced exactly. No hash was hand-edited. The same applies to the other missing pin,
`build/hcu-ps2-closure/all/halo-local.elf` 2fba411b... (now 55bfec22...).

## Re-derivation (all by the owning generators, run against the current ELF b1d3c7b0...)

Chain order: inventory -> gap discovery -> gap layout -> DWARF members -> range member layout -> crosswalk /
dispositions / exact layout / source map / open-root -> empty fields -> byte dispositions -> gap consumer -> overlap domains.

| Report (docs/reports/) | Old sha256 (12) | New sha256 (12) | Producing command |
|---|---|---|---|
| m2-step7-bsp-member-inventory-2026-10-22.json | 29fa47457d98 | 8d0bfccd29da | `generate_hcu_step7_step8_closure.inventory()` + `compile_member_layout()` on the current ELF (only the inventory output; ledger/bindings/coverage audit were NOT regenerated) |
| retail-bsp-preservation-2026-10-21.json | 765ca7073073 | dc4bb2ab5b8c | `python3 tools/audit_retail_bsp_schema.py build/retail-maps/decompressed <ELF> --output ...` |
| retail-bsp-cbsp-audit-c0-2026-10-22.json | 765ca7073073 | dc4bb2ab5b8c | same command (the two files were byte-identical before and after) |
| m2-step7-schema-gap-source-discovery-2026-10-22.json | 1e037a95cf98 | 6f624514c905 | `python3 tools/c4_rederive_step7_gap_discovery.py` (new; no prior generator existed; re-keys definition_id and ELF hash, refuses unless 54 gaps map one-to-one) |
| m2-step7-schema-gap-layout-2026-10-22.json | ecc2ddb487c4 | 6072412d7abd | `python3 tools/verify_hcu_step7_schema_gap_layout.py` |
| m2-step7-schema-gap-dwarf-members-2026-10-22.json | 6b9edb0ccd7a | 958ef393fbb3 | `python3 tools/extract_hcu_step7_gap_dwarf_members.py` |
| m2-step7-bsp-range-member-layout-2026-10-22.json | cc2b4687dbd4 | 60b933028dd9 | `python3 tools/probe_step7_bsp_range_members.py` |
| m2-step7-bsp-consumer-crosswalk-2026-10-22.json | a51c335d2a5a | ef7e8f8ef712 | `python3 tools/generate_step7_bsp_consumer_crosswalk.py` |
| m2-step7-eight-unmapped-exact-layout-2026-10-22.json | 26eca45978fb | 0e760f83d3b9 | `python3 tools/probe_step7_eight_unmapped_exact_layout.py` |
| m2-step7-eight-unmapped-range-source-map-2026-10-22.json | f287145d8ddf | f512d9e12c39 | `python3 tools/audit_step7_eight_unmapped_ranges.py` (tool constants: 8 definition_id literals remapped by the uniform +75496 ELF address delta; edit in tools/) |
| m2-step7-unclassified-range-dispositions-2026-10-22.json | 06db2f9ecfea | 1176f5ce520c | `python3 tools/audit_step7_unclassified_range_dispositions.py` |
| m2-step7-open-root-bsp-dispositions-2026-10-22.json | fb91d0e0a835 | 2c5f649738b4 | `python3 tools/generate_m2_step7_open_root_dispositions.py` |
| m2-step7-empty-bsp-fields-2026-10-22.json | 71be6e234439 | 1d96ac3416ee | `python3 tools/audit_step7_empty_bsp_fields.py --output ...` |
| m2-c0-byte-dispositions-2026-10-23.json | 9ab3f0f156cc | ca734bbccdae | `python3 tools/audit_hcu_c0_byte_dispositions.py` (issues: 0) |
| m2-step7-gap-consumer-evidence-2026-10-22.json | 4479eb1e2958 | (drifts) | `python3 tools/audit_step7_gap_consumer_evidence.py --output ...` |
| m2-step7-overlap-member-domain-audit-2026-10-22.json | b32cda17d3c3 | (drifts) | `python3 tools/audit_step7_overlap_member_domains.py --output ...` |

Gap-consumer and overlap-domain reports hash live CE sources (e.g. `first_person_weapons.c`, `main.c`, being edited by
other lanes), so their hash changes with any CE source edit. They were regenerated last and pass at that moment; the
final hash depends on the CE tree at commit time and must be regenerated (same commands) if a CE source they hash changes.
Before regeneration both were already stale from CE source drift, independent of the ELF.

## Semantic-content proof

* `retail-bsp-preservation` / `retail-bsp-cbsp-audit-c0`: `diff` of the regenerated 12,285,136-byte report against the
  recorded one shows exactly one differing line (`schema_elf_sha256`). Therefore all 24 maps / 82 BSPs / 348,770,304 raw
  source bytes, 349,869,456 CBSP envelope bytes, 348,145,528 schema-owned bytes, every per-BSP CBSP hash and
  `cbsp_round_trip_failure_count` 0 are unchanged.
* Inventory: 48 definitions, 164 member rows, 54 unclassified ranges, 12 open root rows, names, sizes and offsets
  identical; the only changes are `definition_id` (ELF data addresses, uniformly +75,496 for all 48 definitions), the ELF
  hash and the manifest hash. Check: structural diff of old (ids remapped) vs new.
* For every regenerated report, old content with definition ids remapped and the ELF hash substituted was compared with
  the new content field by field: differences are SHA-256 values of upstream files only, plus these input changes
  with other causes: crosswalk `swarm_reports` (live swarm result files changed after 2026-10-22), open-root
  `ce_source_pin` (CE HEAD moved c9f59a8 -> 6de9046), schema-gap-layout `compiled_units` 371 -> 373 (two CE units added),
  overlap-domain source line numbers and member spellings (CE sources edited since 2026-10-22).
* Package provenance: all 36 retained packages reproduce byte-identically from their maps with the current ELFs
  (`--verify-reproduction`), so package content does not depend on the missing ELF.

## Pins NOT re-derived (reported, not forced)

* `tests/test_step7_package_provenance.py::test_retained_package_manifest_binds_each_current_recipe_input` still fails.
  It pins `build/hcu-ps2-closure/all/halo-local.elf` = 2fba411b..., which is also gone, and it requires 12
  path-specific historical invocation bindings whose historical reports themselves pin `schema_elf_sha256` 2fba411b.
  Regenerating the provenance report (run into scratch) keeps 36/36 byte-identical reproductions but drops those bindings
  from 12 to 1, so the test's 12-binding assertion cannot be met without weakening it. The report was left unchanged.
* The step 7/8 closure ledger, its binding audit, coverage audit, recovered bindings and the C0/C1/C2 reports that quote
  56cd9fb8 (about 25 further files; failing already before this work: test_step7_step8_baseline_identity,
  core_report_measurements, recoverable_bindings, mp_consumer_report_imports, test_step8_historical_pin_availability)
  were not regenerated. The ledger generator rewrites the whole ledger and every binding, which is outside the oracle gate.
* `tests/test_c4_member_ledger.py::test_checker_passes_on_committed_ledger` (C4 member-ledger lane) now reports
  "input hashes differ from committed ledger": rerun `python3 tools/audit_c4_member_ledger.py --write` after this change.

## Package root resolution (additional)

`tools/hcu_package_root.py` resolves pinned retail HP2 packages: `HALO_HCU_M2_PACKAGE_ROOT`, the old /tmp directory,
then `build/mp-fog-selection-*/assets/maps`; a directory is accepted only if every requested package exists and matches
its sha256 pin. Used by `tools/audit_mp_lightmap_surface_consumer.py` and the tests test_hcu_mp_lightmap_surface_consumer,
test_hcu_mp_swept_collision, test_hcu_mp_lens_flare_relocated, test_hcu_mp_detail_present_bound,
test_hcu_mp_path_smoothing; tests skip with a message when no verified set exists. No pin was changed.
Blood Gulch `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011` is present in
`build/mp-fog-selection-1792693186821610382/assets/maps/bloodgulch.hp2`.
