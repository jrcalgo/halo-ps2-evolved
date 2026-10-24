# M2 Step 7: retail BSP pointer-target alignment audit

Date: 2026-10-21

## Result

The updated schema walker’s four-byte alignment rule is consistent with the available decompressed stock-map corpus: **14,799 / 14,799 in-image `tag_data` extents begin at four-byte-aligned offsets**. Their total declared payload length is 131,461,185 bytes. The audit covered 24 maps and 82 structure-BSP blocks; the CBSP round-trip failure count was zero. This validates the observed source-data invariant only. It does not prove target-address materialization, PS2 DMA suitability, object-field alignment after relocation, or runtime consumer behavior.

The schema closure ELF used by the audit has SHA-256 `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2`. The corpus was extracted from XISO SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`; the per-map decompressed files are under `build/retail-maps/decompressed/`. The full machine-generated JSON was written to `/tmp/retail_bsp_alignment_audit.json` and hashed `aecef41ae01c26c7a050f0d4669f542aeff0f370596ece7477e749f351606d1e`; that temporary file is not a checked-in deliverable.

## Reproduction

```sh
python3 tools/audit_retail_bsp_schema.py \
  build/retail-maps/decompressed \
  build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  --output /tmp/retail_bsp_alignment_audit.json
```

The resulting JSON records each BSP’s schema extents. Count entries whose `owner` starts with `data ` and check `offset % 4`; the audit result was 14,799 entries and zero violations. Recheck the ELF hash before comparing a later run: schema-manifest changes invalidate this corpus result.

## Interpretation

`tools/ctag_schema_walk.py` rejects a non-null BSP root, in-image `tag_block` target, or in-image `tag_data` target that is not four-byte aligned. Existing schema fixtures cover aligned roots and reject unaligned roots, blocks, and data. This is a fail-closed input-format rule, not a blanket requirement that all CE datum structures or all external `file_data` targets be four-byte aligned. Keep the parser adversarial cases and the target EE proof as separate gates.
