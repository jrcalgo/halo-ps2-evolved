# M2 Step 7 — MP lens-flare marker consumer slice

Date: 2026-10-22. This isolated host fixture invokes CE's actual `rasterizer_lens_flare_submit_for_cluster()` over marker, palette, and cluster arrays decoded from raw retail Xbox MP BSPs. It checks the CE-selected submission marker-index sequence against an independent Python walk of the raw cluster ranges and marker palette indices. It is one consumer slice; Step 7 remains open.

## Source behavior and fixture

CE looks up one cluster, walks its `[first_lens_flare_marker_index, count)` range, caps marker indices to the range that fits signed-short occlusion results, rejects marker indices outside the BSP marker block, skips marker palette indices outside the BSP lens-flare palette, converts the packed direction, resolves the definition, and submits the marker position and index ([`rasterizer_lights.c:774-835`](../../submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c#L774)). The marker schema checks each marker's palette index against the root lens-flare block ([`tag_schema_collision.c:686-695`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L686)); cluster validation checks marker ranges and clears malformed ranges on load ([`tag_schema_collision.c:1474-1481`](../../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c#L1474)).

[`tests/test_hcu_mp_lens_flare_consumer.py`](../../tests/test_hcu_mp_lens_flare_consumer.py) reads the source map's structure-BSP marker, palette, and cluster blocks, generates a temporary C translation unit containing the unchanged CE function body, and compiles/runs it with spies for lens-flare submission and direction/occlusion helpers. Python independently expands each raw cluster marker range, drops out-of-range records as CE does, and compares every emitted marker index. It also asserts zero bad-reference reports. No renderer output or image is claimed.

## Results

Exact raw source map SHA-256 values, counts, and matching CE submissions:

| Map | Lens-flare palette | Markers | Clusters | Expected and observed submissions | Bad references |
|---|---:|---:|---:|---:|---:|
| Boarding Action | 1 | 207 | 41 | 207 | 0 |
| Damnation | 1 | 22 | 12 | 22 | 0 |
| Putput | 1 | 892 | 9 | 892 | 0 |

The raw map hashes are Boarding Action `34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522`, Damnation `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c`, and Putput `efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243`. The other ten catalog MP BSPs have zero marker records and do not offer nonempty consumer cases.

Exact command:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_lens_flare_consumer.py -v
```

Result: **1 test passed** (three BSP subcases; host compiler `cc -std=c99 -O2`). Fixture SHA-256: `005ea3db352e56fc06d5fa0c0d07e3620a720534f470163da78d6b447aef3cdc`. CE source SHA-256: `2a4db1e1f5e125436fddc05a46b1eb68102e2be978d8294919f85275d742b233`.

## Limits

This verifies cluster range iteration, marker-index bounds, palette-index acceptance, and the submitted marker sequence on three raw stock MP BSPs. Direction normalization/compression and definition resolution are stubbed; the submission call is a spy. It does not run `build_structure_lens_flares()` (the geometry-driven mutating builder), actual visibility/occlusion readback, Xbox rendering, or the PS2 lens-flare adapter. The fixture is a host semantic query, not CE map-load/relocation, EE runtime, or target-capacity evidence. It does not close Step 7 or Step 8.
