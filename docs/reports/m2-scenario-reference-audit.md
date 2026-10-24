# M2 Step 5 — scenario BSP reference/catalog audit

## Finding

**Implementation update (2026-10-21):** The former gap is now closed for positive package-derived coverage. `tests/hcu_map_catalog_package_matrix_main.c` reads the CTAG scenario references and asserts path, datum, source extent, CBIX row/tag and canonical order for all 82 references; `tests/test_hcu_map_catalog.py` runs this under ASan/UBSan. The retained source audit below remains independent corroboration against raw retail maps. The remaining failure-injection recommendations below are still open.

The remaining Step 5 question is executable and currently has strong offline evidence, but the production-C all-map test does not yet assert it. Retail `scenario.structure_bsp_references` contains an ordered 32-byte record per BSP: source-file offset and size, runtime/base fields, and an `sbsp` tag reference whose name and datum identify the BSP. The parent catalog duplicates the offset, size, section tag, and scenario path; CBIX maps offset/size to a packaged `Bxxx` section.

I ran an independent read-only audit across the 24 current HP2 packages in `/tmp/hcu-m2-capacity-repro.P5qdmI/packages`, using the original decompressed CE maps in `build/retail-maps/decompressed` as the source side. It parsed each package CTAG's scenario BSP block, compared ordered `(file_offset, file_size, path, group)` tuples against the raw-map extraction, then matched each ordered tuple to the CBIX entry and `B000`, `B001`, … tag. Result: **24 maps, 82 references; all 82 raw-retail references exactly matched CTAG paths/extents/order and the corresponding CBIX row/tag.** The audit is not yet a committed regression and does not prove guest map load, memory fit, or rendering.

The durable package identity report is [`retail-cbsp-catalog-package-audit-e4a97218.json`](retail-cbsp-catalog-package-audit-e4a97218.json), SHA-256 `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`; it binds 24 package hashes and reports 82 catalog rows. For example, `a10.hp2` is `23fb472b52a7b3c3883349e30b5faca5b856f3e1a0d587e800c54e958b0f61c7`, and `bloodgulch.hp2` is `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011`. The test should continue to validate the full per-package hashes from this report, not merely trust the package filenames.

## Source layout and present gap

