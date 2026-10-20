# M0 rooted Win32 mutex versus EE semaphore review

The rooted CE callers all enter through `source/bungie_net/common/thread_win32.c`:
`create_mutex` calls `CreateMutexA`, `take_mutex` accepts both
`WAIT_OBJECT_0` and `WAIT_ABANDONED`, `release_mutex` ignores the Win32 return,
and `dispose_mutex` closes the handle. This is a shared synchronization
primitive, not a drawing or diagnostic-only API.

The PS2 edge adapter uses EE binary semaphores. It ignores mutex names and
attributes, has no owning-thread or recursion state, and `ReleaseMutex` signals
without owner validation. `WaitForSingleObject` maps `WaitSemaEx` failures on
the timed path uniformly to `WAIT_TIMEOUT`; it never reports
`WAIT_ABANDONED`. Thus an EE semaphore may be enough for a constrained
single-owner usage pattern, but that usage has not been established by this
source trace. The CE wrapper does not encode the needed proof, and the adapter
does not implement the full Win32 contract.

Keep `CreateMutexA`, `WaitForSingleObject`, and `ReleaseMutex` pending. Do not
promote them based solely on successful startup or the fact that the PS2
kernel calls compile. Closure requires a reviewed production call graph
showing single-owner/non-recursive use with no abandoned-owner observation, or
an EE implementation that preserves those semantics, plus target tests for
initial ownership, lock/unlock, timeout, invalid handles, wrong-owner release,
and disposal. `CloseHandle` is separately pending because it also handles
files and threads. The source regression records these gaps rather than
claiming behavioral equivalence.
