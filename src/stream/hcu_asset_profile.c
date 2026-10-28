#include "stream/hcu_asset_profile.h"
#include "stream/sha256.h"
#include "stream/hcu_load_trace.h"

#include <string.h>

#if (defined(_EE) || defined(_MIPS_ARCH_R5900)) && ((defined(HALO_PS2_C3_TIMING) && HALO_PS2_C3_TIMING) || \
	(defined(HALO_PS2_C3_TELEMETRY) && HALO_PS2_C3_TELEMETRY))
#include "platform/timer.h"
#define HCP_STAGED_TIMING 1
#else
#define HCP_STAGED_TIMING 0
#endif

#if HCP_STAGED_TIMING
#define HCP_TIME_BEGIN(stats, stamp) do { if (stats) (stamp) = timer_cycles(); } while (0)
#define HCP_TIME_END(stats, stamp, field) do { if (stats) (stats)->field += timer_cycles() - (stamp); } while (0)
#else
#define HCP_TIME_BEGIN(stats, stamp) do { (void)(stats); (void)(stamp); } while (0)
#define HCP_TIME_END(stats, stamp, field) do { (void)(stats); (void)(stamp); } while (0)
#endif

#define HCP_HEADER_SIZE 32u
#define HCP1_RECORD_SIZE 48u
#define HCP2_RECORD_SIZE 96u
#define HCP_ALIGNMENT 16u
#define HCP_SCRATCH 512u

static uint32_t le32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static int rd(hcu_asset_profile_read_at r, void *c,uint32_t o,void *d,uint32_t n)
{ int ok=r(c,o,d,n)==0; if(ok) HCU_LOAD_TRACE_READ_AT("asset-rd", n); return ok; }
static uint32_t row_size(const hcu_asset_profile_view *v) { return v->record_bytes; }
static int read_entry(const hcu_asset_profile_view *v,uint32_t i,hcu_asset_chunk_view *e)
{
	uint8_t b[HCP2_RECORD_SIZE]; uint32_t z,at; uint64_t dirend;
	if(!v||!e)return 0;
	z=row_size(v);
	if(i>=v->chunk_count || (v->version==1?z!=HCP1_RECORD_SIZE:(v->version==2?z!=HCP2_RECORD_SIZE:1))) return 0;
	dirend=(uint64_t)HCP_HEADER_SIZE+(uint64_t)v->chunk_count*z;
	if(dirend>v->total_bytes||dirend!=v->directory_bytes)return 0;
	at=HCP_HEADER_SIZE+i*z;
	if(v->memory_image) memcpy(b,v->memory_image+at,z);
	else if(!rd(v->read_at,v->reader_context,at,b,z)) return 0;
	e->type=le32(b); e->chunk_id=le32(b+4);
	if(v->version==1) { e->offset=le32(b+8); e->size=le32(b+12); e->first_segment=i; e->segment_count=1; memcpy(e->sha256,b+16,32); }
	else {
		uint32_t index=le32(b+24), segment_size=le32(b+12), segment_count=le32(b+28);
		if(index>i || !segment_count || segment_size>HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES)return 0;
		e->offset=le32(b+8); e->size=le32(b+20); e->first_segment=i-index; e->segment_count=segment_count; memcpy(e->sha256,b+64,32);
		if(e->first_segment>=v->chunk_count || segment_count>v->chunk_count-e->first_segment)return 0;
		if(e->offset>v->total_bytes || segment_size>v->total_bytes-e->offset)return 0;
	}
	if(!e->size)return 0;
	if(v->version==1&&(e->offset>v->total_bytes||e->size>v->total_bytes-e->offset ||
		(e->type==HCU_ASSET_CHUNK_MEDIA&&e->size>HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES)))return 0;
	return 1;
}
static int rawread(const hcu_asset_profile_view *v,uint32_t at,void *dst,uint32_t n)
{ if(!v||(!dst&&n)||at>v->total_bytes||n>v->total_bytes-at)return 0; if(v->memory_image) { memcpy(dst,v->memory_image+at,n); return 1; } return v->read_at&&rd(v->read_at,v->reader_context,at,dst,n); }
static int zeroes(const hcu_asset_profile_view *v,uint32_t at,uint32_t n)
{ uint8_t b[HCP_SCRATCH]; while(n) { uint32_t k=n<sizeof(b)?n:(uint32_t)sizeof(b),i; if(!rawread(v,at,b,k)) return 0; for(i=0;i<k;i++) if(b[i]) return 0; at+=k; n-=k; } return 1; }

/* Preflight walks the directory rows, padding and segment bytes strictly in order. Each file-bridge read is an
 * RPC, so two read-ahead windows (directory, data) replace ~3 RPCs per chunk with one per window. */
