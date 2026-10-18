/* Execute the pinned runtime visibility algorithm without a renderer or PS2 SDK. */
#include "world/bsp.h"
#include "render/vis.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv)
{
    if(argc!=8) return 2;
    FILE *f=fopen(argv[1],"rb"); if(!f) return 3;
    if(fseek(f,0,SEEK_END)) return 4;
    long size=ftell(f); if(size<=0 || fseek(f,0,SEEK_SET)) return 4;
    unsigned char *data=malloc((size_t)size), *memory=malloc(1024*1024);
    if(!data || !memory || fread(data,1,(size_t)size,f)!=(size_t)size) return 5;
    fclose(f);
    bsp_section s; if(bsp_open(&s,data,(size_t)size)!=BSP_OK) return 6;
    arena_t a; arena_init(&a,"visibility",memory,1024*1024);
    vis_t v; if(vis_init(&v,&a,&s)) return 7;
    camera_t cam; camera_init(&cam);
    for(int i=0;i<3;i++) cam.pos[i]=strtof(argv[i+2],NULL);
    cam.yaw=strtof(argv[5],NULL)*3.14159265358979323846f/180.0f;
    cam.pitch=strtof(argv[6],NULL)*3.14159265358979323846f/180.0f;
    v.force_all=atoi(argv[7]);
    frustum_t fr; float clip[4][4]; camera_frustum(&cam,&fr);camera_clip_matrix(&cam,clip);
    vis_run(&v,&s,&cam,&fr,(const float (*)[4])clip);
    printf("{\"camera_cluster\":%d,\"portals_tested\":%u,\"portals_passed\":%u,\"arena_high\":%zu,\"batches\":[",v.camera_cluster,v.portals_tested,v.portals_passed,a.high);
    for(unsigned i=0;i<v.batch_count;i++) printf("%s%u",i?",":"",v.batches[i]);
    printf("]}\n");free(data);free(memory);return 0;
}
