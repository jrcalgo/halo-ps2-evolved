#include "stream/hcu_asset_profile.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc,char **argv)
{
	FILE *f; long n; unsigned char *p; hcu_asset_profile_view v; hcu_asset_chunk_view c;
	int expected,rc; uint32_t accounted; unsigned char destination[256]; volatile unsigned char clobber[256]; unsigned i;
	if(argc!=3) return 90;
	f=fopen(argv[1],"rb"); if(!f) return 91;
	fseek(f,0,SEEK_END); n=ftell(f); rewind(f); p=(unsigned char *)malloc((size_t)n);
	if(!p || fread(p,1,(size_t)n,f)!=(size_t)n) return 92; fclose(f);
	expected=(int)strtoul(argv[2],NULL,0);
	rc=hcu_asset_profile_preflight(p,(size_t)n,(uint32_t)expected,&v);
	if(rc==0) {
		for(i=0;i<sizeof(clobber);i++) clobber[i]=(unsigned char)i;
		if(hcu_asset_profile_lookup(&v,HCU_ASSET_CHUNK_CE,0,&c)!=0) return 93;
		if(hcu_asset_profile_accounting(&v,HCU_ASSET_CHUNK_CE,0,&accounted)!=0 ||
			accounted!=((c.size+15u)&~15u)) return 94;
		printf("OK %u %u %u\n",v.profile_id,v.chunk_count,c.size);
		p[n-1]^=1; for(i=0;i<sizeof(destination);i++) destination[i]=0xA5;
		rc=hcu_asset_profile_read_chunk(&v,HCU_ASSET_CHUNK_SOUND_META,0,destination,sizeof(destination));
		if(rc!=HCU_ASSET_PROFILE_E_HASH || destination[0]!=0xA5) return 95;
	} else printf("ERR %d\n",rc);
	free(p); return 0;
}
