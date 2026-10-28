# C3 screen-effect copy probe

## What this build exercises

The movement-trace build registers an optional post-world hook. For each
rendered frame, it copies the current CT16S back buffer (512x448) into a
dedicated 64-page GS texture slot, flushes the GS texture view, and emits
point-sampled quads with one scissor per view. Each quad uses that view's
absolute framebuffer UV rectangle and clamps V to copied row 447. The quads
are emitted on the existing geometry chain before HCU HUD requests; they do
not submit or present a second frame. The trace-only dispatcher skips a raw
screen-effect mask draw only after the copy probe successfully emitted every
view quad. Normal builds register no callback and retain the original texture
cache partition.

The BSP slot refuses a second write while the previous copy's carrying kick
has not completed both VIF1 and GS fences. It also refuses a second copy in
the same frame. This protects the one-slot allocation if future callers build
frames before the earlier kick completes.

This probe copies and reproduces the world image. It does not implement CE's
sniper warp, mask convolution, light enhancement, or desaturation passes, so
it is not visual qualification of the scope effect.

## Build and host checks

The pinned one-view target build is
`build/c3/first-person-fix/integration/quiet-baseline-v1-screen-effect-copy-probe-r7/desktop-launch.json`.
Its ELF SHA-256 is
`7874f81545fe5840c06f480f1b7cc550637353ffb7dd205c63e0836a5daf2b6c`. The
manifest contains 59 source pins, including the callback and copy helper.
The target link map retains `attach_screen_copy_probe` and
`bsp_render_screen_effect_copy_framebuffer`; the linked ELF has no undefined
symbols. The closure labels the ELF `linked-diagnostic` with `acceptance=false`
because it does not execute a CE frame or map render.

Focused host tests:

- `PYTHONPATH=. pytest -q tests/test_hcu_bitmap_quad.py tests/test_hcu_bitmap_view.py tests/test_hcu_bitmap_dispatch.py tests/test_hcu_bitmap_compose.py tests/test_hcu_bitmap_requests.py` — 2 passed, 3 skipped.
- `cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -Isubmodules/halo-ps2/engine/src submodules/halo-ps2/engine/tests/test_screen_effect.c -o /tmp/test_screen_effect && ASAN_OPTIONS=detect_leaks=0 /tmp/test_screen_effect` — passed (`copy=512x448`, clamp to 512x448 active area, fence guard checks).

## Runtime status

A private launch of the pinned ELF under Xvfb display `:237` exited before
map load. PCSX2 logged `vkCreateDevice failed: VK_ERROR_INITIALIZATION_FAILED`
and `GS failed to open`. The private runner stopped its own Xvfb and did not
interact with the user's desktop. Therefore no actual GS pixels, multi-view
scissor captures, or scratch-reuse captures are available yet. The copy/sample
ordering is compile- and host-helper-tested, but remains runtime-unverified.
