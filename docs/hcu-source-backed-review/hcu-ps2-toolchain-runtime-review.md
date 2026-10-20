# M0 rooted toolchain-runtime review

**Scope:** the 16 rooted compiler helper symbols below, reviewed against the exact optical-profile combined machine link map and the pinned PS2 EE GCC source. This is an implementation/provider review, not a claim that double arithmetic is fast on the EE.

## Provider and source provenance

The source pin is `ps2toolchain_ee_gcc` commit `df77d03bc1bd5765b40de554918a5ff541202548`, recorded in [`toolchain-sources.json`](../config/toolchain-sources.json#L12-L16). The checked-out build source is `build/toolchain/sources/ps2toolchain_ee_gcc`; its `libgcc` contents include `libgcc/soft-fp/{adddf3,subdf3,muldf3,divdf3,extendsfdf2,fixdfsi,floatdidf,floatdisf,floatsidf,truncdfsf2,gedf2,ledf2}.c` and `libgcc/libgcc2.c`. GCC's `gedf2.c` provides the `__gtdf2` alias and `ledf2.c` the `__ltdf2` alias. The pinned generic implementations of 64-bit integer multiply/divide/remainder are in `libgcc/libgcc2.c` (`__muldi3`, `__divdi3`, `__moddi3`, `__udivdi3`). These are required compiler ABI routines, not PS2 platform placeholders.

The exact optical-profile link map [`hcu-gameplay-machine-optical.map`](../build/hcu-parent-link-probe/hcu-gameplay-machine-optical.map) resolves the floating-point helpers from the EE `15.2.0/libgcc.a` archive members `_addsub_df.o`, `_mul_df.o`, `_div_df.o`, `_sf_to_df.o`, `_df_to_si.o`, `_floatdidf.o`, `_floatdisf.o`, `_si_to_df.o`, `_gt_df.o`, `_lt_df.o`, and `_df_to_sf.o`; it resolves the 64-bit integer helpers from `libgcc.a(lib2funcs.o)`. The caller-section and caller-source identities are recorded per symbol in [`hcu-ps2-external-review.json`](hcu-ps2-external-review.json), against that ledger's rooted-object hash.

## Individual dispositions

| Rooted symbol | Implementation source / linked member | Semantic role |
|---|---|---|
| `__adddf3`, `__subdf3` | `libgcc/soft-fp/{adddf3,subdf3}.c` / `_addsub_df.o` | CE double addition/subtraction emitted from live object, physics, camera, unit, and sound code. |
| `__muldf3`, `__divdf3` | `libgcc/soft-fp/{muldf3,divdf3}.c` / `_mul_df.o`, `_div_df.o` | CE double multiply/divide used by live physics, input, camera, unit, and timing code. |
| `__extendsfdf2`, `__truncdfsf2` | `libgcc/soft-fp/{extendsfdf2,truncdfsf2}.c` / `_sf_to_df.o`, `_df_to_sf.o` | IEEE single/double conversion preserving CE's compiled expression semantics. |
| `__fixdfsi`, `__floatsidf` | `libgcc/soft-fp/{fixdfsi,floatsidf}.c` / `_df_to_si.o`, `_si_to_df.o` | Double-to-integer and integer-to-double conversions in live CE math and timing paths. |
| `__floatdidf`, `__floatdisf` | `libgcc/soft-fp/{floatdidf,floatdisf}.c` / matching archive members | Signed 64-bit integer conversions used by game timing/object code. |
| `__gtdf2`, `__ltdf2` | `libgcc/soft-fp/{gedf2,ledf2}.c` / `_gt_df.o`, `_lt_df.o` | IEEE ordered comparisons used by live player-control, item, camera, and sound paths. |
| `__muldi3`, `__divdi3`, `__moddi3`, `__udivdi3` | `libgcc/libgcc2.c` / `lib2funcs.o` | Signed/unsigned 64-bit arithmetic used by BSP indexing, encounter timing, input timing, and the PS2 timer adapter. |

`__sync_val_compare_and_swap_4` is deliberately **not** included in this disposition: the rooted map resolves it to the local `ps2_edge.o`, so it requires a separate review of that adapter's synchronization semantics.

## Limits and evidence

The optical-profile parent/HCU image has zero undefined symbols; its source map binds these exact helpers into the linked image. `python3 tools/hcu_ps2_abi_host.py` passes host-ILP32 and R5900 compile-only ABI assertions, and the current PCSX2 optical run reaches the M1 map-request marker. These checks establish provider/link/ABI/startup reachability; they are not per-operation IEEE test vectors or an EE cycle benchmark. GCC's EE `libgcc` software-double implementation is retained to preserve CE's compiled behavior. No double-to-single rewrite or math substitution is approved here. Numerical edge-case vectors and EE performance measurements remain explicit M6 qualification work.
