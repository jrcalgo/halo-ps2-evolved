/* The shared ILP32 prefix maps MSVC __inline to "static inline" for the
 * broader CE fixture. bsp3d.c already writes "static __inline", so use the
 * host keyword's native inline semantics for this one translation unit. */
#undef __inline
#define __inline inline
#include "../submodules/halo-ce-universal/source/physics/bsp3d.c"