#define PF_DIR_WIN 3840u
#define PF_DATA_WIN 8192u
typedef struct {
	hcu_asset_profile_read_at reader; void *context;
	uint32_t image_size, dir_end, off[2], len[2];
	uint8_t dir[PF_DIR_WIN], data[PF_DATA_WIN];
} pf_window;
static pf_window s_pf_window;
static int pf_read(void *c, uint32_t at, void *dst, uint32_t n)
{
	pf_window *w=(pf_window *)c;
	uint32_t k=at<w->dir_end?0u:1u, cap=k?PF_DATA_WIN:PF_DIR_WIN, end=k?w->image_size:w->dir_end, fill;
	uint8_t *win=k?w->data:w->dir;
	if(n>cap||at>end||n>end-at) return w->reader(w->context,at,dst,n);
	if(!(w->len[k]&&at>=w->off[k]&&at-w->off[k]<=w->len[k]&&n<=w->len[k]-(at-w->off[k]))) {
		fill=end-at<cap?end-at:cap;
		w->len[k]=0;
		if(w->reader(w->context,at,win,fill)!=0) return -1;
		w->off[k]=at; w->len[k]=fill;
	}
	memcpy(dst,win+(at-w->off[k]),n);
	return 0;
}

/* Preflight with caller-owned read scratch of at least HCP_SCRATCH bytes. A larger
 * scratch means fewer, larger reads of the same bytes; the checks are unchanged. */