- CE's `scenario_structure_bsp_reference` is declared as `file_offset`, `file_size`, `base_address`, four unused bytes, and `tag_reference structure_bsp`; the record is asserted to be 0x20 bytes in [`scenario_definitions.h`](../../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L147-L157). The scenario's `structure_bsp_references` block is the final field at offset `0x5A4` ([same file](../../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L300-L316)); HCU's Linux schema declares it as a bounded tag block and the CE port's cache format records the 32-B stride and max count 32 ([`tag_schema_scenario.c`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_scenario.c#L1350-L1357), [`cache_file_formats.c`](../../submodules/halo-ce-universal/port/linux/game/cache_file_formats.c#L109-L118)).
- The retail source parser already preserves reference order: [`bsp.locate`](../../submodules/halo-ps2/tools/halo2ps2/bsp.py#L178-L194) walks scenario entries by index and resolves each tag datum through the `sbsp` tag-index paths. `audit_retail_bsp_capacity.audit_map()` returns these ordered `path`, `file_offset`, and `file_size` rows ([`audit_retail_bsp_capacity.py`](../../tools/audit_retail_bsp_capacity.py#L32-L60)).
- CTAG schema conversion relocates tag-reference name pointers into the compact image and checks names are NUL-terminated ([`ctag_schema_walk.py`](../../tools/ctag_schema_walk.py#L244-L272)); `ps2_ctag_open()` validates image size, tag table bounds, and relocation entries but intentionally does not schema-walk scenario fields ([`ps2_ctag.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c#L64-L145)). Thus the scenario walk belongs in the package-level schema-aware matrix, not in the generic envelope parser.
- HCU's catalog entry already has `scenario_bsp_path` next to each extent and section tag ([`hcu_map_catalog.h`](../../src/stream/hcu_map_catalog.h#L9-L23)). The runtime validator checks every extent and tag against CBIX ([`hcu_map_catalog.c`](../../src/stream/hcu_map_catalog.c#L319-L337)); the packaging audit checks CBIX/CBSP extent completeness against raw source extents as sets ([`audit_retail_cbsp_catalogs.py`](../../tools/audit_retail_cbsp_catalogs.py#L23-L63)). Neither check currently compares scenario reference path/order.
- The all-map C test verifies only the scenario tag's own name (`verify_scenario_tag`) and separately validates all catalog extents/CBIX tags/CBSP envelopes (`verify_map`) ([`hcu_map_catalog_package_matrix_main.c`](../../tests/hcu_map_catalog_package_matrix_main.c#L66-L99), [#L101-L159](../../tests/hcu_map_catalog_package_matrix_main.c#L101-L159)). It does not yet parse `scenario_root + 0x5A4`, compare each BSP reference's `sbsp` path against `scenario_bsp_path`, or assert order. Its Python wrapper already compiles the real catalog, HP2, CTAG, and CBSP C readers with ASan/UBSan and validates the exact package-manifest hashes ([`test_hcu_map_catalog.py`](../../tests/test_hcu_map_catalog.py#L54-L105)).

## Recommended regression integration

Extend `tests/hcu_map_catalog_package_matrix_main.c` so the existing C matrix itself proves the runtime-package side of the requirement, then extend its Python wrapper for raw-source cross-checking.

1. Refactor `verify_scenario_tag()` to return a small checked view (or split out a helper) containing the decoded `ps2_ctag_view`, scenario tag instance, and normalized scenario-root image offset. It currently loads/frees CTAG locally; retain the payload for the duration of `verify_map()` so scenario references can be read without a second decode. Do not change `ps2_ctag_open()` into a schema parser.
2. Bounds-check and read the scenario tag root pointer from instance `+20`, require `root + 0x5B0 <= image_size`, then read the tag block at `root + 0x5A4`: signed count and normalized pointer. Require `0 <= count <= 32`, `count == entry->bsp_count`, and a non-null pointer/range for `count * 0x20`. Use checked subtraction/division style bounds (as in the existing table logic) to avoid overflow.
3. For each reference index `i`, parse the structure at `refs + i * 0x20`. Verify `file_offset`/`file_size` equal `entry->bsp_catalog[i]`, the reference group encodes `sbsp`, its normalized path pointer is in-image and NUL-terminated within the tag-name bound, and the exact path bytes equal `entry->bsp_catalog[i].scenario_bsp_path`. Verify the datum handle at `+0x1C` resolves through the CTAG tag-instance table to an `sbsp` entry whose full datum matches and whose tag path matches the reference name. `name_length` is observed zero in the tested CTAG row, so do not assume it equals `strlen(path)`; validate its source/runtime semantics separately if CE relies on it.
4. Match the same index's source extent through `cbsp_catalog_find()`, compare the returned `section_tag` with the catalog's tag, and require canonical `B%03u` order. Current `cbsp_catalog_open()` guarantees sorted non-overlapping extents but not scenario semantics ([`cbsp_catalog.c`](../../src/stream/cbsp_catalog.c#L23-L63)); path-to-extent checks close that gap. Retain the existing CBSP payload check that its embedded source extent equals the catalog row.
5. Add an independent raw-cache check in the Python wrapper. Use `tools.audit_retail_bsp_capacity.audit_map()` on the corresponding pinned decompressed retail `.map`; its rows preserve actual scenario order and tag-index-derived BSP paths. Compare all source `(path, offset, size)` tuples to the C/package results. Prefer emitting structured tuples from the C harness (or a deterministic JSON/line protocol) rather than scraping human diagnostics. The Python test should verify each map's decompressed source SHA against the package's HMAP/audit row and the package SHA against the immutable package manifest. This prevents a bad converter and a self-consistent but wrong static catalog from validating one another.
6. Add failure regressions by copying a small package fixture and mutating, one at a time: reference count; file offset or size; group; path pointer out of image; unterminated path; wrong path; duplicate/reordered reference; wrong datum; missing/duplicate CBIX extent; wrong `Bxxx` section; CBSP embedded extent mismatch. Recompute CTAG CRC/relocation metadata for semantically valid corruption cases so each check reaches the intended layer; otherwise an earlier checksum rejection gives false coverage. Assert rejection before accepting the map. Keep the ASan/UBSan build and exact audit manifest hash checks.
7. Report the positive matrix as `scenario_ref=82/82`, additionally showing maps and references by map. Do not mark the whole Step 5 complete solely on this matrix: adversarial package-reader cases, arena/capacity, CE runtime scenario loading, and guest evidence remain separate gates.

## Reproduction/evidence

The read-only audit used the pinned package directory and retail source maps:

```sh
PYTHONPATH=tools:submodules/halo-ps2/tools python3 - <<'PY'
from pathlib import Path
import struct
import ctag, hmap
from halo2ps2 import hp2
from tools import cbsp
from audit_retail_bsp_capacity import audit_map

packages = Path('/tmp/hcu-m2-capacity-repro.P5qdmI/packages')
maps = Path('build/retail-maps/decompressed')
total = 0
for package_path in sorted(packages.glob('*.hp2')):
    source_rows = audit_map(maps / (package_path.stem + '.map'),
                            capacity=0xFFFFFFFF)['structure_bsps']
    pack = hp2.parse(package_path.read_bytes())
    image = ctag.decode(pack.read('CTAG'), max_image_size=64 * 1024 * 1024)
    identity = hmap.decode(pack.read('HMAP'))
    scenario_index = image.scenario_tag_index & 0xFFFF
    table = struct.unpack_from('<I', image.image, 0)[0]
    instance = table + scenario_index * 32
    scenario_root = struct.unpack_from('<I', image.image, instance + 20)[0]
    count, references = struct.unpack_from('<iI', image.image,
                                           scenario_root + 0x5A4)
    rows = cbsp.decode_catalog(pack.read('CBIX'),
                               expected_file_length=identity.file_length)
    assert count == len(source_rows) == len(rows)
    for index, source in enumerate(source_rows):
        row = references + index * 32
        offset, size = struct.unpack_from('<II', image.image, row)
        assert image.image[row + 0x10:row + 0x14] == b'psbs'
        name_offset = struct.unpack_from('<I', image.image, row + 0x14)[0]
        name_end = image.image.find(b'\0', name_offset, name_offset + 256)
        name = image.image[name_offset:name_end].decode('ascii')
        assert (offset, size, name.lower()) == (
            source['file_offset'], source['file_size'],
            source['path'].replace('/', '\\').lower())
        assert (rows[index].file_offset, rows[index].file_size,
                rows[index].section_tag) == (offset, size, f'B{index:03d}')
        total += 1
print(f'PASS maps=24 scenario_refs={total} '
      'raw_retail_vs_ctag=exact_order_paths_extents '
      'cbix=exact_order_extent_and_Bxxx')
PY
```

This script was executed against the durable current package directory and passed for all 24 maps/82 references. The future regression should harden bounds and source identities as listed above; this one-off audit used the expected-good packages and intentionally demonstrates the field mapping rather than fault behavior.

The catalog/package test command remains:

```sh
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q tests/test_hcu_map_catalog.py
```

## Pin and scope notes

The working source pins during this audit were parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The source-side order/path extraction depends on the pinned halo-ps2 tag-index/BSP parser; CTAG schema/record interpretation depends on the pinned HCU schema and conversion; the catalog reader and fixture are parent sources. Re-run and bind all hashes after any of these pins or package inputs change.

The evidence proves source metadata and package mapping correspondence only. It does not prove PS2 arena fit, `scenario_structure_bsp_load()` behavior, collision/PVS/sound consumers, gameplay initialization, VIF/GS submission, a visible image, or full M2 completion.
