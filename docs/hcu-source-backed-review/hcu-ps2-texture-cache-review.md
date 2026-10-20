# M0 CE texture-cache root review

The five pending roots are one integration boundary, not isolated drawing
calls. `scenario_tags_load` opens the texture cache before scenario tags are
loaded; `scenario_tags_unload` closes it before tag teardown. In CE,
`texture_cache_open` validates the cache datum, while `texture_cache_close`
flushes outstanding work and invalidates that datum. The no-op PS2 bodies do
not implement that lifecycle. The parent has a GS texture-pack/cache owner,
but no source-backed handoff proves it owns this CE datum or its map transition
semantics.

The HaloScript `texture_cache_flush` call kicks/waits the D3D push buffer and
flushes the LRU. A zero-return no-op is not yet equivalent to a parent GS cache
flush. `texture_cache_debug_options` supplies writable script booleans for the
graph/list diagnostics; CE reads them when building texture-cache debug output.
Their zero-initialized storage is safe only if the PS2 script/UI policy for
those options is explicitly excluded.

`_texture_cache_bitmap_get_hardware_format` is more widely rooted: decals,
particle/light rendering, predicted-resource precache, object lights, and
weapon projectile-trail precache query or load D3D texture formats through it.
Some use the result only to decide whether/how to draw; others participate in
resource discovery and cache load state. Returning `NULL` for all calls may
therefore be a valid renderer separation in some paths but cannot be approved
without tracing all callers against HP2 packs and CE tick/resource effects.

All five ledger entries remain `pending`. Closure needs an explicit ownership
adapter from CE tag/resource lifecycle to the parent texture packs, per-caller
confirmation that a missing hardware-format pointer cannot change simulation
or precache progress, plus map load/unload and flush tests. This report does
not require D3D or approve dropping CE resource state. The caller/root review
is locked by `test_ce_texture_cache_roots_are_stateful_and_remain_pending`.
