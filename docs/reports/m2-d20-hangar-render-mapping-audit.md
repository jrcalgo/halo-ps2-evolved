# M2 d20_hangar source-surface / PS2 render-batch mapping experiment

**Disposition: useful offline mapping evidence; no BSP bytes are approved for removal and no capacity credit is granted.** This probe asks whether the existing `halo-ps2` BSPS/VIF output can identify every CE source render surface and reproduce its position stream closely enough for a render-only CPU accessor experiment. It does not replace CE collision, material lookup, light sampling, or any tag-schema validator.

## Frozen inputs and reproduction

The probe uses the checked-in decompressed `build/retail-maps/decompressed/d20.map`, BSP index 3 (`levels\\d20\\d20_hangar`). Map SHA-256 is `30d8fc02bcd209a7ce03174d8cf6cf771dd3621837d9a2d02111718dcc5e792c`; the source BSP block at offset 18,900,992 is 8,517,632 bytes with SHA-256 `a8e8174997a793831bd0504484582172e3802688a51d6b32a61e30c5962001ab`. The emitted BSPS v2 section has SHA-256 `1442a7da4494a6be9ff45753e65a0fc72c8eb03e75ee94aeda2b80786c67c3bb` and is produced in-memory by the currently checked-out `halo-ps2` converter via [`audit_bsp_render_mapping.py`](../../tools/audit_bsp_render_mapping.py). The machine-readable result is [`m2-d20-hangar-bsps-render-mapping.json`](m2-d20-hangar-bsps-render-mapping.json).

Reproduce with:

```sh
python3 tools/audit_bsp_render_mapping.py \
  build/retail-maps/decompressed/d20.map --bsp 3 \
  --output docs/reports/m2-d20-hangar-bsps-render-mapping.json
PYTHONPATH=. python3 -m pytest -q tests/test_retail_bsp_render_mapping.py
```

The test binds map, source-block, and generated-section hashes and independently checks source-surface coverage, triangle counts, expanded-corner count, a 0.002-unit maximum Euclidean error bound, and the explicitly non-gameplay scope. It passed with the focused BSP audit suite: **6 passed**.

## Result

| Measurement | Result |
|---|---:|
| CE source BSP block | 8,517,632 bytes |
| CE structure surface records | 49,859 |
| Source rendered material triangles | 49,859 |
| BSPS raw section | 3,876,512 bytes |
| BSPS batches | 2,550 |
| Source surface IDs mapped to exactly one output triangle | 49,859 / 49,859 |
| Source surfaces missing cluster routes in this BSP | 0 |
| Expanded vertex-corner comparisons | 149,577 |
| Maximum absolute per-axis position error | 0.0012770058 world units |
| Maximum Euclidean position error | 0.0018663984 world units |
| Maximum absolute lightmap-UV error | 0.0 |
| Diffuse-UV components beyond converter's ±64 sane-input range / non-finite | 6 |
| Maximum finite source diffuse-UV magnitude | 516.0 |
| Maximum absolute diffuse-UV error after BSPS quantization/clamp | 512.0001221 |
| Candidate direct lookup storage | 199,436 bytes (4 bytes × 49,859 source surfaces) |

The mapping replay intentionally mirrors the converter's `(cluster set, material)` grouping, spatial triangle order, and 24-triangle batch partition. The candidate four-byte row is merely a lower-bound layout estimate: `batch:u16, triangle-in-batch:u8, flags:u8`, with an absent-batch sentinel for surfaces not represented. Material is recoverable from the BSPS batch. It is not a selected ABI or converter sidecar format.

## What this establishes and what it does not

This d20_hangar case demonstrates a deterministic source-surface-to-expanded-triangle relation for every source material triangle in the current converter output. It quantifies position quantization at roughly 0.0019 world units maximum and exact lightmap-UV round-trip for this case. However, six diffuse-UV components exceed the converter's ±64 “sane” input range (largest finite magnitude 516), and BSPS clamping/quantization changes the maximum diffuse UV by 512.0001. That is a concrete non-equivalence for an unrestricted CPU query, even though those outlier values are documented as authored garbage and clamped for the VU render path. A render-only adapter must preserve CE's source-data fallback for such values or prove with CE call-site/tag evidence that they are never semantically consumed. The acceptable visibility/frustum and UV behavior must still be tested around triangle/frustum/texture boundaries; measured position error is not a tolerance approval. The candidate index costs about 199 KiB before alignment, versioning, source identity, bounds checks, and any transactional staging.

The report does not show that the 3,311,136 bytes of CE `compressed_vertex_data` may be removed. CE uses the same record for collision-hit→surface/material/barycentric resolution and for diffuse/lightmap UVs, packed normals/tangent frames, and incident radiosity (`structure_visibility.c`, `structures.c`, and `object_lights.c`; see [`m2-bsp-compressed-vertices-parity-audit.md`](m2-bsp-compressed-vertices-parity-audit.md)). BSPS stores quantized expanded positions/UVs/color, omits those CPU query fields, and is itself a 3,876,512-byte resident candidate. If its section was not already included in the live renderer footprint, the direct comparison `3,311,136 removed - 3,876,512 BSPS - 199,436 index` is **negative 764,812 bytes**, before any remaining CE query data or staging. If BSPS is already resident for rendering, it still must be counted exactly once, and only the validated CE-position bytes plus bridge can be considered as a possible offset. Neither case is a passing whole-map ledger.

No production converter format, HCU accessor, runtime pointer, collision path, or arena binding was changed. Next valid work is to add a source-identified mapping to a temporary converter prototype and compare exact frustum/visibility decisions plus boundary cases against CE while preserving all other CE data; then recalculate every simultaneous BSP/CTAG/render owner from physical evidence. Until those pass, retain the full CE data and keep gameplay-map admission closed.