int hcu_asset_profile_preflight_reader_scratch(hcu_asset_profile_read_at reader,void *context,uint32_t image_size,uint32_t expected,hcu_asset_profile_view *view,uint8_t *buf,uint32_t buf_bytes)
{
	uint8_t h[32],row[96],dig[32],expected_logical[32]; uint32_t ver,rs,profile,count,doff,dsize,total,last_end,i,pt=0,pi=0,prev_index=0,logical_off=0,logical_size=0,seg_count=0; uint64_t expect;
	sha256_context logical_sha; int in_logical=0;
	hcu_asset_profile_read_at raw_reader=reader; void *raw_context=context;
	if(!reader||!view) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(!buf||buf_bytes<HCP_SCRATCH) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(image_size<32||!rd(reader,context,0,h,32)) return HCU_ASSET_PROFILE_E_BOUNDS;
	ver=le32(h+4); rs=ver==1?48u:ver==2?96u:0u;
	if(!rs || (ver==1?memcmp(h,"HCP1",4):memcmp(h,"HCP2",4)) || le32(h+8)!=32) return HCU_ASSET_PROFILE_E_FORMAT;
	profile=le32(h+12); count=le32(h+16); doff=le32(h+20); dsize=le32(h+24); total=le32(h+28);
	expect=(uint64_t)count*rs;
	if(!profile||!count||count>HCU_ASSET_PROFILE_MAX_CHUNKS||doff!=32||expect!=dsize||total!=image_size||dsize>total-doff) return HCU_ASSET_PROFILE_E_FORMAT;
	if(profile!=expected) return HCU_ASSET_PROFILE_E_PROFILE;
	last_end=doff+dsize;
	memset(&s_pf_window,0,sizeof(s_pf_window));
	s_pf_window.reader=raw_reader; s_pf_window.context=raw_context; s_pf_window.image_size=total; s_pf_window.dir_end=last_end;
	reader=pf_read; context=&s_pf_window;
	for(i=0;i<count;i++) {
		uint32_t type,id,off,n,lo=0,ls=0,idx=0,nseg=1,at,rem; sha256_context segsha;
		if(!rd(reader,context,doff+i*rs,row,rs)) return HCU_ASSET_PROFILE_E_BOUNDS; /* preflight-row */
		type=le32(row); id=le32(row+4); off=le32(row+8);
		if(ver==1) n=le32(row+12);
		else { n=le32(row+12); lo=le32(row+16); ls=le32(row+20); idx=le32(row+24); nseg=le32(row+28); }
		uint64_t canonical=((uint64_t)last_end+15u)&~(uint64_t)15u;
		if(!hcu_asset_chunk_id_valid(type,id)||!n||(ver==1&&type==2&&n>65536u)||
			(off&15u)||off!=canonical||off>total||n>total-off) return HCU_ASSET_PROFILE_E_BOUNDS;
		if(!zeroes(&(hcu_asset_profile_view){.read_at=reader,.reader_context=context,.total_bytes=total},last_end,off-last_end)) return HCU_ASSET_PROFILE_E_FORMAT;
		if(ver==1) {
			if(i&&(type<pt||(type==pt&&id<=pi))) return HCU_ASSET_PROFILE_E_FORMAT;
			sha256_init(&segsha); at=off; rem=n;
			while(rem) { uint32_t k=rem<buf_bytes?rem:(uint32_t)buf_bytes; if(!rd(reader,context,at,buf,k)) return HCU_ASSET_PROFILE_E_BOUNDS; sha256_update(&segsha,buf,k); at+=k; rem-=k; }
			sha256_final(&segsha,dig); HCU_LOAD_TRACE_HASH("hcp1",n); if(memcmp(dig,row+16,32)) return HCU_ASSET_PROFILE_E_HASH;
		} else {
			if(!ls||!nseg||nseg>count||idx>=nseg||n>65536u||lo>ls||n>ls-lo) return HCU_ASSET_PROFILE_E_FORMAT;
			if(!i || type!=pt || id!=pi) {
				if(in_logical && (prev_index+1!=seg_count || logical_off!=logical_size)) return HCU_ASSET_PROFILE_E_FORMAT;
				if(i&&(type<pt||(type==pt&&id<=pi))) return HCU_ASSET_PROFILE_E_FORMAT;
				if(idx!=0||lo!=0) return HCU_ASSET_PROFILE_E_FORMAT;
				logical_size=ls; logical_off=0; seg_count=nseg; prev_index=0; in_logical=1; memcpy(expected_logical,row+64,32); sha256_init(&logical_sha);
			} else if(idx!=prev_index+1||lo!=logical_off||ls!=logical_size||nseg!=seg_count||memcmp(expected_logical,row+64,32)) return HCU_ASSET_PROFILE_E_FORMAT;
			sha256_init(&segsha); at=off; rem=n;
			while(rem) { uint32_t k=rem<buf_bytes?rem:(uint32_t)buf_bytes; if(!rd(reader,context,at,buf,k)) return HCU_ASSET_PROFILE_E_BOUNDS; sha256_update(&segsha,buf,k); sha256_update(&logical_sha,buf,k); at+=k; rem-=k; }
			sha256_final(&segsha,dig); HCU_LOAD_TRACE_HASH("segment",n); if(memcmp(dig,row+32,32)) return HCU_ASSET_PROFILE_E_HASH;
			logical_off+=n; prev_index=idx;
			if(idx+1==nseg) { sha256_final(&logical_sha,dig); HCU_LOAD_TRACE_HASH("logical",logical_size); if(logical_off!=logical_size||memcmp(dig,row+64,32)) return HCU_ASSET_PROFILE_E_HASH; in_logical=0; }
		}
		last_end=off+n; pt=type; pi=id;
	}
	if(in_logical||last_end!=total) return HCU_ASSET_PROFILE_E_FORMAT;
	{
		hcu_asset_profile_view v; hcu_asset_chunk_view e;
		memset(&v,0,sizeof(v)); v.profile_id=profile; v.total_bytes=total; v.chunk_count=count; v.directory_bytes=doff+dsize; v.version=ver; v.record_bytes=rs; v.read_at=raw_reader; v.reader_context=raw_context;
		if(hcu_asset_profile_lookup(&v,1,0,&e)||hcu_asset_profile_lookup(&v,3,0,&e)) return HCU_ASSET_PROFILE_E_FORMAT;
		*view=v;
	}
	return HCU_ASSET_PROFILE_OK;
}
int hcu_asset_profile_preflight_reader(hcu_asset_profile_read_at reader,void *context,uint32_t image_size,uint32_t expected,hcu_asset_profile_view *view)
{
	uint8_t buf[HCP_SCRATCH];
	return hcu_asset_profile_preflight_reader_scratch(reader,context,image_size,expected,view,buf,(uint32_t)sizeof(buf));
}
typedef struct { const uint8_t *p; size_t n; } memr;
static int memread(void *c,uint32_t o,void *d,uint32_t n) { memr*m=c; if(o>m->n||n>m->n-o)return -1; memcpy(d,m->p+o,n);return 0; }
int hcu_asset_profile_preflight(const void *p,size_t n,uint32_t id,hcu_asset_profile_view *v)
{ memr m; hcu_asset_profile_view t; int r; if(!p||n>0xffffffffu)return HCU_ASSET_PROFILE_E_ARGUMENT; m.p=p;m.n=n;r=hcu_asset_profile_preflight_reader(memread,&m,(uint32_t)n,id,&t);if(r)return r;t.memory_image=p;t.read_at=0;t.reader_context=0;*v=t;return 0; }

