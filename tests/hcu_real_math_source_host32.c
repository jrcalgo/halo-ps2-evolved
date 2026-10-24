/* Compile the production CE translation unit while avoiding the fixture
 * prefix's `static inline` compatibility spelling on already-static CE
 * declarations. */
#undef __inline
#define __inline inline
#undef _inline
#define _inline inline
#define halo_ce_random hcu_real_math_ce_random
#include "../submodules/halo-ce-universal/source/math/real_math.c"
