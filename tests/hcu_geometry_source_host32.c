/* Compile production CE geosphere generation/disposal from geometry.c. */
#undef __inline
#define __inline inline
#undef _inline
#define _inline inline
#define halo_ce_random hcu_geometry_ce_random
#include "../submodules/halo-ce-universal/source/math/geometry.c"