int hcu_asset_profile_lookup(const hcu_asset_profile_view *v,uint32_t type,uint32_t id,hcu_asset_chunk_view *out)
{
	uint32_t lo=0,hi; if(!v||!out)return HCU_ASSET_PROFILE_E_ARGUMENT; hi=v->chunk_count;
	while(lo<hi) { uint32_t m=lo+(hi-lo)/2; hcu_asset_chunk_view e; if(!read_entry(v,m,&e))return HCU_ASSET_PROFILE_E_BOUNDS;
		if(e.type==type&&e.chunk_id==id) {
			if(v->version==2) { uint32_t first=e.first_segment; hcu_asset_chunk_view start;
				if(first>m||!read_entry(v,first,&start)||start.type!=type||start.chunk_id!=id||start.first_segment!=first)return HCU_ASSET_PROFILE_E_BOUNDS;
				e=start;
			}
			*out=e;return 0; }
		if(e.type<type||(e.type==type&&e.chunk_id<id))lo=m+1;else hi=m;
	} return HCU_ASSET_PROFILE_E_FORMAT;
}
static int read_range_unchecked(const hcu_asset_profile_view*v,const hcu_asset_chunk_view*e,uint32_t offset,uint8_t*dst,uint32_t size)
{
	uint32_t first=e->first_segment,count=e->segment_count,end=offset+size,lo=0,hi=count,done=0,i;
	if(first>v->chunk_count||count>v->chunk_count-first||!count)return 0;
	/* HCP2 logical offsets are contiguous and sorted, so locate the first
	 * intersecting segment in logarithmic time before reading the requested span. */
	if(v->version==2) while(lo<hi) { uint32_t mid=lo+(hi-lo)/2u,row=first+mid,base,n;uint8_t b[96];
		uint32_t ra=HCP_HEADER_SIZE+row*v->record_bytes;
		if(v->memory_image)memcpy(b,v->memory_image+ra,v->record_bytes);else if(!rd(v->read_at,v->reader_context,ra,b,v->record_bytes))return 0;
		if(le32(b)!=e->type||le32(b+4)!=e->chunk_id||le32(b+24)!=mid||le32(b+28)!=count||le32(b+20)!=e->size)return 0;
		base=le32(b+16);n=le32(b+12);
		if(!n||n>HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES||base>e->size||n>e->size-base)return 0;
		if(base+n<=offset)lo=mid+1;else hi=mid;
	}
	for(i=lo;i<count&&done<size;i++) { uint8_t b[96];uint32_t row=first+i,off,n,base=0,seglo,take,ra;
		ra=HCP_HEADER_SIZE+row*v->record_bytes;
		if(v->memory_image)memcpy(b,v->memory_image+ra,v->record_bytes);else if(!rd(v->read_at,v->reader_context,ra,b,v->record_bytes))return 0;
		if(le32(b)!=e->type||le32(b+4)!=e->chunk_id)return 0;
		off=le32(b+8);n=v->version==1?le32(b+12):le32(b+12);
		if(v->version==2){base=le32(b+16);if(!n||n>HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES||le32(b+24)!=i||le32(b+28)!=count||le32(b+20)!=e->size||base>e->size||n>e->size-base)return 0;}
		if(end<=base)break;
		if(offset>=base+n)continue;
		seglo=offset>base?offset:base;{uint32_t segend=end<base+n?end:base+n;take=segend-seglo;}
		if(off>v->total_bytes||n>v->total_bytes-off||take>n-(seglo-base))return 0;
		if(v->memory_image)memcpy(dst+done,v->memory_image+off+(seglo-base),take);else if(!rd(v->read_at,v->reader_context,off+(seglo-base),dst+done,take))return 0;
		done+=take;
	}
	return done==size;
}
int hcu_asset_profile_read_range(const hcu_asset_profile_view*v,uint32_t type,uint32_t id,uint32_t off,void*dst,uint32_t n)
{ hcu_asset_chunk_view e; if(!v||(!dst&&n))return HCU_ASSET_PROFILE_E_ARGUMENT; if(hcu_asset_profile_lookup(v,type,id,&e))return HCU_ASSET_PROFILE_E_FORMAT; if(off>e.size||n>e.size-off)return HCU_ASSET_PROFILE_E_BOUNDS; return read_range_unchecked(v,&e,off,(uint8_t*)dst,n)?0:HCU_ASSET_PROFILE_E_BOUNDS; }
/* Reload one directory record using bounds derived from the preflighted view,
 * then prove it still belongs to this logical chunk before trusting its extent. */
static int read_segment_record(const hcu_asset_profile_view *v,
	const hcu_asset_chunk_view *e, uint32_t relative_index, uint8_t row[HCP2_RECORD_SIZE])
{
	uint32_t physical_index, row_at, offset, segment_size, logical_size, logical_offset;
	if(!v || !e || v->version!=2 || v->record_bytes!=HCP2_RECORD_SIZE ||
		e->first_segment>=v->chunk_count || !e->segment_count ||
		e->segment_count>v->chunk_count-e->first_segment || relative_index>=e->segment_count)
		return 0;
	physical_index=e->first_segment+relative_index;
	row_at=HCP_HEADER_SIZE+physical_index*HCP2_RECORD_SIZE;
	if(row_at>v->directory_bytes || HCP2_RECORD_SIZE>v->directory_bytes-row_at ||
		row_at>v->total_bytes || HCP2_RECORD_SIZE>v->total_bytes-row_at)
		return 0;
	if(!rawread(v,row_at,row,HCP2_RECORD_SIZE))return 0;
	offset=le32(row+8); segment_size=le32(row+12); logical_offset=le32(row+16);
	logical_size=le32(row+20);
	if(le32(row)!=e->type || le32(row+4)!=e->chunk_id ||
		le32(row+24)!=relative_index || le32(row+28)!=e->segment_count ||
		logical_size!=e->size || memcmp(row+64,e->sha256,32) ||
		!segment_size || segment_size>HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES ||
		logical_offset>logical_size || segment_size>logical_size-logical_offset ||
		offset>v->total_bytes || segment_size>v->total_bytes-offset)
		return 0;
	return 1;
}

