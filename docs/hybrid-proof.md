# M08 hybrid proof

M08 is complete. Original Halo datum and integer-point operations drive a synthetic visible object. The project boundary is `src/hybrid/boundary.h`. Command and snapshot types in `src/hybrid/protocol.h` contain handles and scalars only.

`python3 tools/build_hybrid_host.py` runs the shared 18,000-tick script on ILP32. Suppressed, delayed, and normal presentation reads produce event hash `1235839601`, with 30 creations, 30 destructions, and 30 stale rejections. Mutating a copied snapshot does not change the next capture.

`make hybrid-elf` links the unchanged `data.c` and `integer_math.c` with that script and the platform presenter in `src/hybrid/ee_main.c`. The ELF SHA-256 is `defae213cf558a118194137d99e5fa8088d9e6f61dd8605c3e1e1e8ebcc7e3ca`. DMA, VIF, VU1, and GS calls are confined to `ee_main.c`.

`make test-emulator SCENARIO=hybrid` ran PCSX2 2.8.2 at parent `722778f` in both CPU modes. Each mode reported the same three schedule hashes and `elapsed_ms=600033`. Heap stayed `1269760`. Chain high-water stayed 20. Window captures are `visible-start.png`, `visible-motion.png`, and `visible-final.png` in the retained run directories. `python3 tools/qualify_hybrid.py` rechecked those logs. The qualification record is ignored `build/emulator/hybrid-qualification.json`.

This object is not a Halo player, weapon, or retail scene. Guest elapsed time is not a physical-console performance measurement.
