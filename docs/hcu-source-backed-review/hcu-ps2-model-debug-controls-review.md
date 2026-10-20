# M0 source review: model debug controls

## Disposition

Five rooted model controls are `excluded-proven` as optional developer diagnostics: `render_model_index_counts`, `render_model_markers`, `render_model_no_geometry`, `render_model_nodes`, and `render_model_vertex_counts`.

## Source review

`source/models/models.c:1063-1080` uses `render_model_nodes` only to draw parent-node lines and node matrices from the already constructed node palette. `models.c:1082-1113` uses `render_model_markers` to transform existing marker definitions through existing node matrices and draw their matrices/names. Neither changes the palette, nodes, markers, or object transform.

`models.c:1115-1224` computes optional vertex/index count labels and emits them through debug text. Geometry selection, LOD selection, and the normal model submission path are independent of the count flags. The associated host/PS2 platform renderer does not need these labels to make a model draw.

`render_model_no_geometry` is the only visual toggle that bypasses ordinary model geometry submission (`models.c:324-326`). Its CE default is false (`source/hs/hs_globals_external.c:2595`), and it is exposed as a developer/script debug control. Its effect is limited to suppressing model geometry when deliberately enabled; animation/node state and object simulation continue. That deliberate diagnostic mode is not part of the PS2 product acceptance path, so the PS2 adapter may omit the switch while preserving normal geometry rendering. If user-facing mod scripts are later expected to control this debug variable, reassess the decision as tooling compatibility, not gameplay parity.

## Regression guard

The test ties every disposition to the source-backed branch and verifies geometry draw conditions are not gated by count/marker/node toggles, while no-geometry is only a rendering conditional and defaults false. This does not claim visual parity for the actual PS2 model renderer.