int hcu_asset_profile_read_chunk(const hcu_asset_profile_view*v,uint32_t type,uint32_t id,void*dst,uint32_t cap)
{
	hcu_asset_chunk_view e;uint8_t b[HCP_SCRATCH],dig[32],row[HCP2_RECORD_SIZE];sha256_context s;uint32_t at=0,seg=0,segment_at=0;sha256_context segment_sha;
	if(!v||!dst)return HCU_ASSET_PROFILE_E_ARGUMENT;
	if(hcu_asset_profile_lookup(v,type,id,&e))return HCU_ASSET_PROFILE_E_FORMAT;
	if(v->version==1&&type==2&&e.size>65536u)return HCU_ASSET_PROFILE_E_BOUNDS;
	if(cap<e.size)return HCU_ASSET_PROFILE_E_MEMORY;
	/* Validate before touching dst: callers rely on a hash failure leaving
	 * their previous contents intact. Combine segment and logical checks in one
	 * pass, then reread only for the copy. */
	sha256_init(&s);
	if(v->version==2) {
		if(!read_segment_record(v,&e,0,row)||le32(row+16)!=0)return HCU_ASSET_PROFILE_E_BOUNDS;
		HCU_LOAD_TRACE_READ_AT("segment-row", HCP2_RECORD_SIZE);
		sha256_init(&segment_sha);
	}
	while(at<e.size) {
		uint32_t k=e.size-at<sizeof(b)?e.size-at:(uint32_t)sizeof(b);
		if(v->version==2) {
			uint32_t left=le32(row+12)-segment_at;
			if(k>left)k=left;
		}
		if(!read_range_unchecked(v,&e,at,b,k)) return HCU_ASSET_PROFILE_E_BOUNDS;
		sha256_update(&s,b,k);
		if(v->version==2)sha256_update(&segment_sha,b,k);
		at+=k;
		if(v->version==2) {
			segment_at+=k;
			if(segment_at==le32(row+12)) {
				sha256_final(&segment_sha,dig);
				if(memcmp(dig,row+32,32)) return HCU_ASSET_PROFILE_E_HASH;
				seg++;
				segment_at=0;
				if(seg<e.segment_count) {
					if(!read_segment_record(v,&e,seg,row)||le32(row+16)!=at) return HCU_ASSET_PROFILE_E_BOUNDS;
					HCU_LOAD_TRACE_READ_AT("segment-row", HCP2_RECORD_SIZE);
					sha256_init(&segment_sha);
				}
			}
		}
	}
	sha256_final(&s,dig);
	if(memcmp(dig,e.sha256,32)||(v->version==2&&(seg!=e.segment_count||segment_at!=0))) return HCU_ASSET_PROFILE_E_HASH;
	at=0;
	sha256_init(&s);
	while(at<e.size) {
		uint32_t k=e.size-at<sizeof(b)?e.size-at:(uint32_t)sizeof(b);
		if(!read_range_unchecked(v,&e,at,b,k)) { memset(dst,0,e.size); return HCU_ASSET_PROFILE_E_BOUNDS; }
		sha256_update(&s,b,k);
		memcpy((uint8_t*)dst+at,b,k);
		at+=k;
	}
	sha256_final(&s,dig);
	if(memcmp(dig,e.sha256,32)) { memset(dst,0,e.size); return HCU_ASSET_PROFILE_E_HASH; }
	return HCU_ASSET_PROFILE_OK;
}

/* Disposable-destination variant for cold loads. It resolves each segment row
 * once, then reads that segment directly into its final staging position.
 * Hashes are computed over exactly those bytes, so no second payload pass is
 * needed and a mutable backing source cannot publish unchecked data. */
