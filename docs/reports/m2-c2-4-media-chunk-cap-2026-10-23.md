# C2.4 media chunk size increment (2026-10-23)

The HCP1 profile path now rejects `MEDIA` directory entries larger than 65,536 bytes during C preflight, before a profile view is published. The C chunk-read API also checks the limit before copying. The Python HCP1 encoder and strict package validator enforce the same wire rule. Exactly 65,536 bytes remains valid. A focused structural fixture covers the exact limit, encoder rejection at 65,537 bytes, and a manually constructed oversized but otherwise hashed HCP1 package rejected by C preflight.

This cap applies to HCP1 `MEDIA` resources, which are independently addressable decoded assets. It does not apply to the `CE` and `SOUND_META` root entries: those have distinct mount/stream handling and this change does not segment or impose a cap on them. The limit is a persistent package-resource bound; it is not inferred from, or conflated with, HP2's 64 KiB LZ4 back-reference history ring.

This is only the size-bound slice of C2.4. It does not segment oversized logical assets, establish a generic per-resource pin/fence protocol, prove CE gameplay-pointer and DMA/GS reader lifetimes, or provide safe eviction. A producer with a single MEDIA resource above the cap now fails closed and needs a future segmented-resource representation. The existing bitmap request/lease path remains the only specialized reader accounting evidence; no general residency or eviction claim follows from this change.

Focused verification: `python3 -m pytest -q tests/test_hcu_asset_profile_chunks.py` and `git diff --check`.
