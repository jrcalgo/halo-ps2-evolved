# Retail CTAG schema-coverage audit

Status: audit evidence for M2; this is not a retail-map conversion or runtime-load pass.

## Reproduction

The audit uses the compiler-derived schema manifest from the measured HCU closure ELF and every decompressed Xbox map in `data/retail/weapon-audit-maps/`:

```sh
python3 tools/audit_ctag_retail_maps.py \
  data/retail/weapon-audit-maps \
  build/hcu-ps2-closure/all/halo-local.elf
```

The report format is deterministic JSON. Both diagnostic policies are explicit in [`audit_ctag_retail_maps.py`](../tools/audit_ctag_retail_maps.py); it emits no CTAG. Retail tag pointers and actual stored reference handles are walked by [`ctag_schema_walk.py`](../tools/ctag_schema_walk.py), and only compiler-derived definitions from the linked ELF are accepted.

## Result

For the current 24-map retail fixture set:

- All 24 maps completed the schema walk; 272,829 stored `tag_reference` fields were inventoried, with no unresolved handles.
- `metr` is the only group without a linked CE schema. Each map contains exactly two such roots; no stored reference handle in any map targets `metr`.
- No other unsupported top-level group was found.
- Every inventoried nonempty `_tag_schema_file_data` extent lies within its decompressed map file.
- The maps contain 14,815 bitmap images and 72,558 file-backed records; all resource extents are in their source map files, with zero invalid ranges. The file-backed records all have flags zero.
- Blood Gulch's two `metr` paths are `ui\hud\cyborg shield` and `ui\hud\cyborg body`. It has 516 bitmap images (23,119,360 payload bytes) and 916 file-backed sample records (12,229,380 payload bytes).
- Blood Gulch's nonempty bitmap and sample ranges combine into 1,432 source intervals: 35,348,740 payload bytes across a 35,644,736-byte address span, with 295,996 gap bytes and no overlaps. The combined window is `[0x0013D000, 0x0233B540)`, ending 192 bytes before the tag region at `0x0233B600`.

These are source-file coordinates, not EE allocations. The result rules out treating the original retail map as one resident gameplay buffer: the production reader needs bounded random/range access to the original map file (or an explicitly remapped equivalent), while only the converted tag image and active working sets belong in the fixed EE arenas. Across the 24 maps, payload sums are 761,727,488 bitmap bytes and 1,606,686,372 file-data bytes; these are per-map sums, not unique/deduplicated storage requirements.

The audit also compares the merged resource intervals with each original tag-data extent. All 24 maps have zero resource intervals overlapping `[tag_data_offset, tag_data_offset + tag_data_size)`. Blood Gulch resources end at byte 36,943,168; its original tag region begins at 36,943,360 (192 bytes later). Therefore the cache adapter's current rejection of reads overlapping the substituted CTAG image is conservative but does not exclude an audited retail bitmap/sample payload, provided the mounted CTAG starts at the original tag offset and fits the virtual file. This does not validate arbitrary custom maps or a repacked resource-offset scheme.

