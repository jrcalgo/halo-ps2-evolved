# C3 sniper second zoom freeze fix

## Failure evidence

The user confirmed the failure is a frozen picture while PCSX2 remains open. The
read-only log for the visible quiet Blood Gulch guest records:

```text
[ 157.4081] HALO_PS2_FAIL c3-render frame-end frame=1455
```

The C3 view path rejects vertical fields of view below `0.1` radians. An active
view with a rejected snapshot camera is skipped. If that leaves the frame with
no rendered views, BSP frame-end fails and the render loop stops producing
frames, which matches the reported freeze.

CE computes the scoped weapon angle, then converts it to vertical FOV with
`2*atan(0.75*0.85*tan(native_fov/2))`. At 10x, the 70 degree base weapon angle
becomes 7 degrees; the converted vertical FOV is `0.07794286` radians. That is a
valid, finite camera value, but it was incorrectly rejected by the HCU `0.1`
radian floor.

## Change

The HCU camera validator now accepts FOVs down to `0.019` radians. CE's weapon
FOV function only returns magnified angles above `pi/100`; converting that
boundary produces `0.02002863` radians, leaving about `0.001` radians of float
rounding margin. The validator still rejects lower values, zero, negative,
non-finite values, values above `2.8` radians, invalid bases, and invalid aspect
ratios. It does not clamp or alter the weapon's magnification.

The host fixture exercises the production conversion at 70, 35, and 7 degrees,
the narrowest legal CE weapon angle, and confirms the generated engine camera
projection remains finite. It also checks invalid narrow and non-finite inputs
are refused.

## Verification

```text
python3 -I -m pytest -q tests/test_hcu_render_views.py
3 passed
```

The visible desktop guest was read-only throughout. A private guest using the
same frozen ELF and cloned data reached Blood Gulch, but still had a pistol, so
it did not exercise the sniper pickup or second zoom. A full runtime regression
with the sniper equipped remains necessary before claiming the in-game fix is
confirmed.