int hcu_asset_profile_read_chunk_staged_profiled(const hcu_asset_profile_view *v,
	uint32_t type, uint32_t id, void *dst, uint32_t cap,
	hcu_asset_profile_staged_stats *stats)
{
	hcu_asset_chunk_view e;
	uint8_t row[HCP2_RECORD_SIZE], digest[32];
	sha256_context logical_sha;
	uint32_t seg, logical_at = 0;
	uint32_t stamp = 0;
	int rc = HCU_ASSET_PROFILE_E_BOUNDS;
	if (stats) memset(stats, 0, sizeof(*stats));
	if (!v || !dst) return HCU_ASSET_PROFILE_E_ARGUMENT;
	HCP_TIME_BEGIN(stats, stamp);
	if (hcu_asset_profile_lookup(v, type, id, &e)) { HCP_TIME_END(stats, stamp, metadata_cycles); return HCU_ASSET_PROFILE_E_FORMAT; }
	HCP_TIME_END(stats, stamp, metadata_cycles);
	if (v->version == 1 && type == HCU_ASSET_CHUNK_MEDIA &&
		e.size > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) return HCU_ASSET_PROFILE_E_BOUNDS;
	if (cap < e.size) return HCU_ASSET_PROFILE_E_MEMORY;
	sha256_init(&logical_sha);
	if (v->version == 1) {
		uint32_t at = 0;
		if (e.offset > v->total_bytes || e.size > v->total_bytes - e.offset) goto fail;
		while (at < e.size) {
			uint32_t n = e.size - at;
			if (n > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) n = HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
			if (stats) { stats->payload_read_calls++; stats->payload_read_bytes += n; }
			HCP_TIME_BEGIN(stats, stamp);
			if (!rawread(v, e.offset + at, (uint8_t *)dst + at, n)) { HCP_TIME_END(stats, stamp, read_cycles); goto fail; }
			HCP_TIME_END(stats, stamp, read_cycles);
			HCP_TIME_BEGIN(stats, stamp); sha256_update(&logical_sha, (uint8_t *)dst + at, n); HCP_TIME_END(stats, stamp, hash_cycles);
			at += n;
		}
	} else if (v->version == 2) {
		if (!e.segment_count || e.segment_count > v->chunk_count - e.first_segment) goto fail;
		for (seg = 0; seg < e.segment_count; ++seg) {
			sha256_context segment_sha;
			uint32_t offset, bytes, logical_offset, at = 0;
			HCP_TIME_BEGIN(stats, stamp);
			if (!read_segment_record(v, &e, seg, row)) { HCP_TIME_END(stats, stamp, metadata_cycles); goto fail; }
			HCP_TIME_END(stats, stamp, metadata_cycles);
			HCU_LOAD_TRACE_READ_AT("segment-row", HCP2_RECORD_SIZE);
			offset = le32(row + 8); bytes = le32(row + 12); logical_offset = le32(row + 16);
			if (logical_offset != logical_at || !bytes || bytes > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES ||
				logical_at > e.size || bytes > e.size - logical_at) goto fail;
			sha256_init(&segment_sha);
			while (at < bytes) {
				uint32_t n = bytes - at;
				if (n > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) n = HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
				if (stats) { stats->payload_read_calls++; stats->payload_read_bytes += n; }
				HCP_TIME_BEGIN(stats, stamp);
				if (!rawread(v, offset + at, (uint8_t *)dst + logical_at + at, n)) { HCP_TIME_END(stats, stamp, read_cycles); goto fail; }
				HCP_TIME_END(stats, stamp, read_cycles);
				HCP_TIME_BEGIN(stats, stamp);
				sha256_update(&segment_sha, (uint8_t *)dst + logical_at + at, n);
				sha256_update(&logical_sha, (uint8_t *)dst + logical_at + at, n);
				HCP_TIME_END(stats, stamp, hash_cycles);
				at += n;
			}
			HCP_TIME_BEGIN(stats, stamp); sha256_final(&segment_sha, digest); HCP_TIME_END(stats, stamp, hash_cycles);
			if (memcmp(digest, row + 32, 32)) { rc = HCU_ASSET_PROFILE_E_HASH; goto fail; }
			logical_at += bytes;
		}
		if (logical_at != e.size) goto fail;
	} else { rc = HCU_ASSET_PROFILE_E_FORMAT; goto fail; }
	HCP_TIME_BEGIN(stats, stamp); sha256_final(&logical_sha, digest); HCP_TIME_END(stats, stamp, hash_cycles);
	if (memcmp(digest, e.sha256, 32)) { rc = HCU_ASSET_PROFILE_E_HASH; goto fail; }
	return HCU_ASSET_PROFILE_OK;
fail:
	memset(dst, 0, e.size);
	return rc;
}
int hcu_asset_profile_read_chunk_staged(const hcu_asset_profile_view *v,
	uint32_t type, uint32_t id, void *dst, uint32_t cap)
{ return hcu_asset_profile_read_chunk_staged_profiled(v, type, id, dst, cap, 0); }
static const hcu_asset_chunk_kind chunk_kinds[] = {
	{HCU_ASSET_CHUNK_CE, "CE", HCU_ASSET_LIFETIME_MAP_UNLOAD, 0},
	{HCU_ASSET_CHUNK_MEDIA, "MEDIA", HCU_ASSET_LIFETIME_REQUEST, 1},
	{HCU_ASSET_CHUNK_SOUND_META, "SOUND_META", HCU_ASSET_LIFETIME_MAP_UNLOAD, 0},
	{HCU_ASSET_CHUNK_BSPS, "BSPS", HCU_ASSET_LIFETIME_MAP_UNLOAD, 1},
	{HCU_ASSET_CHUNK_TEXS, "TEXS", HCU_ASSET_LIFETIME_MAP_UNLOAD, 1},
	{HCU_ASSET_CHUNK_LIGHTMAP, "LMn", HCU_ASSET_LIFETIME_MAP_UNLOAD, 1}};
