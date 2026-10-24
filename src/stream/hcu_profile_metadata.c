#include "stream/hcu_profile_metadata.h"
#include "stream/sha256.h"
#include <string.h>

#define HCM_HEADER_BYTES 32u
#define HCM_BITMAP_BYTES 56u
#define HCM_CBSP_BYTES 76u
#define HCM_RANGE_BYTES 12u

static uint16_t get16(const uint8_t *p)
{ return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static int add_size(size_t a, size_t b, size_t *out)
{ if (b > (size_t)-1 - a) return 0; *out=a+b; return 1; }
static int mul_size(size_t a, size_t b, size_t *out)
{ if (a && b > (size_t)-1/a) return 0; *out=a*b; return 1; }

static void digest_bytes(const uint8_t *p, size_t n, uint8_t digest[32])
{
	sha256_context sha;
	sha256_init(&sha);
	sha256_update(&sha, p, (uint32_t)n);
	sha256_final(&sha, digest);
}

int hcu_profile_metadata_decode(const void *bytes, size_t byte_count,
	const uint8_t expected_sha256[32], uint32_t expected_profile_id,
	void *storage, size_t storage_bytes, hcu_profile_metadata_view *view)
{
	const uint8_t *p=(const uint8_t *)bytes;
	uint8_t digest[32];
	uint32_t profile_id, bitmap_count, cbsp_count, range_count;
	size_t bitmap_bytes, cbsp_bytes, range_bytes, total, needed, at;
	uint8_t *out=(uint8_t *)storage;
	uint32_t i;
	if (!p || !expected_sha256 || !view || (!storage && storage_bytes))
		return HCU_PROFILE_METADATA_E_ARGUMENT;
	if (byte_count < HCM_HEADER_BYTES || byte_count > 0xffffffffu ||
		memcmp(p, "HCM1", 4) != 0 ||
		get16(p+4) != 1 || get16(p+6) != HCM_HEADER_BYTES ||
		get32(p+8) != byte_count || get32(p+28) != 0)
		return HCU_PROFILE_METADATA_E_FORMAT;
	profile_id=get32(p+12); bitmap_count=get32(p+16);
	cbsp_count=get32(p+20); range_count=get32(p+24);
	if (profile_id != expected_profile_id) return HCU_PROFILE_METADATA_E_PROFILE;
	if (!mul_size(bitmap_count,HCM_BITMAP_BYTES,&bitmap_bytes) ||
		!mul_size(cbsp_count,HCM_CBSP_BYTES,&cbsp_bytes) ||
		!mul_size(range_count,HCM_RANGE_BYTES,&range_bytes) ||
		!add_size(HCM_HEADER_BYTES,bitmap_bytes,&total) ||
		!add_size(total,cbsp_bytes,&total) || !add_size(total,range_bytes,&total) ||
		total != byte_count || !add_size(bitmap_bytes,cbsp_bytes,&needed) ||
		!add_size(needed,range_bytes,&needed)) return HCU_PROFILE_METADATA_E_FORMAT;
	digest_bytes(p,byte_count,digest);
	if (memcmp(digest,expected_sha256,32)) return HCU_PROFILE_METADATA_E_HASH;
	if (needed > storage_bytes || (needed && !out)) return HCU_PROFILE_METADATA_E_CAPACITY;
	/* Native table starts aligned for the strongest table member. */
	if (needed && ((uintptr_t)out & 3u)) return HCU_PROFILE_METADATA_E_ARGUMENT;
	memset(view,0,sizeof(*view)); view->profile_id=profile_id;
	at=HCM_HEADER_BYTES;
	view->bitmap_count=bitmap_count;
	view->bitmap_bindings=(const hcu_bitmap_binding *)out;
	for (i=0;i<bitmap_count;i++,at+=HCM_BITMAP_BYTES) {
		hcu_bitmap_binding *b=(hcu_bitmap_binding *)(out+i*HCM_BITMAP_BYTES);
		b->bitmap_output_datum=get32(p+at); b->bitmap_index=get16(p+at+4);
		b->image_index=get16(p+at+6); b->chunk_id=get32(p+at+8);
		b->expected_source_datum=get32(p+at+12); b->expected_profile_id=get32(p+at+16);
		memcpy(b->expected_chunk_sha256,p+at+20,32);
		b->cache_key=get16(p+at+52); b->reserved=get16(p+at+54);
		if (b->reserved || b->chunk_id > 0xffffu || b->cache_key >= 4096)
			return HCU_PROFILE_METADATA_E_FORMAT;
	}
	view->cbsp_count=cbsp_count;
	view->cbsp_bindings=(const hcu_profile_cbsp_binding *)(out+bitmap_bytes);
	for (i=0;i<cbsp_count;i++,at+=HCM_CBSP_BYTES) {
		hcu_profile_cbsp_binding *b=(hcu_profile_cbsp_binding *)(out+bitmap_bytes+i*HCM_CBSP_BYTES);
		b->source_file_offset=get32(p+at); b->source_file_size=get32(p+at+4);
		b->media_chunk_id=get32(p+at+8); memcpy(b->source_map_sha256,p+at+12,32);
		memcpy(b->expected_chunk_sha256,p+at+44,32);
		if (!b->source_file_size) return HCU_PROFILE_METADATA_E_FORMAT;
	}
	view->resource_range_count=range_count;
	view->resource_ranges=(const hcu_profile_resource_range *)(out+bitmap_bytes+cbsp_bytes);
	for (i=0;i<range_count;i++,at+=HCM_RANGE_BYTES) {
		hcu_profile_resource_range *r=(hcu_profile_resource_range *)(out+bitmap_bytes+cbsp_bytes+i*HCM_RANGE_BYTES);
		r->output_datum=get32(p+at); r->source_offset=get32(p+at+4); r->size=get32(p+at+8);
		if (!r->size || r->source_offset > 0xffffffffu-r->size)
			return HCU_PROFILE_METADATA_E_FORMAT;
	}
	return HCU_PROFILE_METADATA_OK;
}
