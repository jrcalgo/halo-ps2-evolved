# Step 8 Blood Gulch target query probe

## Result

The isolated diagnostic now targets Blood Gulch, the largest stock MP map in
the current static content inventory. Its candidate split is 4,477,120 bytes
of tags and 1,814,336 bytes of BSP, exactly 6,291,456 bytes inside the existing
`current_bsp` region. The final diagnostic ELF passed the Blood Gulch load,
all-row PVS walk, source-oracle collision hit, unload-state and canary checks
in both PCSX2 backends.

The ordinary admission path remains UI-only. Blood Gulch and Sidewinder remain
accepted only when `HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC` is compiled into the
separate diagnostic ELF.

## Diagnostic behavior and source oracle

The guest fixture loads `levels\\test\\bloodgulch\\bloodgulch`, queries all
cluster PVS rows, and checks a positive `collision_test_vector()` result against
the raw retail BSP oracle. The independent source audit selects surface 84,
plane designator 94, material index 0/type 2, from start point
`(65.13331604003906, -87.30911254882812, 19.533559799194336)` with vector
`(0.9637277722358704, -0.26664623618125916, 0.011338776908814907)`. It requires
exactly one qualifying source polygon and validates raw BSP3D/BSP2D routing.
The guest asserts hit, surface 84, and material type 2, then unloads the
scenario. The parent checks arena canaries after the shell returns, but the
diagnostic also checks them directly after unload before printing its
completion marker; the successful recompiler log contains `guards=ok` after
the unload-state assertion.

Source oracle: [`mp-collision-shared-edge-source-oracle.json`](../../build/mp-collision-shared-edge-source-oracle.json), SHA-256
`ff26f43f8e474f59397c441d246b93e3a45f39fdaefca555d5eb7e3bfb54b95a`.
The Blood Gulch source map is 44,328,960 bytes, SHA-256
`9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1`.
The all-BSP package is 2,832,384 bytes, SHA-256
`ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011`.

## Build and guest evidence

Build command: `python3 tools/hcu_parent_link_probe.py --step8-mp-capacity-diagnostic`.
The command completed successfully. Final diagnostic ELF SHA-256 is
`82d06f41b6cf117486d79e1e9c947c3548c5c4530b572f76e50e73bbf8917810`; build
report SHA-256 is
`1a9a27ea7e8a44a950e75f9d7db38f394fc1eccd6284a20c4af340d942f86cfa`.

The initial sandbox launches failed before guest execution because Qt's xcb
plugin could not load without `xcb-cursor0`; `xvfb-run` also could not connect
to its temporary display. With display access, both runs of the final ELF
passed and reached `game-initialize-done`. The recompiler completed in 47.37
seconds and the interpreter in 83.71 seconds. Both emitted:

```text
HALO_PS2_LOCAL step8-mp-capacity-query map=bloodgulch clusters=30 pvs_rows=30 collision_called=1 collision_hit=1 collision_surface=84 collision_material_type=2
HALO_PS2_LOCAL step8-mp-capacity-unloaded map=bloodgulch guards=ok
HALO_PS2_LOCAL step8-mp-capacity-complete map=bloodgulch query_only=1
```

| Backend | Result artifact | Result SHA-256 | Guest log SHA-256 |
|---|---|---|---|
| Recompiler | `build/hcu-ps2-closure/emulator-m1-recompiler-996f53483b2c405984269bd5732ac186/result.json` | `05aa8a8768ceb24cb77d706ee19017bf5731b0b051999eb5e6bae892c36e89a2` | `12a4db4d6aadb1d97f927c58e09485efd47effd027ca16dd3d94c235e36cce41` |
| Interpreter | `build/hcu-ps2-closure/emulator-m1-interpreter-f201703a3e45400e871c135edafdec06/result.json` | `6fd190bd510ff1bc13e3f7d2d31d1c72bd1f4e7189c4fa62a2b517455e368c2b` | `63435af6a2751c04245d5528fe5ad4146d0ed779fe4ccfa4d4df1091dff7457c` |

Both result files report `host_assets_unchanged=true`; both logs contain the
same query, unload-state, canary, and completion markers.

## Limits

This diagnostic does not change product admission or budgets. It does not
establish EE hardware placement/performance, complete multiplayer asset
closure, rendering, or gameplay readiness. This closes only one representative
MP map query slice; keep Step 8 open for all-map owner/lifetime and
gameplay-content gates.
