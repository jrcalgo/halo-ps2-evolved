/* Host prototypes for the usage log collision_bsp_test_sphere calls.
 * collision_usage.h is suppressed in this fixture; the definitions live in
 * hcu_swept_collision_main.c and do not modify collision-user depth. */
#ifndef HCU_SWEPT_COLLISION_HOST_H
#define HCU_SWEPT_COLLISION_HOST_H

void collision_log_usage(short collision_function);
void collision_log_start_time(LARGE_INTEGER *start_time);
void collision_log_end_time(short collision_function, long start_time);

#endif
