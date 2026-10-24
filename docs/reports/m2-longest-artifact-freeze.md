# M2 Longest package artifact freeze

**Status: partial preparation evidence only.** This freezes one reproducible host package against the current exact decompressed map and current schema ELF. It does not qualify a fixed EE tag/BSP split, load a CE scenario, prove renderer assets, or admit Longest in the runtime catalog.

## Inputs and source identity

| Input | Identity |
|---|---|
| Decompressed `longest.map` | `build/retail-maps/decompressed/longest.map`, 42,141,696 bytes, SHA-256 `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` |
| HCU schema ELF | `build/hcu-ps2-closure/all/halo-local.elf`, SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa` |
| Current closure record | `build/hcu-ps2-closure/all/result.json`, SHA-256 `2b63236e097dd0836532acc6283d9885dd027047526ad0c937eab779b15a51af` |
| Closure compiler/result | R5900 GCC 15.2.0; 369 selected sources compiled, zero failures; closure gate remains open; HCU commit `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; manifest SHA-256 `8fa834f2185dd9dae225c51ef236d6491e2ab9449c3e6f7cc9eb2eb7c407485a`; prefix SHA-256 `8edce2ba3c42b406db6c73cdca3c6c68e318c9df390a16c1db0f54321c8074b2` |
| Parent / HCU / halo-ps2 pins | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Pack converter | `tools/pack_retail_ctag_hp2.py`, SHA-256 `bbcaa062284fdcbec07855b572307577c1f2978e4de7df52dfaa080084b17ed1` |

The previous 35 MiB schema build directory was preserved at `build/m2-artifacts/schema-2fba411b-prior/` before rerunning the closure. The regenerated `result.json` now records the current HCU commit and current dirty-source hashes; for example, its `source/hs/hs.c` digest matches the current file. The output ELF remains byte-identical to the previous schema ELF, which keeps existing schema-size reports tied to the same binary while the closure record now ties that binary to this source/build run. The decompressed map hash was rechecked; the original retail XISO was not re-read in this turn, so use the earlier source-XISO record in the capacity audit as provenance rather than claiming a new disc extraction.

## Generated package and contents

Command:

```sh
python3 tools/pack_retail_ctag_hp2.py \
  build/retail-maps/decompressed/longest.map \
  build/hcu-ps2-closure/all/halo-local.elf \
  build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2 \
  --include-all-bsps
```

Output: `build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2`, 2,041,856 bytes, SHA-256 `6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b`. The earlier package made from the byte-identical ELF and map has the same hash. Converter summary:

| Measurement | Value |
|---|---:|
| Source cache length | 42,141,696 bytes |
| CE tags / tag-data extent | 1,696 / offset 35,062,272, size 7,079,296 |
| Compact CTAG image / wire payload | 4,263,624 / 4,339,096 bytes |
| CTAG relocations | 18,855 |
| CRNG wire section / intervals | 9,380 bytes / 1,168 |
| HMAP identity section | 72 bytes |
| Active CE BSPs represented | one (`B000`) |
| B000 encoded/raw image | 377,388 / 374,784 bytes |
| B000 internal / CTAG-name relocations | 138 / 76 |
| BSP source tag path | `levels\test\longest\longest` |
| HP2 sections | `CTAG`, `CRNG`, `HMAP`, `B000`, `CBIX` |

The packer constructs CTAG/CRNG/HMAP from the source map and uses `--include-all-bsps` to convert every referenced BSP and generate CBIX (`tools/pack_retail_ctag_hp2.py:47-73,81-123`). It reopens the resulting HP2 and decodes CTAG, CRNG, HMAP, each CBSP, and CBIX to check consistency (`tools/pack_retail_ctag_hp2.py:125-155`). The runtime still has an explicit non-UI `capacity-not-qualified` guard (`src/stream/hcu_map_service.c:219-224`); the tag read only succeeds for CE's final bound tag-cache address and after CTAG materialization (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:358-397`).

## Verification and limits

- Added `tests/test_pack_retail_ctag_hp2.py::test_packages_longest_ctag_and_selected_bsp_with_current_schema`. It asserts section set, CTAG image size and scenario index, HMAP map/source identity, single-row CBIX targeting B000, decoded BSP image size, resource interval count, and deterministic package hash across a second conversion.
- `python3 -m pytest -q tests/test_pack_retail_ctag_hp2.py` — **3 passed, 6 subtests passed**.
- `python3 tools/hcu_ps2_closure.py --layer all` — **369 compiled, zero failures**; the reported M0 gate remains open. The schema ELF is host/pack evidence, not a runtime-combined ELF or guest result.
- `git diff --check` passes.

