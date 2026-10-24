#include "stream/hcu_asset_profile.h"
#include <stdio.h>
#include <stdlib.h>

static void put_le32(unsigned char *p, unsigned value)
{
	p[0]=(unsigned char)value; p[1]=(unsigned char)(value>>8);
	p[2]=(unsigned char)(value>>16); p[3]=(unsigned char)(value>>24);
}

int main(int argc, char **argv)
{
	FILE *f; long n; unsigned char *p, *whole, sample[24]; hcu_asset_profile_view v;
	hcu_asset_chunk_view e; unsigned i;
	if (argc != 2) return 90;
	f=fopen(argv[1],"rb"); if(!f)return 91; fseek(f,0,SEEK_END); n=ftell(f); rewind(f);
	p=(unsigned char*)malloc((size_t)n); if(!p||fread(p,1,(size_t)n,f)!=(size_t)n)return 92; fclose(f);
	whole=(unsigned char*)malloc(140123); if(!whole)return 99;
	{int rc=hcu_asset_profile_preflight(p,(size_t)n,7,&v);if(rc!=HCU_ASSET_PROFILE_OK){fprintf(stderr,"preflight %d\n",rc);return 93;}}
	if(v.version!=2||v.record_bytes!=96)return 97;
	if(hcu_asset_profile_lookup(&v,HCU_ASSET_CHUNK_CE,0,&e)||e.size!=140123||e.segment_count!=3)return 94;
	if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,65530,sample,sizeof(sample)))return 95;
	for(i=0;i<sizeof(sample);i++)if(sample[i]!=(unsigned char)((65530+i)*13u+7u))return 96;
	/* A previously validated view must remain memory safe if its directory is
	 * modified after preflight. */
	put_le32(p+32+8,0xffffffffu);
	if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK ||
		hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123)==HCU_ASSET_PROFILE_OK)return 98;
	put_le32(p+32+8,416);
	put_le32(p+32+28,0xffffffffu);
	if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK ||
		hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123)==HCU_ASSET_PROFILE_OK)return 100;
	put_le32(p+32+28,3);
	put_le32(p+32+12,65537);
	if(hcu_asset_profile_read_range(&v,HCU_ASSET_CHUNK_CE,0,0,sample,1)==HCU_ASSET_PROFILE_OK ||
		hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_CE,0,whole,140123)==HCU_ASSET_PROFILE_OK)return 101;
	free(whole); free(p); puts("HCP2 segmented range OK"); return 0;
}
