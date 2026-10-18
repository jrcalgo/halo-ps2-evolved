typedef struct { int init_count, max_count; } ee_sema_t;
typedef struct { void *func,*stack,*gp_reg; int stack_size,initial_priority; } ee_thread_t;
int WaitSema(int); int SignalSema(int); int PollSema(int);
int CreateSema(ee_sema_t *); int DeleteSema(int);
int CreateThread(ee_thread_t *); int StartThread(int,void *);
int TerminateThread(int); int DeleteThread(int);
