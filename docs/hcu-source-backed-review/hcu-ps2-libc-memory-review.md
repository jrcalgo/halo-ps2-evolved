# M0 bounded libc memory-helper review

**Scope:** four rooted Newlib byte-memory primitives, reviewed against the pinned PS2 EE Newlib source, current caller identities in the M0 ledger, and the exact combined optical-profile link map. `memcpy` is intentionally still pending because its 100+ rooted caller sections require a separate non-overlap/caller-bounds audit.

## Provenance and providers

The source pin is `ps2toolchain_ee_newlib` commit `8881dc4b138f0561596980ac9a481c7e638aebd0` ([pin record](../config/toolchain-sources.json#L19-L24)). Its build checkout is `build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libc/string/`. The current [optical machine link map](../build/hcu-parent-link-probe/hcu-gameplay-machine-optical.map) resolves the routines from EE Newlib's `libc.a(libc_a-{memchr,memcmp,memcpy,memmove,memset}.o)` members. The rooted ledger binds each name to its exact live caller sections and SHA-256-pinned source candidates.

| Symbol | Newlib source | Contract relied on by callers |
|---|---|---|
| `memchr` | `newlib/libc/string/memchr.c` | Searches only the specified byte count and returns a pointer to the first match or null. |
| `memcmp` | `newlib/libc/string/memcmp.c` | Compares only the specified byte count and returns ordering/equality; used for signatures, binary headers, and CE string/memory comparisons. |
| `memmove` | `newlib/libc/string/memmove.c` | Copies the specified byte count with overlap allowed; required by CE's generic move paths. |
| `memset` | `newlib/libc/string/memset.c` | Writes the specified byte count with the low byte of the fill value. |

These are deterministic CPU memory operations with no OS, file, display, audio, or network side effects. No PS2 replacement or empty stub is appropriate. This review approves the provider and API-level role, not the correctness of every caller's length calculation; caller bounds remain covered by the relevant tag/cache/parser and arena checks. Although Newlib `memcpy.c` and its linked archive member are identified, the ledger keeps `memcpy` pending until its large live caller set has been checked for the non-overlap precondition and size bounds.

## Verification limits

The current optical-profile combined ELF links with zero undefined imports, and the PCSX2 guest run exercises the same EE Newlib runtime during startup and asset reading. Focused host tests cover the CE/PS2 tag, file, and cache consumers, but they do not execute the EE Newlib member in isolation. Keep the provider pinned; include overlap, zero-length, alignment, and boundary vectors in target libc qualification before final performance release. This does not close the other 472 rooted symbols.
