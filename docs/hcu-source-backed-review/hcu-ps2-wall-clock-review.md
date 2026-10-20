# M0 rooted wall-clock API review

Do not treat wall-clock time as interchangeable with the monotonic EE timer.
The already-reviewed PS2SDK `GetTimerSystemTime` service supports wrapping
`GetTickCount` and performance counters. The three symbols here serve a
different contract and remain pending.

`source/cseries/cseries_windows.c::system_seconds` returns `time(NULL)`.
`source/cseries/errors.c::write_to_error_file` also reads `time`, then calls
`localtime` when its date flag is set and prints local civil time into the
error log. `port/ps2/src/ps2_time.c::GetSystemTime` reads `time(NULL)`, calls
`gmtime_r`, and copies UTC fields into XDK `SYSTEMTIME` (milliseconds are
always zero). These paths therefore depend on both the console RTC and a
documented timezone policy; they are not frame timing.

The target map resolves `gmtime_r` and `localtime` from pinned Newlib. The PS2SDK
libc glue (`submodules/ps2sdk/ee/libcglue/src/rtc.c`) obtains wall time through
`ps2time(NULL)` and computes a bus-clock offset. That identifies the provider,
but does not prove that every OPL-launched/PCSX2/optical startup path has the
CDVD RTC RPC ready, that an unset RTC is distinguished from a valid date, or
that timezone state is configured consistently. `localtime` additionally
depends on Newlib timezone and shared conversion state. CE's error logger then
depends on file-backed `fopen`/`fprintf`/`fflush`, which remain unqualified for
the read-only M1 profile.

Keep `time`, `gmtime_r`, and `localtime` pending. Close them only after the
startup contract establishes RTC readiness/failure handling, tests UTC and
local conversion around leap/month/year boundaries and timezone policy, and
proves error logging handles absent or invalid time without corrupting CE
state. The monotonic timer review remains separate.

Regression anchor: `tests/test_hcu_external_review.py::test_wall_clock_apis_are_separate_from_monotonic_timer_and_remain_pending`.
It verifies caller separation, exact target providers, UTC field copying, and
the unresolved file-log dependency. Host/source checks are not an RTC device
test.
