# M0 pinned Newlib numeric parsing and formatting review

This review covers the rooted standard interfaces `atoi`, `atof`, `sprintf`,
`snprintf`, and `vsnprintf`. Each resolves to the exact pinned PS2 EE Newlib
4.6.0 archive member in the current combined link map:

| Symbol | Archive member | Source role |
|---|---|---|
| `atoi` | `libc_a-atoi.o` | Integer prefix conversion, used by HaloScript compilation and text drawing. |
| `atof` | `libc_a-atof.o` | Decimal conversion via Newlib `strtod`, used by HaloScript real-literal compilation. |
| `sprintf` | `libc_a-sprintf.o` | CE string formatting for scripts, object diagnostics, and UI/game state text. |
| `snprintf` | `libc_a-snprintf.o` | Bounded formatting used by CE runtime/console and tag utilities. |
| `vsnprintf` | `libc_a-vsnprintf.o` | Bounded variadic formatting used by CE `csprintf`, error, and console paths. |

The source pin is `ps2toolchain_ee_newlib` commit
`8881dc4b138f0561596980ac9a481c7e638aebd0` from
[`toolchain-sources.json`](../config/toolchain-sources.json#L19). Newlib's
`atoi.c` delegates to `_strtol_r`; `atof.c` delegates to `_strtod_r`; the
formatted interfaces use the pinned Newlib vfprintf implementation and
destination-stream variants. They are real library owners, not generated
placeholders. `printf`/`puts` share the same formatting/stream family, with
stdout's PS2SDK `tty0:` route separately traced in
[`hcu-ps2-libc-stdout-review.md`](hcu-ps2-libc-stdout-review.md).

The ledger disposition confirms implementation ownership only. It does not
claim that every CE format specifier, floating-point edge case, truncation
boundary, or historical MSVC formatting quirk has been matched. In particular,
HaloScript numeric-literal parity and EE soft-double cost belong in later
source-parity tests/profiling; the current closure/guest test proves these
archive members are linked into the bootable image, not that all gameplay
scripts have been exercised. CE's legacy unbounded `sprintf` callers retain
their existing buffer-capacity obligations. The custom `_snprintf`,
`_vsnprintf`, `_vsnwprintf`, and wide formatting adapters are deliberately not
included in this approval.

`test_pinned_newlib_numeric_format_helpers_resolve_to_exact_archive_members`
locks exact source, map members, per-symbol ledger entries, and the explicit
open status of the custom XDK-style formatting symbols.
