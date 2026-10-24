#include "stream/hcu_asset_profile.h"
#include "stream/sha256.h"

#include <string.h>

#define HCP_HEADER_SIZE 32u
#define HCP_RECORD_SIZE 48u
#define HCP_ALIGNMENT 16u
#define HCP_SCRATCH 512u

static uint32_t le32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static int read_bytes(hcu_asset_profile_read_at r, void *c, uint32_t o, void *d, uint32_t n)
{ return r(c, o, d, n) == 0; }
static int read_entry(const hcu_asset_profile_view *v, uint32_t i, hcu_asset_chunk_view *e)
{
	uint8_t b[HCP_RECORD_SIZE];
	if (i >= v->chunk_count) return 0;
	if (v->memory_image) memcpy(b, v->memory_image + HCP_HEADER_SIZE + i * HCP_RECORD_SIZE, sizeof(b));
	else if (!read_bytes(v->read_at, v->reader_context,
		HCP_HEADER_SIZE + i * HCP_RECORD_SIZE, b, sizeof(b))) return 0;
	e->type=le32(b); e->chunk_id=le32(b+4); e->offset=le32(b+8); e->size=le32(b+12);
	memcpy(e->sha256,b+16,32); return 1;
}

int hcu_asset_profile_preflight_reader(hcu_asset_profile_read_at reader, void *context,
	uint32_t image_size, uint32_t expected_profile_id, hcu_asset_profile_view *view)
{
	uint8_t h[HCP_HEADER_SIZE], row[HCP_RECORD_SIZE], scratch[HCP_SCRATCH], digest[32];
	uint32_t profile,count,dir_off,dir_size,total,last_end,i,prev_type=0,prev_id=0;
	if (!reader || !view) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if (image_size < HCP_HEADER_SIZE || !read_bytes(reader,context,0,h,sizeof(h))) return HCU_ASSET_PROFILE_E_BOUNDS;
	if (memcmp(h,"HCP1",4) || le32(h+4)!=1 || le32(h+8)!=HCP_HEADER_SIZE) return HCU_ASSET_PROFILE_E_FORMAT;
	profile=le32(h+12); count=le32(h+16); dir_off=le32(h+20); dir_size=le32(h+24); total=le32(h+28);
	if (!profile || !count || count>HCU_ASSET_PROFILE_MAX_CHUNKS || dir_off!=HCP_HEADER_SIZE ||
		dir_size!=count*HCP_RECORD_SIZE || total!=image_size || dir_size>total-dir_off)
		return HCU_ASSET_PROFILE_E_FORMAT;
	if (profile!=expected_profile_id) return HCU_ASSET_PROFILE_E_PROFILE;
	last_end=dir_off+dir_size;
	for(i=0;i<count;i++) {
		uint32_t type,id,offset,size,at,remaining;
		sha256_context sha;
		if(!read_bytes(reader,context,dir_off+i*HCP_RECORD_SIZE,row,sizeof(row))) return HCU_ASSET_PROFILE_E_BOUNDS;
		type=le32(row); id=le32(row+4); offset=le32(row+8); size=le32(row+12);
		if((type<1 || type>3) || (type!=HCU_ASSET_CHUNK_MEDIA && id!=0) ||
			(i && (type<prev_type || (type==prev_type && id<=prev_id))) || !size ||
			(offset&(HCP_ALIGNMENT-1u)) || offset<last_end || offset>total || size>total-offset)
			return HCU_ASSET_PROFILE_E_BOUNDS;
		sha256_init(&sha); at=offset; remaining=size;
		while(remaining) {
			uint32_t take=remaining<sizeof(scratch)?remaining:(uint32_t)sizeof(scratch);
			if(!read_bytes(reader,context,at,scratch,take)) return HCU_ASSET_PROFILE_E_BOUNDS;
			sha256_update(&sha,scratch,take); at+=take; remaining-=take;
		}
		sha256_final(&sha,digest);
		if(memcmp(digest,row+16,32)) return HCU_ASSET_PROFILE_E_HASH;
		last_end=offset+size; prev_type=type; prev_id=id;
	}
	if(last_end!=total) return HCU_ASSET_PROFILE_E_FORMAT;
	/* Publish only after validating roots, using a local candidate until then. */
	{
		hcu_asset_profile_view candidate;
		candidate.read_at=reader; candidate.reader_context=context; candidate.memory_image=0;
		candidate.profile_id=profile; candidate.total_bytes=total; candidate.chunk_count=count;
		candidate.directory_bytes=dir_off+dir_size;
	{
		hcu_asset_chunk_view e;
		if(hcu_asset_profile_lookup(&candidate,HCU_ASSET_CHUNK_CE,0,&e)!=HCU_ASSET_PROFILE_OK ||
			hcu_asset_profile_lookup(&candidate,HCU_ASSET_CHUNK_SOUND_META,0,&e)!=HCU_ASSET_PROFILE_OK)
			return HCU_ASSET_PROFILE_E_FORMAT;
	}
		*view=candidate;
	}
	return HCU_ASSET_PROFILE_OK;
}

