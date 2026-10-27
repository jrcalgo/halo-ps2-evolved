/* Host prefix for the C5 retail lifecycle closure (tools/c5_retail_lifecycle_producer.py).
 * Included after tests/soundreq_host_prefix.h, before any CE header. It makes three things the
 * host compile needs and the MSVC/PS2 builds do not: the struct tags the CE prototypes name before
 * their definitions (a struct first named in a prototype's parameter list is a new type, so the
 * later definition conflicts with it), the libc names for the Win32 string calls, and the one PS2
 * render body the host never enters (declared here, linked as a blocking stub). */
#include <strings.h>

#define _stricmp strcasecmp
#define _snprintf snprintf

/* Every struct tag the sources define is declared at file scope before any header's prototypes
 * (tools/c5_retail_lifecycle_producer.py writes the list, c5_struct_tags.h, into the build
 * directory): a struct first named in a parameter list is a new type, and the later definition
 * conflicts with it. */
struct real_matrix4x3 *render_interpolation_object_node_matrices(long object_index);

/* Port functions the closure calls and does not compile (their definitions are stubs that
 * record a blocker when reached): the same prototypes as port/linux/include/halo_linux_source_fixups.h. */
unsigned char custom_edition_vehicle_placement_allowed(struct scenario_object_datum const *placement);

/* Xbox debug-monitor types cseries_windows.h names (the host has no exception contexts). */
typedef struct _EXCEPTION_POINTERS *PEXCEPTION_POINTERS;
typedef struct _CONTEXT CONTEXT;
void render_interpolation_tick(void);
float render_interpolation_fraction(void);

/* Win32 performance counter (the PS2 build's timers: port/ps2); the host gives them clock_gettime */
int QueryPerformanceFrequency(void *frequency);
int QueryPerformanceCounter(void *count);
void render_interpolation_frame_begin(void);
void render_interpolation_frame_end(void);