This bundle is sufficient to start the Longest host stream-decoder and CTAG/CBSP materialization comparisons. It is **not** the full capacity prerequisite. Missing evidence includes: original XISO re-verification; a source- and output-hash-pinned renderer geometry/lightmap/texture pack; an exact non-overlapping boot-time tag/BSP split with CE claims and canary bounds; persistent CRNG/CBIX descriptor sizing; complete EE/GS/IOP/SPU2 working-set and transition ledger; Longest CE scenario/BSP load; collision/surface/PVS/sound consumers; gameplay tick/snapshot; and interpreter/recompiler screenshots/logs from the same exact gameplay ELF. Keep the map admission guard closed.

## Bounded HP2 visitor slice (2026-10-21)

The halo-ps2 world loader now exposes `world_visit_section_with_scratch()` in `engine/src/world/section.h:8-19` and implements it in `engine/src/world/section.c:25-130`. It retains one file-reader descriptor while validating/decoding the selected HP2 entry, checks input offsets against the measured file length, leases the existing 98,304-byte history/input/output workspace from a caller-owned scratch arena, streams decoded spans to a callback, then releases scratch and closes the reader on success or failure. The existing full-output loader remains available and still owns a complete section-sized allocation (`engine/src/world/section.c:133-233`).

The visitor contract is intentionally conservative: a sink may have received a prefix before I/O, decode, or CRC failure, so the caller must not publish that sink state unless the visitor returns `HP2_OK`; the API is synchronous/non-reentrant because it shares static header storage (`engine/src/world/section.h:11-19`). Sink-buffer lifetime and contiguous callback order are now explicit in the API comments. This is not yet a CTAG destination/materializer, and it does not make callback writes transactional. A future direct-to-CE-cache sink must establish an unpublished destination/rollback or equivalent revalidation contract before writing into memory visible to HCU. The unchanged runtime map guard is still required.

Evidence:

- `tests/test_world_section_visitor.py:9-54` compiles production `section.c`, `mem.c`, `hp2.c`, and `file.c` with AddressSanitizer/UBSan, pins the UI, Longest, and Blood Gulch package SHAs above, and compares all five sections (CTAG/CRNG/HMAP/B000/CBIX) byte-for-byte with the legacy whole-output API. Longest CTAG/B000 are 4,339,096/377,388 bytes; Blood Gulch CTAG/B000 are 4,556,496/1,303,092 bytes. A second visitor call for each section larger than two output windows rejects at decoded offset 32,768 after two successful sink calls, verifies `HP2_ERR_IO`, zero published `raw_size`, and scratch rewind. The synthetic engine fixture derives the first payload offset from the table and injects I/O failure there, after header/table parsing (`submodules/halo-ps2/engine/tests/test_world_loader.c:120-197`).
- Verification after the expanded tests: `python3 -m pytest -q tests/test_world_section_visitor.py` — **1 passed** across the available package/section matrix; `ASAN_OPTIONS=detect_leaks=0 make -C submodules/halo-ps2/engine/tests test` passed with ASan/UBSan. LeakSanitizer remains disabled because of this environment's ptrace incompatibility. A forced R5900 rebuild of `section.c` succeeded earlier; the API follow-up changed comments and host test code only. This proves bounded decoder parity and failure behavior, but not provenance-coherent regeneration of the existing Blood Gulch package, EE throughput, live CE tag-cache materialization, or map-load behavior.

Remaining before a real M2 vertical slice: implement a transactional/unpublished CTAG destination strategy in the production cache path, inventory and retain bounded CRNG/CBIX metadata, validate then materialize CBSP to a separate current-BSP owner, audit renderer/audio/animation/transition memory, and inject failure/retry in the exact guest lifecycle. Successful UI reload cycles now have interpreter/recompiler evidence (see [`m2-ctag-stream-consumer-audit.md`](m2-ctag-stream-consumer-audit.md#production-unload-hook-follow-up-2026-10-21)); no gameplay-map admission, map render, or visible PCSX2 scene is claimed.
