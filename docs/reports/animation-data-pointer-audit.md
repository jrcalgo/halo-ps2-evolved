# CE `animation.data` pointer-use audit

**Purpose:** complete the call-site inventory required before considering the
M2 animation-payload capacity candidate. This is a source audit, not a format
change or evidence that an animation cache meets RAM/CPU/DVD limits.

**Sources examined:** the current `halo-ce-universal` checkout under
`source/models/` and `port/linux/game/`, including the PS2-selected retail tag
schema and the accessors used by CE pose generation. The schema declares
`struct animation.data` as `_tag_schema_data`, not
`_tag_schema_file_data` ([schema declaration](../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L1208)).
The retail range audit reports this field's candidate source ranges but does
not externalize them ([range audit](retail-animation-data-ranges-v1.json),
[audit tool](../../tools/audit_animation_data_ranges.py)).

## Direct access inventory

| Site | Read behavior | External-storage consequence |
|---|---|---|
| [`animation_data_problem`](../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L862) | During the animation schema check, compressed animations directly compute `animation->data.address + compressed_data_offset`, read the compressed header, and walk defaults, node headers, keyframe values, and keyframe frame-index arrays through `compressed_animation_keyframes_problem`. Uncompressed validation only uses `data.size` for frame-count bounds. [`animation_check`](../submodules/halo-ce-universal/port/linux/game/tag_schema_models.c#L933) invokes this before a graph is accepted. | A runtime-only frame accessor is insufficient. Compressed payload bytes must be made available to the schema check (including all tables it scans), or the validator must gain an explicit PS2 typed-external-data validation path. A null/out-of-image pointer currently fails the schema's ordinary `_tag_schema_data` ownership checks before/while the callback runs. |
| [`animation_get_frame_data`](../submodules/halo-ce-universal/source/models/model_animation_definitions.c#L500) | Calls `tag_data_get_pointer(&animation->data, 0, 0)` and returns either a frame offset (`frame_index * frame_size`) or the compressed-data offset. The result is consumed by frame validation and the uncompressed rotation/translation/scale decode paths in [`model_animations.c`](../submodules/halo-ce-universal/source/models/model_animations.c#L850). | This is the common accessor for uncompressed frames and some compressed paths, but it returns a raw pointer with no lease/release boundary. Callers assume it remains valid for the duration of their decode. |
| [`animation_get_keyframe_rotation`](../submodules/halo-ce-universal/source/models/model_animations.c#L2145) | Directly calls `tag_data_get_pointer(&animation->data, compressed_data_offset, 0)`, then reads the compressed header, per-node headers, default quaternions, keyframe quaternions, and frame-index arrays. | The full compressed record or a range-aware stable accessor is required. The backing bytes must not be evicted while the helper is using pointers into them. |
| [`animation_get_keyframe_translation`](../submodules/halo-ce-universal/source/models/model_animations.c#L2289) | Same pattern for compressed translation defaults, node headers, keyframes, and frame indices. | Same lifetime and bounds requirement; it is a separate direct path and must not be missed by a wrapper around frame extraction. |
| [`animation_get_keyframe_scale`](../submodules/halo-ce-universal/source/models/model_animations.c#L2424) | Same pattern for compressed scale defaults, node headers, keyframes, and frame indices. | Same lifetime and bounds requirement. |
| [`animation_data_contains`](../submodules/halo-ce-universal/source/models/model_animations.c#L2575) | Reads only `animation->data.size` and validates offset/count arithmetic; it does not fetch payload bytes. It is used by frame validation and compressed access bounds checks. | The size metadata must remain the original logical record length even if its bytes move. This helper alone does not prove the backing range is resident. |

## Simultaneous-pointer and adjacent-field constraints

`animation_get_node_orientations` obtains four frame pointers (`data00`,
`data10`, `data01`, `data11`) before decoding a yaw/pitch blend
([call sites](../submodules/halo-ce-universal/source/models/model_animations.c#L1867)).
They all refer to the same `animation.data` allocation, but an accessor that
reuses/evicts one staging buffer on every call would invalidate earlier
pointers. A lease-based or one-acquisition-per-animation API is needed, with
the storage held through the complete orientation calculation. Other frame
interpolation paths similarly obtain current/next frame pointers before use
([example](../submodules/halo-ce-universal/source/models/model_animations.c#L1603)).

Do not conflate this candidate with the adjacent fields:

- `animation.default_data` remains a separate schema-owned tag-data allocation
  and supplies the default pose ([access](../submodules/halo-ce-universal/source/models/model_animation_definitions.h#L62),
  [runtime use](../submodules/halo-ce-universal/source/models/model_animations.c#L862)).
- `animation.frame_info` is separate; CE reads it directly for movement/root
  offsets ([direct read](../submodules/halo-ce-universal/source/models/model_animations.c#L395))
  and through `animation_get_frame_info`
  ([accessor](../submodules/halo-ce-universal/source/models/model_animation_definitions.c#L520)).
- Both adjacent fields remain in the tag image unless independently audited
  and given their own typed relocation/lifetime contract.

## Required contract before implementation

1. Preserve `_tag_schema_data` semantics. The converter must emit a typed
   animation payload table (stable graph/tag identity, field identity, logical
   length, source record/hash, bounded packed offset); it must not silently
   relabel the field as file-data or treat arbitrary DWORDs as pointers.
2. Teach the PS2 tag validator how the typed table authorizes the moved field,
   and validate the complete compressed structures from bounded backing before
   accepting a graph. Keep all other tag-data ownership checks unchanged.
3. Route every runtime read above through one explicit acquire/release or
   stable-view contract. Preserve the original `data.size`, validate each
   subrange before dereference, support four simultaneous frame views, and
   cover compressed and uncompressed paths. Retain the independent
   `default_data` and `frame_info` paths.
4. Add production-C parity fixtures for compressed/uncompressed animations,
   malformed offsets, truncated table data, eviction while views are live,
   two-frame interpolation, four-frame yaw/pitch blending, and schema validation
   of the external record. Compare decoded orientations and movement offsets
   with the unmodified retail in-image representation.
5. Measure peak staging/cache bytes, cache misses, bytes/read, IOP/DVD latency,
   and simulation tick time under campaign and multiplayer scenes, including
   1–4 local players and simultaneous object/first-person animation work.
   Reject any design that invalidates a returned pointer or blocks the 30 Hz
   tick; conversion range arithmetic alone is not a runtime qualification.

**Disposition:** inventory complete enough to rule out a wrapper around only
`animation_get_frame_data()`. The validator's direct `animation.data.address`
read and the three compressed runtime readers are separate mandatory routes.
No external-data representation, cache policy, or capacity solution is chosen
by this report; the nine-map M2 lower-bound gap remains open.
