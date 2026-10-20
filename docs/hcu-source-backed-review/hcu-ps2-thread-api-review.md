# M0 rooted CE thread API review

Five rooted Win32 APIs form one incomplete thread contract: `CreateThread`,
`SetThreadPriority`, `ResumeThread`, `GetExitCodeThread`, and thread-handle
`CloseHandle` (which is also shared with files and mutexes).
`source/bungie_net/common/thread_win32.c::create_thread` allocates a CE thread
reference, creates the worker suspended, maps priority flags, requires
`SetThreadPriority` success, and then resumes it. `thread_has_exited` considers
a thread done only when `GetExitCodeThread` succeeds and the code is not
`THREAD_STILL_ACTIVE`; `dispose_thread` closes the handle.

The current PS2 generated bodies do not implement that contract:

- `CreateThread` returns `NULL`, forcing CE's UI filesystem initialization to
  run synchronously; that specific fallback is correct and source-backed.
- Player-profile and playlist-profile writers call `create_thread` without a
  synchronous fallback, so failed creation can silently omit persistence work.
  The Winsock transport caller also depends on asynchronous worker creation.
- `SetThreadPriority` returns failure, so a real thread would never reach
  resume through the CE wrapper.
- `ResumeThread` returns zero, which the CE wrapper accepts as success even
  though this stub has not resumed anything.
- `GetExitCodeThread` returns failure; CE treats that as “still running,” so a
  real worker paired with this stub can strand wait loops.
- PS2 `CloseHandle` recognizes file and mutex handles, not thread handles.

Keep all five pending. Do not approve the `CreateThread` failure based only on
the UI fallback. Closure needs an explicit local thread policy: bounded EE
thread creation/priority/status/close semantics, or caller-by-caller removal
or synchronous conversion with preservation of profile, playlist, filesystem,
and any in-scope transport state. Add lifecycle tests for create-failure,
suspended start, priority mapping, exit/wait, close, and every converted
fallback. The M0 review regression locks the current path and stub behavior; it
does not claim target thread correctness.
