# Retail split-screen field of view (2026-11-10)

Source: static analysis of the retail Xbox `default.xbe` (`compute_window_bounds` 0xbba00, camera frustum 0x5bcb0, vertical angle
constant 0.6375 at 0x1f1010) and CE `render_cameras.c`.

- 1 player: 70 deg horizontal, 55.4 deg vertical (the port keeps the menu FOV slider here).
- More than one window: every window has the same vertical angle, 56.35 deg (half tangent 0.5357); the horizontal angle follows the
  window's physical (4:3 television) shape: 110 deg for the 8:3 windows (2 players, the top window of 3), about 71 deg for the 4:3
  windows (4 players, the bottom windows of 3).
- Retail's frustum is slightly off axis (half tangents 2P: -1.4195/+1.4374 across, +0.6071/-0.4642 up/down); the port uses the
  symmetric equivalent.

Port: `hcu_views_set_window_count` (set each frame from the local player count), `hcu_views_vertical_fov`,
`hcu_views_camera_aspect`, `hcu_views_fov_aspect` / `_camera` in `src/stream/hcu_render_views.c`; used by the BSP camera
(`hcu_c3_views_camera`), the object culling frustum and the viewmodel pass. With one window nothing changes.
Test: `tests/hcu_render_views_main.c`. Unverified: viewmodel FOV in retail split screen, the 0.18 s FOV transition.
