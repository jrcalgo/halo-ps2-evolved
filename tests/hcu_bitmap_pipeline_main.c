#include "cseries.h"
#include "bitmaps/bitmap_group.h"
#include "interface/interface.h"
#include "rasterizer/rasterizer.h"
#include "halo_ps2_bitmap_requests.h"
#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#undef malloc
#undef free
#undef strcmp

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

typedef char fixture_ilp32[sizeof(void *)==4&&sizeof(long)==4?1:-1];
static struct bitmap_group s_group;
static struct bitmap_data s_bitmap;
static uint32_t s_tag_datum = 5;

void *csmemset(void *p,long value,unsigned long size)
{
	unsigned long i; byte *b=(byte*)p; for(i=0;i<size;i++) b[i]=(byte)value; return p;
}
void *tag_block_get_element_with_size(struct tag_block const *block,long index,long size)
{
	if(!block||index<0||index>=block->count||!block->address||size<=0) return NULL;
	return (byte*)block->address+index*size;
}
void *tag_get(long group_tag,long tag_index)
{
	return group_tag==BITMAP_GROUP_TAG&&(uint32_t)tag_index==s_tag_datum?&s_group:NULL;
}

static unsigned log2_exact_u(unsigned v)
{
	unsigned n=0; if(!v||(v&(v-1u))) return 99u; while(v>1u){v>>=1;n++;}return n;
}

static int load_file(const char *path,uint8_t **out,size_t *size)
{
	FILE *f=fopen(path,"rb"); long n;
	if(!f) return 0; if(fseek(f,0,SEEK_END)||((n=ftell(f))<0)||fseek(f,0,SEEK_SET)){fclose(f);return 0;}
	*out=(uint8_t*)malloc((size_t)n); if(!*out){fclose(f);return 0;}
	if(fread(*out,1,(size_t)n,f)!=(size_t)n){free(*out);fclose(f);return 0;}
	fclose(f);*size=(size_t)n;return 1;
}

