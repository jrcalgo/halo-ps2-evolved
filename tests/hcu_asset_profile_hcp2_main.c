#include "stream/hcu_asset_profile.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void put_le32(unsigned char *p, unsigned value)
{
	p[0]=(unsigned char)value; p[1]=(unsigned char)(value>>8);
	p[2]=(unsigned char)(value>>16); p[3]=(unsigned char)(value>>24);
}

typedef struct { unsigned char *image; unsigned calls, bytes, fail_on_payload_call; } counted_reader;
static int counted_read(void *context, uint32_t offset, void *destination, uint32_t size)
{
	counted_reader *r=(counted_reader *)context;
	/* This fixture's first logical chunk starts at 416 and occupies 140123 bytes. */
	if (offset < 416u+140123u && 416u < offset+size) {
		r->calls++; r->bytes += size;
		if (r->fail_on_payload_call && r->calls == r->fail_on_payload_call) return -1;
	}
	memcpy(destination,r->image+offset,size); return 0;
}

int main(int argc, char **argv)
{
	FILE *f; long n; unsigned char *p, *whole, *staged, sample[24]; hcu_asset_profile_view v;
	hcu_asset_chunk_view e; unsigned i;
	if (argc != 2) return 90;
	f=fopen(argv[1],"rb"); if(!f)return 91; fseek(f,0,SEEK_END); n=ftell(f); rewind(f);
	p=(unsigned char*)malloc((size_t)n); if(!p||fread(p,1,(size_t)n,f)!=(size_t)n)return 92; fclose(f);
	whole=(unsigned char*)malloc(140123); staged=(unsigned char*)malloc(140123); if(!whole||!staged)return 99;
	{int rc=hcu_asset_profile_preflight(p,(size_t)n,7,&v);if(rc!=HCU_ASSET_PROFILE_OK){fprintf(stderr,"preflight %d\n",rc);return 93;}}
	if(v.version!=2||v.record_bytes!=96)return 97;
	if(hcu_asset_profile_lookup(&v,HCU_ASSET_CHUNK_CE,0,&e)||e.size!=140123||e.segment_count!=3)return 94;
	if(hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123) ||
		hcu_asset_profile_read_chunk_staged(&v,HCU_ASSET_CHUNK_CE,0,staged,140123) ||
		memcmp(whole,staged,140123)) return 103;
	{
		counted_reader cr; hcu_asset_profile_view cv;
		memset(&cr,0,sizeof(cr)); cr.image=p;
		if(hcu_asset_profile_preflight_reader(counted_read,&cr,(uint32_t)n,7,&cv))return 105;
		cr.calls=cr.bytes=0;
		{hcu_asset_profile_staged_stats ps;
		 if(hcu_asset_profile_read_chunk_staged_profiled(&cv,HCU_ASSET_CHUNK_CE,0,staged,140123,&ps) ||
			cr.calls!=3 || cr.bytes!=140123u || ps.payload_read_calls!=3 || ps.payload_read_bytes!=140123u ||
			ps.read_cycles || ps.hash_cycles || ps.metadata_cycles) return 106;}
		cr.calls=cr.bytes=0; cr.fail_on_payload_call=2; memset(staged,0xA5,140123);
		if(hcu_asset_profile_read_chunk_staged(&cv,HCU_ASSET_CHUNK_CE,0,staged,140123)!=HCU_ASSET_PROFILE_E_BOUNDS ||
			staged[0] || staged[140122]) return 107;
	}
	/* Staged bytes are disposable until every hash passes. */
	p[416] ^= 1; memset(staged,0xA5,140123);
	if(hcu_asset_profile_read_chunk_staged(&v,HCU_ASSET_CHUNK_CE,0,staged,140123)!=HCU_ASSET_PROFILE_E_HASH ||
		staged[0] || staged[140122]) return 104;
	p[416] ^= 1;
	if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,65530,sample,sizeof(sample)))return 95;
	for(i=0;i<sizeof(sample);i++)if(sample[i]!=(unsigned char)((65530+i)*13u+7u))return 96;
	/* A previously validated view must remain memory safe if its directory is
	 * modified after preflight. */
	put_le32(p+32+8,0xffffffffu);
	{int a=hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123);
	 int b=hcu_asset_profile_read_chunk_staged(&v,HCU_ASSET_CHUNK_CE,0,staged,140123);
	 if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK || a==HCU_ASSET_PROFILE_OK || b!=a)return 98;}
	put_le32(p+32+8,416);
	put_le32(p+32+28,0xffffffffu);
	{int a=hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123);
	 int b=hcu_asset_profile_read_chunk_staged(&v,HCU_ASSET_CHUNK_CE,0,staged,140123);
	 if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK || a==HCU_ASSET_PROFILE_OK || b!=a)return 100;}
	put_le32(p+32+28,3);
	put_le32(p+32+12,65537);
	{int a=hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123);
	 int b=hcu_asset_profile_read_chunk_staged(&v,HCU_ASSET_CHUNK_CE,0,staged,140123);
	 if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK || a==HCU_ASSET_PROFILE_OK || b!=a)return 101;}
	free(staged); free(whole); free(p); puts("HCP2 segmented range OK"); return 0;
}