int hcu_asset_chunk_kind_lookup(uint32_t type,hcu_asset_chunk_kind*kind)
{ uint32_t i; if(!kind)return HCU_ASSET_PROFILE_E_ARGUMENT; for(i=0;i<sizeof chunk_kinds/sizeof chunk_kinds[0];i++) if(chunk_kinds[i].type==type){*kind=chunk_kinds[i];return HCU_ASSET_PROFILE_OK;} return HCU_ASSET_PROFILE_E_FORMAT; }
int hcu_asset_chunk_id_valid(uint32_t type,uint32_t id)
{ hcu_asset_chunk_kind k; return hcu_asset_chunk_kind_lookup(type,&k)==HCU_ASSET_PROFILE_OK && (k.keyed||id==0); }
int hcu_asset_profile_lifetime(uint32_t t,uint32_t*l){hcu_asset_chunk_kind k;if(!l)return -1;if(hcu_asset_chunk_kind_lookup(t,&k)!=HCU_ASSET_PROFILE_OK)return -3;*l=k.lifetime;return 0;}
int hcu_asset_profile_accounting(const hcu_asset_profile_view*v,uint32_t t,uint32_t id,uint32_t*b)
{hcu_asset_chunk_view e;uint64_t n;if(!v||!b)return -1;if(hcu_asset_profile_lookup(v,t,id,&e))return -3;n=((uint64_t)e.size+15)&~(uint64_t)15;if(n>0xffffffffu)return -6;*b=(uint32_t)n;return 0;}

/* Residency: a fixed table of resident segments with independent CE pins, DMA/GS
 * leases and gameplay references. Every transition is checked before mutation. */
static hcu_asset_residency_entry *residency_find(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg)
{
	uint32_t i;
	for (i = 0; i < t->count; i++)
		if (t->entries[i].type == type && t->entries[i].chunk_id == id && t->entries[i].segment == seg) return &t->entries[i];
	return 0;
}
static const hcu_asset_residency_entry *residency_find_const(const hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg)
{ return residency_find((hcu_asset_residency *)t, type, id, seg); }

