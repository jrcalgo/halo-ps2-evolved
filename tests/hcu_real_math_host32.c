/* External definitions for CE header helpers that the host fixture's
 * translation-unit-local inline prefix does not emit as linkable symbols. */
#define REAL_MATH_EXTERNAL_POINT_FROM_LINE3D 1
#define REAL_MATH_EXTERNAL_PLANE3D_DISTANCE_TO_POINT 1
#include "cseries.h"
#include "math/real_math.h"

real_point3d *point_from_line3d(real_point3d const *point,
	real_vector3d const *vector, real t, real_point3d *result)
{
	result->x = vector->i * t + point->x;
	result->y = vector->j * t + point->y;
	result->z = vector->k * t + point->z;
	return result;
}

real plane3d_distance_to_point(real_plane3d const *plane,
	real_point3d const *point)
{
	return point->x * plane->n.i + point->y * plane->n.j +
		point->z * plane->n.k - plane->d;
}
