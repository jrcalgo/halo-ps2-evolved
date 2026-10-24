# M2 Step 7 retail CBSP validation

**Disposition: partial; Step 7 remains open.** A real, non-UI Blood Gulch BSP now passes schema conversion, explicit pointer-domain validation, and byte-for-byte Python/PS2-C materialization comparison. The actual CE `structure_bsp_port_verify` and collision/surface/PVS/sound consumers have not been run against this materialized BSP, so this is relocation evidence—not CE BSP acceptance, game-map loading, capacity qualification, or rendering evidence.

## Reproducible fixture identity

- Parent: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- HCU: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Decompressed retail Blood Gulch map: `build/retail-maps/decompressed/bloodgulch.map`, SHA-256 `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`.
- Schema ELF: `build/hcu-ps2-closure/all/halo-local.elf`, SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`.
- Generated diagnostic package: `build/retail-maps/bloodgulch-with-bsps.hp2`, 2,832,384 bytes, SHA-256 `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011`.
- HP2 `B000` CBSP section: 1,303,092 bytes, SHA-256 `0fc221a36e097285e472e6fc4227a6bf07f20b063d285d4b464303c7d7a0715d`; normalized image is 1,296,384 bytes from retail file extent `(2048, 1296384)`, with 463 internal relocations and 93 typed CTAG-name relocations.

## What changed

`tests/test_cbsp.py` now has a real-fixture parity test that skips when the generated/licensed build artifact is absent. With the local artifact present, it checks each typed name target is within CTAG and NUL-terminated within 256 bytes, computes Python’s materialized expected bytes, then runs the PS2 C decoder/materializer on the same packaged CBSP and CTAG image. The C output matches byte-for-byte. The existing synthetic C fixture remains in place.

The PS2 `ps2_cbsp_materialize` interface now receives the CTAG image bytes as well as its target base and extent. Before writing the output image, it checks every domain-1 target for a bounded NUL terminator; `ps2_cache.c` supplies the already materialized tag-cache base. Python `CbspImage.materialize` applies the same name rule, rejects virtual BSP/CTAG overlap, and Python CBSP encoding rejects unaligned relocation slots to match the C parser. Regression coverage includes overlap, unterminated names, unaligned fields, and an unchanged destination on C rejection. The relevant implementation is in `tools/cbsp.py`, `submodules/halo-ce-universal/port/ps2/include/ps2_cbsp.h`, `submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c`, and its production caller `submodules/halo-ce-universal/port/ps2/src/ps2_cache.c`.

## Verification and limits

`python3 -m pytest -q tests/test_cbsp.py tests/test_ctag_schema_walk.py` passed (26 tests). This included the actual Blood Gulch HP2 artifact and host-compiled `ps2_cbsp.c`. The result compares all 1,296,384 materialized bytes; the unchanged bytes remain unchanged and each recorded pointer is rebased by its declared domain. `python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory` also passed target compilation: `compiled_count=369`, `failed_count=0`, R5900 GCC `15.2.0`, manifest SHA-256 `8fa834f2185dd9dae225c51ef236d6491e2ab9449c3e6f7cc9eb2eb7c407485a`. This is compile-closure evidence only (M0 gate remains open); combined production link and guest requalification are still required.

Still required for Step 7:

1. The R5900 compile/link closure must pass with the new interface.
2. Invoke CE schema/tag validation and `structure_bsp_port_verify` on the materialized Blood Gulch BSP before publishing CE BSP globals.
3. Exercise and compare actual CE collision, surface/material, cluster-PVS, and sound-cluster queries; validate their references stay inside the BSP and CTAG allocations.
4. Cover a second structurally different retail BSP and malformed CBSP/CTAG pairs on the target path. The current test validates one real BSP and synthetic failure cases.
5. Keep `collision_bsp`, clusters, surfaces, PVS, sound-cluster data, pathfinding data, and referenced materials/lightmaps intact. No fields were removed or externalized.

The independent audit [`m2-step7-independent-audit.md`](m2-step7-independent-audit.md) predates this C materializer run and interface hardening. Its findings about CE verifier/query acceptance and the remaining open gates still apply; its statement that actual Blood Gulch had not reached the C materializer is superseded by this report and the new test result.
