# M0 rooted `_control87` rounding-state review

`real_math_reset_precision` calls `_control87(CW_DEFAULT, 0xFFFFF)` and is
rooted at initialization, each game tick, and map transition. The PS2 float
header accurately notes that the R5900 has no x87 control word; it defines
`CW_DEFAULT` with `_RC_NEAR` and `_PC_53`, and the current generated stub does
nothing and returns zero. The return value is ignored by CE.

The lack of x87 precision control is expected on the EE, and CE `real` values
are single precision, but this does not by itself prove the zero stub preserves
the requested rounding behavior. The R5900 has its own FCR rounding control,
and neither the CE caller nor the current test evidence proves what value is
selected after SDK/runtime initialization or whether another EE service can
change it. A host ILP32 build cannot establish the guest FCR state.

Keep `_control87` pending until the PS2 owner either explicitly sets/preserves
the equivalent FCR round-to-nearest mode (while documenting unsupported x87
exception/precision bits) or provides target evidence that the EE runtime
guarantees the needed mode across reset/init and tick call sites. Add a PCSX2
and hardware FCR fixture plus float-parity checks before approval. This review
does not authorize early single-precision math substitutions or waive M6
numerical-parity evidence.
