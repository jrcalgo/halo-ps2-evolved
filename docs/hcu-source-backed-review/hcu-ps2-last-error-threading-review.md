# M0 rooted last-error threading review

Both `GetLastError` and `SetLastError` are rooted across two distinct source
domains. CE `source/tag_files/files_windows.c` checks the error after failed
open/stat/seek/read/write operations, uses it to distinguish missing paths from
other failures, emits diagnostics, and often clears it for the next operation.
CE `source/input/input_xbox.c` reaches XInput calls; the PS2 `XInputOpen`
adapter sets `ERROR_DEVICE_NOT_CONNECTED` through `SetLastError`.

The PS2 provider currently stores both APIs in one static `ps2_last_error`
(`port/ps2/src/ps2_edge.c`). That is process-global, whereas Win32 last-error
state belongs to the calling thread. If input polling and a file operation can
run concurrently, an input failure can replace a file error between the file
API and its `GetLastError` consumer (or vice versa). The source tree includes
thread creation and mutex interfaces, and no reviewed call graph or runtime
trace proves all relevant operations are serialized on one thread.

Disposition remains `pending` for both symbols. Do not approve the current
global slot on the basis that most M1 startup work appears synchronous. Close
this only after either (a) the full production call graph and target trace prove
the relevant operations share a serialized thread, or (b) the adapter provides
per-thread last-error storage and tests error isolation across CE file and
input callers. The focused regression records the current risk, not a pass of
the Win32 contract.