int hcu_asset_profile_segment_info(const hcu_asset_profile_view *v, uint32_t type, uint32_t id,
	uint32_t seg, uint32_t *bytes, uint32_t *logical_offset)
{
	hcu_asset_chunk_view e; uint8_t row[HCP2_RECORD_SIZE];
	if (!v || !bytes || !logical_offset) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if (v->version != 2) return HCU_ASSET_PROFILE_E_PROFILE;
	if (hcu_asset_profile_lookup(v, type, id, &e)) return HCU_ASSET_PROFILE_E_FORMAT;
	if (!read_segment_record(v, &e, seg, row)) return HCU_ASSET_PROFILE_E_BOUNDS;
	*bytes = le32(row+12); *logical_offset = le32(row+16);
	return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_profile_read_segment(const hcu_asset_profile_view *v, uint32_t type, uint32_t id,
	uint32_t seg, void *dst, uint32_t capacity)
{
	hcu_asset_chunk_view e; uint8_t row[HCP2_RECORD_SIZE], digest[32]; sha256_context sha;
	uint32_t offset, size;
	if (!v || !dst) return HCU_ASSET_PROFILE_E_ARGUMENT;
	if (v->version != 2) return HCU_ASSET_PROFILE_E_PROFILE;
	if (hcu_asset_profile_lookup(v, type, id, &e)) return HCU_ASSET_PROFILE_E_FORMAT;
	if (!read_segment_record(v, &e, seg, row)) return HCU_ASSET_PROFILE_E_BOUNDS;
	offset = le32(row+8); size = le32(row+12);
	if (size > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) return HCU_ASSET_PROFILE_E_BOUNDS;
	if (capacity < size) return HCU_ASSET_PROFILE_E_MEMORY;
	if (!rawread(v, offset, dst, size)) return HCU_ASSET_PROFILE_E_BOUNDS;
	sha256_init(&sha); sha256_update(&sha, dst, size); sha256_final(&sha, digest);
	if (memcmp(digest, row+32, 32)) { memset(dst, 0, size); return HCU_ASSET_PROFILE_E_HASH; }
	return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_init(hcu_asset_residency *t, hcu_asset_residency_entry *entries, uint32_t capacity)
{
	if (!t || (!entries && capacity)) return HCU_ASSET_PROFILE_E_ARGUMENT;
	memset(t, 0, sizeof(*t));
	t->entries = entries; t->capacity = capacity;
	if (entries && capacity) memset(entries, 0, sizeof(*entries) * capacity);
	return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_pin(hcu_asset_residency *t, const hcu_asset_profile_view *v,
	uint32_t type, uint32_t id, uint32_t seg, void *storage, uint32_t capacity)
{
	hcu_asset_residency_entry *e; int rc, created = 0; uint32_t bytes, logical;
	if (!t || !v) return HCU_ASSET_PROFILE_E_ARGUMENT;
	e = residency_find(t, type, id, seg);
	if (e && e->resident) {
		if (e->pin_count == UINT32_MAX) return HCU_ASSET_PROFILE_E_STATE;
		e->pin_count++; return HCU_ASSET_PROFILE_OK;
	}
	rc = hcu_asset_profile_segment_info(v, type, id, seg, &bytes, &logical);
	if (rc) return rc;
	if (!storage || capacity < bytes) return HCU_ASSET_PROFILE_E_MEMORY;
	if (t->resident_bytes > UINT32_MAX - bytes) return HCU_ASSET_PROFILE_E_MEMORY;
	if (!e) {
		uint32_t i;
		/* An evicted entry with no reader is free; reuse it before growing. */
		for (i = 0; i < t->count && !e; ++i)
			if (!t->entries[i].resident && !t->entries[i].pin_count &&
				!t->entries[i].lease_count && !t->entries[i].gameplay_refs)
				e = &t->entries[i];
		if (!e) {
			if (t->count >= t->capacity) { t->refused_pins++; return HCU_ASSET_PROFILE_E_MEMORY; }
			e = &t->entries[t->count++];
			created = 1;
		}
		memset(e, 0, sizeof(*e));
		e->type = type; e->chunk_id = id; e->segment = seg;
	}
	rc = hcu_asset_profile_read_segment(v, type, id, seg, storage, capacity);
	if (rc) { t->verify_failures++; if (created) t->count--; return rc; }
	e->bytes = bytes; e->storage = storage; e->resident = 1; e->pin_count = 1;
	t->resident_bytes += bytes;
	if (t->resident_bytes > t->resident_high_water) t->resident_high_water = t->resident_bytes;
	return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_unpin(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg)
{
	hcu_asset_residency_entry *e = t ? residency_find(t, type, id, seg) : 0;
	if (!e || !e->resident || !e->pin_count) return HCU_ASSET_PROFILE_E_STATE;
	e->pin_count--; return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_lease(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg)
{
	hcu_asset_residency_entry *e = t ? residency_find(t, type, id, seg) : 0;
	if (!e || !e->resident) return HCU_ASSET_PROFILE_E_STATE;
	if (e->lease_count == UINT32_MAX) return HCU_ASSET_PROFILE_E_STATE;
	e->lease_count++; return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_release_lease(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg)
{
	hcu_asset_residency_entry *e = t ? residency_find(t, type, id, seg) : 0;
	if (!e || !e->lease_count) return HCU_ASSET_PROFILE_E_STATE;
	e->lease_count--; return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_gameplay_ref(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg, int delta)
{
	hcu_asset_residency_entry *e = t ? residency_find(t, type, id, seg) : 0;
	if (!e || !e->resident) return HCU_ASSET_PROFILE_E_STATE;
	if (delta > 0) { if (e->gameplay_refs == UINT32_MAX) return HCU_ASSET_PROFILE_E_STATE; e->gameplay_refs++; return HCU_ASSET_PROFILE_OK; }
	if (delta < 0) { if (!e->gameplay_refs) return HCU_ASSET_PROFILE_E_STATE; e->gameplay_refs--; return HCU_ASSET_PROFILE_OK; }
	return HCU_ASSET_PROFILE_E_ARGUMENT;
}

int hcu_asset_residency_evict(hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg, void **storage_out)
{
	hcu_asset_residency_entry *e = t ? residency_find(t, type, id, seg) : 0;
	if (!e || !e->resident) return HCU_ASSET_PROFILE_E_STATE;
	if (e->pin_count || e->lease_count || e->gameplay_refs) { t->refused_evictions++; return HCU_ASSET_PROFILE_E_BUSY; }
	if (storage_out) *storage_out = e->storage;
	t->resident_bytes -= e->bytes;
	e->resident = 0; e->bytes = 0; e->storage = 0;
	t->evictions++;
	return HCU_ASSET_PROFILE_OK;
}

int hcu_asset_residency_state(const hcu_asset_residency *t, uint32_t type, uint32_t id, uint32_t seg,
	const hcu_asset_residency_entry **entry)
{
	const hcu_asset_residency_entry *e;
	if (!t || !entry) return HCU_ASSET_PROFILE_E_ARGUMENT;
	e = residency_find_const(t, type, id, seg);
	if (!e) return HCU_ASSET_PROFILE_E_STATE;
	*entry = e; return HCU_ASSET_PROFILE_OK;
}