int main(int argc,char **argv)
{
	halo_ps2_bitmap_request_queue queue; halo_ps2_bitmap_request_reader reader={0};
	point2d point; real_rectangle2d clip; tex_section textures; tex_info image;
	uint8_t *asset=NULL,*chain_mem=NULL; size_t asset_size=0; chain_t chain;
	hcu_bitmap_quad_state_t state; hcu_bitmap_vertex_t vertices[4];
	uint32_t i; int full=argc>2&&strcmp(argv[2],"full")==0;
	int bad=argc>2&&strcmp(argv[2],"bad_asset")==0;
	const char *interface_sha=argc>3?argv[3]:"missing";
	uint32_t datum=argc>4?(uint32_t)strtoul(argv[4],NULL,0):5u;
	uint32_t image_index=argc>5?(uint32_t)strtoul(argv[5],NULL,0):0u;
	unsigned source_w=argc>6?(unsigned)strtoul(argv[6],NULL,0):8u;
	unsigned source_h=argc>7?(unsigned)strtoul(argv[7],NULL,0):8u;
	short registration_x=argc>8?(short)strtol(argv[8],NULL,0):4;
	short registration_y=argc>9?(short)strtol(argv[9],NULL,0):4;
	if(argc<2||!load_file(argv[1],&asset,&asset_size)) return 2;
	s_tag_datum=datum;
	memset(&s_group,0,sizeof s_group); memset(&s_bitmap,0,sizeof s_bitmap);
	s_group.bitmaps.count=1; s_group.bitmaps.address=&s_bitmap;
	s_bitmap.width=(short)source_w; s_bitmap.height=(short)source_h; s_bitmap.tag_index=(long)(int32_t)datum;
	s_bitmap.registration_point.x=(real)registration_x; s_bitmap.registration_point.y=(real)registration_y;
	memset(&queue,0,sizeof queue); halo_ps2_bitmap_requests_init(&queue);
	if(halo_ps2_bitmap_requests_begin(&queue,71,9001,0,0)!=HALO_PS2_BITMAP_REQUEST_OK) return 3;
	point.x=320;point.y=224;clip.x0=0.125f;clip.x1=0.875f;clip.y0=0.125f;clip.y1=0.875f;
	if(full){for(i=0;i<HALO_PS2_BITMAP_REQUEST_CAPACITY+1u;i++) interface_draw_bitmap(&s_bitmap,&point,&clip,2.0f,0.4f,0.5f);}
	else interface_draw_bitmap(&s_bitmap,&point,&clip,2.0f,0.4f,0.5f);
	if(full){if(queue.count!=HALO_PS2_BITMAP_REQUEST_CAPACITY||queue.full_count!=1) return 4;}
	else if(queue.count!=1) return 5;
	halo_ps2_bitmap_requests_end(&queue);
	if(halo_ps2_bitmap_requests_acquire(&queue,9001,&reader)!=HALO_PS2_BITMAP_REQUEST_OK) return 6;
	if(full){
		chain_mem=(uint8_t*)malloc(64*16); if(!chain_mem)return 7; memset(chain_mem,0xA5,64*16); chain_init(&chain,chain_mem,64);
		if(chain_qwords(&chain)!=0) return 8;
		printf("pipeline-full captured=%u full=%u emitted=%u interface_sha256=%s\n",reader.count,queue.full_count,chain_qwords(&chain),interface_sha);
		return 0;
	}
	if(reader.count!=1||(uint32_t)reader.requests[0].bitmap_tag_index!=datum||reader.requests[0].bitmap_index!=0||image_index!=0) return 9;
	/* interface.c's translation-unit enum places alpha_multiply_add at slot 7. */
	if(reader.requests[0].framebuffer_blend_function!=7) return 10;
	if(reader.requests[0].alpha_weighted) return 17;
	if(reader.requests[0].vertices[0].x==reader.requests[0].vertices[1].x||
	   reader.requests[0].vertices[0].y==reader.requests[0].vertices[1].y) return 11;
	{
		static const float uv[4][2]={{0.125f,0.125f},{0.875f,0.125f},{0.875f,0.875f},{0.125f,0.875f}};
		float cs=cosf(0.4f), sn=sinf(0.4f);
		for(i=0;i<4;i++){
			float lx=((float)source_w*uv[i][0]-(float)registration_x)*2.0f;
			float ly=((float)source_h*uv[i][1]-(float)registration_y)*2.0f;
			float ex=320.0f+lx*cs-ly*sn, ey=224.0f+lx*sn+ly*cs;
			if(fabsf(reader.requests[0].vertices[i].x-ex)>0.01f||
			   fabsf(reader.requests[0].vertices[i].y-ey)>0.01f||
			   reader.requests[0].vertices[i].u!=uv[i][0]||reader.requests[0].vertices[i].v!=uv[i][1]||
			   reader.requests[0].vertices[i].color!=0x7FFFFFFFu) return 26;
		}
	}
	if(bad){asset[0]='X';if(tex_open(&textures,asset,asset_size)==TEX_OK)return 12;
		printf("pipeline-bad-asset capture=%u emitted=0 rejected=1 interface_sha256=%s\n",reader.count,interface_sha);return 0;}
	if(tex_open(&textures,asset,asset_size)!=TEX_OK) return 13;
	image=tex_get(&textures,0); if(image.source_id!=(uint32_t)reader.requests[0].bitmap_tag_index) return 14;
	for(i=0;i<4;i++){
		vertices[i].x=reader.requests[0].vertices[i].x; vertices[i].y=reader.requests[0].vertices[i].y;
		vertices[i].u=reader.requests[0].vertices[i].u; vertices[i].v=reader.requests[0].vertices[i].v;
		vertices[i].argb=reader.requests[0].vertices[i].color;
	}
	if(log2_exact_u(image.width)>15u||log2_exact_u(image.height)>15u) return 25;
	memset(&state,0,sizeof state); state.tex0=GS_TEX0(10,(image.width+63u)/64u,image.psm,
		log2_exact_u(image.width),log2_exact_u(image.height),1,0,30,GS_PSMCT32,0,0,1);
	state.screen_w=640;state.screen_h=448;state.clip_w=640;state.clip_h=448;state.z=0x1234;
	state.blend=HCU_BITMAP_BLEND_PREMULTIPLIED;state.texture_layers=1;
	state.point_sampled=reader.requests[0].point_sampled;
	chain_mem=(uint8_t*)malloc(64*16);if(!chain_mem)return 15;memset(chain_mem,0xA5,64*16);chain_init(&chain,chain_mem,64);
	if(hcu_bitmap_quad_emit(&chain,&textures,0,&state,vertices)!=HCU_BITMAP_QUAD_OK||chain_qwords(&chain)!=49) return 16;
	{
		uint32_t *packet=(uint32_t*)(chain_mem+16); uint64_t *q=(uint64_t*)(chain_mem+32);
		if((packet[3]&0xFFFFu)!=47u||(((uint64_t*)chain_mem)[0]&0xFFFFu)!=48u||
		   ((((uint64_t*)chain_mem)[0]>>28)&7u)!=DMA_ID_CNT) return 18;
		if(q[8]!=GS_ALPHA(2,1,0,1,0)||q[14]!=GIF_TAG(6,1,1,GS_PRIM(GSX_PRIM_TRIANGLE,1,1,0,1,0,1,0,0),GIFX_FLG_PACKED,3)) return 19;
		if((uint32_t)q[16]!=128u||(uint32_t)(q[16]>>32)!=128u||(uint32_t)q[17]!=128u||(uint32_t)(q[17]>>32)!=64u) return 20;
		if((uint32_t)q[18]!=(uint32_t)((0.5f+0.125f*((float)image.width-1.0f))*16.0f+0.5f)||
		   (uint32_t)(q[18]>>32)!=(uint32_t)((0.5f+0.125f*((float)image.height-1.0f))*16.0f+0.5f)) return 23;
		if((uint32_t)q[20]!=(uint32_t)((2048.0f-320.0f+reader.requests[0].vertices[0].x)*16.0f+0.5f)||
		   (uint32_t)(q[20]>>32)!=(uint32_t)((2048.0f-224.0f+reader.requests[0].vertices[0].y)*16.0f+0.5f)) return 24;
		if(q[52]!=GIF_TAG(1,1,0,0,GIFX_FLG_PACKED,1)||q[54]!=GS_ALPHA(0,2,2,1,128)||q[55]!=GS_A_ALPHA_1) return 21;
		if(q[56]!=GIF_TAG(6,1,1,GS_PRIM(GSX_PRIM_TRIANGLE,1,1,0,1,0,1,0,0),GIFX_FLG_PACKED,3)) return 22;
	}
	printf("pipeline-ok source_datum=%u image_index=%u request=%u:%u vertices=4 gs_alpha=%u emitted_qw=%u gs_mode=triangle tex_width=%u tex_height=%u interface_sha256=%s\n",
	       image.source_id,image_index,(uint32_t)reader.requests[0].bitmap_tag_index,
	       reader.requests[0].bitmap_index,(uint32_t)(((reader.requests[0].vertices[0].color>>24)*128u+127u)/255u),chain_qwords(&chain),image.width,image.height,interface_sha);
	return 0;
}
