#ifndef HCU_BITMAP_OWNER_LAYOUT_H
#define HCU_BITMAP_OWNER_LAYOUT_H

#include <stddef.h>
#include <stdint.h>

/* Shared with hcu_main.c so the boot guard and host layout test use the same
 * production accounting, including all typed allocations and worst padding. */
static inline size_t hcu_bitmap_owner_required(size_t journal_bytes,
	size_t reader_bytes, size_t slot_bytes, size_t lease_bytes,
	size_t queue_bytes, size_t source_bytes, size_t staging_bytes,
	size_t descriptor_bytes)
{
	return journal_bytes + reader_bytes + slot_bytes + lease_bytes +
		queue_bytes + source_bytes + staging_bytes + descriptor_bytes + 8u * 15u;
}

#endif
