#include "hcu_pose_asset.h"

#include <math.h>
#include <string.h>

#define HPOS_HEADER_BYTES 24u
#define HPOS_NODE_BYTES 16u
#define HPOS_MAX_BYTES 65536u

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static float rdf32(const uint8_t *p) { uint32_t u = rd32(p); float f; memcpy(&f, &u, sizeof f); return f; }
static const uint8_t *node_at(const uint8_t *p, uint16_t i) { return p + HPOS_HEADER_BYTES + rd32(p + 16) + (size_t)i * HPOS_NODE_BYTES; }
static size_t node_off(const uint8_t *p) { return HPOS_HEADER_BYTES + rd32(p + 16); }
static size_t floats_off(const uint8_t *p) { return node_off(p) + (size_t)rd16(p + 10) * HPOS_NODE_BYTES; }

int hcu_pose_asset_validate(const void *blob, size_t bytes)
{
	const uint8_t *p = (const uint8_t *)blob;
	uint16_t asset, frames, nodes, qcount, tcount;
	uint32_t names;
	uint32_t body;
	size_t no, fo, qbytes, tbytes, i, j;
	if (!p || bytes < HPOS_HEADER_BYTES || bytes > HPOS_MAX_BYTES || memcmp(p, "HPOS", 4) != 0 || rd16(p + 4) != 1) return 0;
	/* Header: magic,version,asset,frames,nodes,qcount,tcount,names_bytes,body_bytes. */
	frames=rd16(p+8); nodes=rd16(p+10); qcount=rd16(p+12); tcount=rd16(p+14); names=rd32(p+16); body=rd32(p+20); asset=rd16(p+6);
	if ((asset != 1 && asset != 2) || !frames || frames > 256 || !nodes || nodes > 64 || !qcount || !names || names > 4096 ||
	    body != bytes - HPOS_HEADER_BYTES || names > bytes - HPOS_HEADER_BYTES) return 0;
	if ((asset == 1 && tcount != nodes) || (asset == 2 && !tcount)) return 0;
	no=HPOS_HEADER_BYTES; fo=no + names + (size_t)nodes * HPOS_NODE_BYTES;
	qbytes=(size_t)qcount * 4u * sizeof(float); tbytes=(size_t)tcount * 3u * sizeof(float);
	if (fo > bytes || qbytes > bytes-fo || tbytes > bytes-fo-qbytes || fo+qbytes+tbytes+11u*sizeof(float) != bytes) return 0;
	for (i=0; i<(qbytes+tbytes+11u*sizeof(float))/sizeof(float); ++i)
		if (!isfinite(rdf32(p+fo+i*sizeof(float)))) return 0;
	for (i=0; i<nodes; ++i) {
		const uint8_t *n=p+no+names+i*HPOS_NODE_BYTES;
		uint32_t name=rd32(n); int16_t parent=(int16_t)rd16(n+4);
		uint16_t qa=rd16(n+8), qn=rd16(n+10), ta=rd16(n+12), tn=rd16(n+14);
		const uint8_t *namep;
		if (name >= names || !memchr(p+no+name, 0, names-name) || parent < -1 || parent >= (int16_t)i || n[6] > 1 || n[7] != 0 ||
		    (qn != 1 && qn != frames) || qa+qn > qcount) return 0;
		namep=p+no+name; if (namep[0] == 0) return 0;
		for (j=0; namep[j]; ++j) if (namep[j] < 0x20 || namep[j] > 0x7e) return 0;
		for (j=0; j<i; ++j) { const uint8_t *prior=p+no+names+j*HPOS_NODE_BYTES; if (strcmp((const char *)(p+no+rd32(prior)),(const char *)namep)==0) return 0; }
	if (asset == 1) { if (tn != 1 || ta != i) return 0; }
		else if ((tn != 1 && tn != frames) || ta+tn > tcount) return 0;
		for (j=0; j<qn*4u; ++j) if (!isfinite(rdf32(p+fo+((size_t)qa*4u+j)*4u))) return 0;
		if (asset == 2) for (j=0; j<tn*3u; ++j) if (!isfinite(rdf32(p+fo+qbytes+((size_t)ta*3u+j)*4u))) return 0;
	}
	for (i=0; i<11; ++i) if (!isfinite(rdf32(p+fo+qbytes+tbytes+i*4u))) return 0;
	return 1;
}

int hcu_pose_asset_find_node(const void *blob, size_t bytes, const char *name)
{
	const uint8_t *p=(const uint8_t *)blob; uint16_t count; uint32_t names; size_t i;
	if (!name || !hcu_pose_asset_validate(blob,bytes)) return -1;
	count=rd16(p+10); names=rd32(p+16);
	for (i=0; i<count; ++i) { const uint8_t *n=node_at(p,(uint16_t)i); uint32_t off=rd32(n); if (off<names && strcmp((const char *)(p+HPOS_HEADER_BYTES+off),name)==0) return (int)i; }
	return -1;
}

int hcu_pose_asset_sample(const void *blob, size_t bytes, uint16_t index,
	uint32_t frame, float q[4], float t[3], uint8_t *override)
{
	const uint8_t *p=(const uint8_t *)blob, *n; uint16_t nodes,frames,qcount,qa,qn,ta,tn; size_t fo,qbytes; uint32_t f; unsigned i;
	if (!q || !t || !override || !hcu_pose_asset_validate(blob,bytes)) return 0;
	nodes=rd16(p+10); frames=rd16(p+8); qcount=rd16(p+12);
	if (index>=nodes) return 0;
	n=node_at(p,index); qa=rd16(n+8); qn=rd16(n+10); ta=rd16(n+12); tn=rd16(n+14);
	f=qn>1 ? frame%frames : 0;
	fo=floats_off(p); qbytes=(size_t)qcount*4u*sizeof(float);
	for(i=0;i<4;i++) q[i]=rdf32(p+fo+((size_t)(qa+f)*4u+i)*4u);
	if(rd16(p+6)==1) { for(i=0;i<3;i++) t[i]=rdf32(p+fo+qbytes+((size_t)index*3u+i)*4u); }
	else { f=tn>1 ? frame%frames : 0; for(i=0;i<3;i++) t[i]=rdf32(p+fo+qbytes+((size_t)(ta+f)*3u+i)*4u); }
	*override=n[6];
	return 1;
}

int hcu_pose_asset_constants(const void *blob, size_t bytes, float hold[4], float meshq[4], float mesht[3])
{
	const uint8_t *p=(const uint8_t *)blob; size_t off; unsigned i;
	if (!hold || !meshq || !mesht || !hcu_pose_asset_validate(blob,bytes)) return 0;
	off=floats_off(p)+(size_t)rd16(p+12)*4u*sizeof(float)+(size_t)rd16(p+14)*3u*sizeof(float);
	for(i=0;i<4;i++) hold[i]=rdf32(p+off+i*4u);
	for(i=0;i<4;i++) meshq[i]=rdf32(p+off+(4u+i)*4u);
	for(i=0;i<3;i++) mesht[i]=rdf32(p+off+(8u+i)*4u);
	return 1;
}