The manifest entry for `metr` deliberately has a null definition ([group declaration](../submodules/halo-ce-universal/port/linux/game/tag_schema_effects.c#L2014)). The validator still requires every non-BSP tag instance to have a non-null root, but only validates a tag through its schema when a definition exists ([tag-table checks](../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L1131), [instance traversal](../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L1049)). A source audit found no `metr` consumer outside the schema-group declaration and generic meter terminology; runtime uses of HUD meters are embedded in `unhi`/`wphi` structures, not fetched through `metr` tags.

## Converter policy and limits

The evidence supports preserving these retail `metr` roots as opaque, unreachable tag instances: keep the table entry and relocate its top-level root pointer, but do not interpret or rewrite unknown root bytes. The walker accepts that behavior only when the caller explicitly allowlists a group that the linked CE manifest declares with a null schema. Default conversion still rejects `metr`; arbitrary unknown groups and absent/null roots still fail closed. Tests exercise both default rejection and explicit opaque retention ([schema-walk tests](../tests/test_ctag_schema_walk.py)).

This conclusion is scoped to the audited retail fixtures and current HCU source closure. Re-run the audit when either changes. It does not prove a general `metr` schema, authorize dropping the tags, or close the other M2 gates: bitmap and file-backed resource reads still need a bounded HP2/PS2 range path, and a production arena-backed loader must still validate, load the scenario/BSP, and roll back safely. The synchronous cache callback is only a correctness seam; bounded buffering, DVD latency, and deadline behavior remain unqualified.

## Retail CTAG compaction audit

Reproduce the current schema-guided conversion across the complete supplied retail-map fixture set with:

```sh
PYTHONPATH=. python3 tools/audit_retail_ctag_conversion.py \
  data/retail/weapon-audit-maps \
  build/hcu-ps2-closure/all/halo-local.elf \
  --output /tmp/retail-ctag-compaction-audit.json
```

[`convert_retail_ctag.py`](../tools/convert_retail_ctag.py) removes the contiguous Xbox model vertex/index interval from the CE tag image after schema walking. It remaps each relocation field and target; conversion fails if a schema-declared pointer intersects the removed bytes. All 24 maps converted successfully with zero such references. This removes render geometry from the runtime tag image rather than merely zeroing the Xbox header's render-buffer pointers. Blood Gulch drops from 7,385,184 to 4,477,116 bytes by removing 2,908,068 bytes; its resulting 19,832 relocations are deterministic and pass the production C CTAG decoder/materializer.

Across the 24 maps, compacted tag images range from 1,510,628 bytes (`ui`) to 11,781,424 bytes (`b40`). Nine images remain above both the 6,815,744-byte resident-gameplay region and the 6,291,456-byte current-BSP region: `a10`, `a30`, `a50`, `b30`, `b40`, `c10`, `c40`, `d20`, and `d40`. The campaign-sized maps therefore still cannot fit the current candidate contiguous regions even after the verified render-buffer removal. The audit is not a memory fit claim; it exposes a blocking M2 representation/ownership decision. Do not consume the 5,767,168-byte reserve or silently omit campaign tags to make the table pass. M2 needs a measured full-map storage strategy consistent with CE's pointer-based tag access, PS2 region ownership, and campaign scope before production loading can be accepted.

The current CE BSP loader makes the peak requirement stricter than the image-only comparison: [`cache_file_structure_bsp_reference_verify`](../submodules/halo-ce-universal/source/cache/cache_files.c#L487) requires a structure BSP's `base_address` to lie after `tag_data_size` in the same `physical_memory_get_tag_cache` span, and [`scenario_structure_bsp_load`](../submodules/halo-ce-universal/source/cache/cache_files.c#L1355) reads the BSP to that address. For example, `a10`'s compact tag image is 9.62 MiB and its largest listed structure BSP (`a10g`) is 8.17 MiB ([BSP inventory](reports/tag-index.md#L328)); the native ownership model therefore needs roughly their sum contiguous, plus aligned read/validation scratch. A design that puts tags and collision in separate arenas must deliberately port this CE BSP-address/validation path and prove the changed ownership; merely binding a larger tag cache does not make the current implementation compatible with the v2 6 MiB current-BSP region.

## Schema-visited tag-image lower bound

The schema walker now reports bytes reached through the CE tag table, typed roots,
reflexive blocks, and in-image `tag_data` spans. It deliberately excludes tag-name
strings and opaque null-schema payloads, so this is a **lower bound**, not an
alternative serialized image size. The reproducible report is
[`retail-ctag-schema-coverage-v3.json`](reports/retail-ctag-schema-coverage-v3.json);
it includes source-map and schema-ELF hashes for cross-report verification.

All nine over-budget campaign CTAGs have schema-visited data alone greater than
the 6,815,744-byte `resident_gameplay` region (9.42–11.57 MiB). Joining that
lower bound to the most optimistic BSP candidate—after hypothetically
externalizing all compressed BSP vertices—still leaves those maps at
13.50–14.90 MiB for tags plus one active BSP, above the combined
13,107,200-byte `resident_gameplay` + `current_bsp` allowance. The combined
screen is reproduced by
[`audit_retail_map_working_set.py`](../tools/audit_retail_map_working_set.py)
and [`retail-map-minimum-working-set-v2.json`](reports/retail-map-minimum-working-set-v2.json).
Therefore removing only unvisited padding/gaps cannot close the capacity gap.
The remaining route must preserve CE semantics while changing the storage/access
model or proposing a measured, versioned budget/region revision; simply packing
the current pointer graph more tightly is insufficient. These figures still
omit validator scratch, the externalized vertex destination, alignment, load
overlap, and renderer/texture/audio working sets.

| Map | Schema-visited tag bytes (lower bound) | Largest projected active BSP | Sum | Over combined regions |
|---|---:|---:|---:|---:|
| a10 | 9,420,629 | 4,736,728 | 14,157,357 | 1,050,157 |
| a30 | 9,497,505 | 5,575,320 | 15,072,825 | 1,965,625 |
| a50 | 10,973,713 | 4,360,680 | 15,334,393 | 2,227,193 |
| b30 | 10,067,063 | 4,588,728 | 14,655,791 | 1,548,591 |
| b40 | 11,566,060 | 3,974,200 | 15,540,260 | 2,433,060 |
| c10 | 11,311,886 | 4,310,616 | 15,622,502 | 2,515,302 |
| c40 | 11,014,620 | 4,257,528 | 15,272,148 | 2,164,948 |
| d20 | 9,895,199 | 5,206,496 | 15,101,695 | 1,994,495 |
| d40 | 10,145,465 | 4,518,168 | 14,663,633 | 1,556,433 |

“Over combined regions” is each sum minus 13,107,200 bytes. The table excludes
the strings/opaque roots omitted by the schema-byte lower bound, plus all
transient and external payload costs; it cannot be interpreted as required
final allocation sizes.
