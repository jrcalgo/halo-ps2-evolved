#include "stream/hcu_pose_asset.h"
#include "game/sword_idle.h"
#include "game/carbine_idle.h"
#include "game/hold_pose.h"
#include <stdio.h>
#include <stdlib.h>

static unsigned char *load(const char *path, size_t *n)
{
	FILE *f=fopen(path,"rb"); unsigned char *p; long z;
	if(!f || fseek(f,0,SEEK_END) || (z=ftell(f))<0 || fseek(f,0,SEEK_SET)) return NULL;
	p=(unsigned char*)malloc((size_t)z); if(!p || fread(p,1,(size_t)z,f)!=(size_t)z) return NULL;
	fclose(f); *n=(size_t)z; return p;
}
static int same(const float *a,const float *b,int n)
{ int i; for(i=0;i<n;i++) if(a[i]!=b[i]) return 0; return 1; }
static unsigned get32(const unsigned char *p)
{ return (unsigned)p[0]|((unsigned)p[1]<<8)|((unsigned)p[2]<<16)|((unsigned)p[3]<<24); }

int main(int argc,char **argv)
{
	unsigned char *s,*c,*bad; size_t sn=0,cn=0; unsigned i,f; float q[4],t[3],hq[4],mq[4],mt[3]; uint8_t over;
	if(argc!=3) return 2;
	s=load(argv[1],&sn); c=load(argv[2],&cn);
	if(!s||!c) return 3;
	if(!hcu_pose_asset_validate(s,sn)) return 31;
	if(!hcu_pose_asset_validate(c,cn)) return 32;
	if(!hcu_pose_asset_constants(s,sn,hq,mq,mt)||!same(hq,PLAY_FP_Q_SWORD,4)||!same(mq,PLAY_FP_SWORD_HANDLE_Q,4)||!same(mt,PLAY_FP_SWORD_HANDLE_T,3)) return 11;
	if(!hcu_pose_asset_constants(c,cn,hq,mq,mt)||!same(hq,PLAY_FP_Q_CARBINE,4)||!same(mq,PLAY_FP_CARBINE_GUN_Q,4)||!same(mt,PLAY_FP_CARBINE_GUN_T,3)) return 12;
	for(i=0;i<PLAY_FP_SWORD_NODES;i++) for(f=0;f<PLAY_FP_SWORD_FRAMES+3;f++) {
		if(!hcu_pose_asset_sample(s,sn,(uint16_t)i,f,q,t,&over)) return 4;
		if(!same(q,play_fp_sword_node_quat((int)i,(int)f),4)||!same(t,PLAY_FP_SWORD_NODE[i].t,3)||over!=PLAY_FP_SWORD_NODE[i].trans_override) return 5;
		if(hcu_pose_asset_find_node(s,sn,PLAY_FP_SWORD_NODE[i].name)!=(int)i) return 6;
	}
	for(i=0;i<PLAY_FP_CARBINE_NODES;i++) for(f=0;f<PLAY_FP_CARBINE_FRAMES+3;f++) {
		if(!hcu_pose_asset_sample(c,cn,(uint16_t)i,f,q,t,&over)) return 7;
		if(!same(q,play_fp_carbine_node_quat((int)i,(int)f),4)||!same(t,play_fp_carbine_node_trans((int)i,(int)f),3)||over!=PLAY_FP_CARBINE_NODE[i].trans_override) return 8;
		if(hcu_pose_asset_find_node(c,cn,PLAY_FP_CARBINE_NODE[i].name)!=(int)i) return 9;
	}
	if(hcu_pose_asset_find_node(s,sn,"not a node")!=-1) return 10;
	if(hcu_pose_asset_validate(s,sn-1)) return 13;
	bad=(unsigned char*)malloc(sn); if(!bad) return 14;
	memcpy(bad,s,sn); bad[20]^=1; if(hcu_pose_asset_validate(bad,sn)) return 15;
	memcpy(bad,s,sn); bad[24+get32(bad+16)+8]=0xff; bad[24+get32(bad+16)+9]=0xff; if(hcu_pose_asset_validate(bad,sn)) return 16;
	memcpy(bad,s,sn); memcpy(bad+24+get32(bad+16)+16,bad+24+get32(bad+16),4); if(hcu_pose_asset_validate(bad,sn)) return 25;
	memcpy(bad,s,sn); bad[24+get32(bad+16)+10]=2; bad[24+get32(bad+16)+11]=0; if(hcu_pose_asset_validate(bad,sn)) return 17;
	memcpy(bad,s,sn); bad[24+get32(bad+16)+4]=1; if(hcu_pose_asset_validate(bad,sn)) return 18;
	memcpy(bad,s,sn); memset(bad+16,0xff,4); if(hcu_pose_asset_validate(bad,sn)) return 19;
	memcpy(bad,s,sn); memset(bad+20,0xff,4); if(hcu_pose_asset_validate(bad,sn)) return 20;
	memcpy(bad,s,sn); bad[24+get32(bad+16)+4]=1; if(hcu_pose_asset_validate(bad,sn)) return 21;
	memcpy(bad,s,sn); { unsigned off=24+get32(bad+16)+37*16+(unsigned)0x0; unsigned qcount=(unsigned)bad[12]|((unsigned)bad[13]<<8); off+=qcount*16; bad[off]=0; bad[off+1]=0; bad[off+2]=0xc0; bad[off+3]=0x7f; } if(hcu_pose_asset_validate(bad,sn)) return 22;
	free(bad);
	bad=(unsigned char*)malloc(cn); if(!bad) return 23;
	memcpy(bad,c,cn); bad[24+get32(bad+16)+14]=2; bad[24+get32(bad+16)+15]=0; if(hcu_pose_asset_validate(bad,cn)) return 24;
	free(bad);
	free(s); free(c); puts("pose-payload-parity frames=sword:92x37 gravity:92x37 result=passed"); return 0;
}