typedef struct { const uint8_t *bytes; size_t size; } memory_reader;
static int memory_read(void *context,uint32_t offset,void *destination,uint32_t size)
{
	memory_reader *m=(memory_reader *)context;
	if(offset>m->size || size>m->size-offset) return -1;
	memcpy(destination,m->bytes+offset,size); return 0;
}
int hcu_asset_profile_preflight(const void *image,size_t size,uint32_t profile,hcu_asset_profile_view *view)
{
	int rc;
	if(!image || size>0xffffffffu) return HCU_ASSET_PROFILE_E_ARGUMENT;
	{
		memory_reader m; hcu_asset_profile_view candidate;
		m.bytes=(const uint8_t *)image; m.size=size;
		rc=hcu_asset_profile_preflight_reader(memory_read,&m,(uint32_t)size,profile,&candidate);
		if(rc!=HCU_ASSET_PROFILE_OK) return rc;
		candidate.memory_image=(const uint8_t *)image; candidate.read_at=0; candidate.reader_context=0;
		*view=candidate;
	}
	return HCU_ASSET_PROFILE_OK;
}
int hcu_asset_profile_lookup(const hcu_asset_profile_view *v,uint32_t type,uint32_t id,hcu_asset_chunk_view *out)
{
	uint32_t low=0,high;
	if(!v || !out) return HCU_ASSET_PROFILE_E_ARGUMENT;
	high=v->chunk_count;
	/* The preflight proved strict (type,id) ordering. Stream O(log N) records
	 * instead of retaining the roster directory or scanning it per request. */
	while(low<high) {
		uint32_t middle=low+(high-low)/2u;
		hcu_asset_chunk_view entry;
		if(!read_entry(v,middle,&entry)) return HCU_ASSET_PROFILE_E_BOUNDS;
		if(entry.type==type && entry.chunk_id==id) { *out=entry; return HCU_ASSET_PROFILE_OK; }
		if(entry.type<type || (entry.type==type && entry.chunk_id<id)) low=middle+1u;
		else high=middle;
	}
	return HCU_ASSET_PROFILE_E_FORMAT;
}

int hcu_asset_profile_read_chunk(const hcu_asset_profile_view *v,uint32_t type,uint32_t id,
	void *destination,uint32_t capacity)
{
	hcu_asset_chunk_view e; uint8_t scratch[HCP_SCRATCH],digest[32];
	sha256_context sha; uint32_t at,remaining,written=0; uint8_t copied_digest[32];
	if(!v || !destination) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(hcu_asset_profile_lookup(v,type,id,&e)!=HCU_ASSET_PROFILE_OK) return HCU_ASSET_PROFILE_E_FORMAT;
	if(capacity<e.size) return HCU_ASSET_PROFILE_E_MEMORY;
	sha256_init(&sha); at=e.offset; remaining=e.size;
	while(remaining) {
		uint32_t take=remaining<sizeof(scratch)?remaining:(uint32_t)sizeof(scratch);
		int ok;
		if(v->memory_image) { memcpy(scratch,v->memory_image+at,take); ok=1; }
		else ok=read_bytes(v->read_at,v->reader_context,at,scratch,take);
		if(!ok) return HCU_ASSET_PROFILE_E_BOUNDS;
		sha256_update(&sha,scratch,take);
		at+=take; remaining-=take;
	}
	sha256_final(&sha,digest);
	if(memcmp(digest,e.sha256,32)) return HCU_ASSET_PROFILE_E_HASH;
	/* Integrity is established before caller-visible bytes are copied. */
	at=e.offset; remaining=e.size;
	sha256_init(&sha);
	while(remaining) {
		uint32_t take=remaining<sizeof(scratch)?remaining:(uint32_t)sizeof(scratch);
		int ok;
		if(v->memory_image) { memcpy(scratch,v->memory_image+at,take); ok=1; }
		else ok=read_bytes(v->read_at,v->reader_context,at,scratch,take);
		if(!ok) return HCU_ASSET_PROFILE_E_BOUNDS;
		sha256_update(&sha,scratch,take);
		memcpy((uint8_t *)destination+written,scratch,take);
		written+=take; at+=take; remaining-=take;
	}
	sha256_final(&sha,copied_digest);
	if(memcmp(copied_digest,e.sha256,32)) {
		memset(destination,0,e.size);
		return HCU_ASSET_PROFILE_E_HASH;
	}
	return HCU_ASSET_PROFILE_OK;
}
int hcu_asset_profile_lifetime(uint32_t type,uint32_t *lifetime)
{
	if(!lifetime) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(type==HCU_ASSET_CHUNK_CE || type==HCU_ASSET_CHUNK_SOUND_META)
		*lifetime=HCU_ASSET_LIFETIME_MAP_UNLOAD;
	else if(type==HCU_ASSET_CHUNK_MEDIA) *lifetime=HCU_ASSET_LIFETIME_REQUEST;
	else return HCU_ASSET_PROFILE_E_FORMAT;
	return HCU_ASSET_PROFILE_OK;
}
int hcu_asset_profile_accounting(const hcu_asset_profile_view *v,uint32_t type,uint32_t id,uint32_t *bytes)
{
	hcu_asset_chunk_view e; uint64_t total;
	if(!v || !bytes) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(hcu_asset_profile_lookup(v,type,id,&e)!=HCU_ASSET_PROFILE_OK) return HCU_ASSET_PROFILE_E_FORMAT;
	/* The directory stays in the source. Charge the resident view once under
	 * its owner; this query reports one independently aligned decode target. */
	total=0;
	total+=((uint64_t)e.size+HCP_ALIGNMENT-1u)&~(uint64_t)(HCP_ALIGNMENT-1u);
	if(total>0xffffffffu) return HCU_ASSET_PROFILE_E_MEMORY;
	*bytes=(uint32_t)total; return HCU_ASSET_PROFILE_OK;
}
