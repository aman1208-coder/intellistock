/* sys_enter_openat is a syscall tracepoint; production policy should resolve
 * paths in user space and apply a configured allowlist before emitting events. */
#include <uapi/linux/ptrace.h>
BPF_PERF_OUTPUT(open_events);
struct open_event { u32 pid; char comm[TASK_COMM_LEN]; char path[128]; };
TRACEPOINT_PROBE(syscalls, sys_enter_openat) { struct open_event e={}; e.pid=bpf_get_current_pid_tgid()>>32; bpf_get_current_comm(&e.comm,sizeof(e.comm)); bpf_probe_read_user_str(&e.path,sizeof(e.path),(void *)args->filename); open_events.perf_submit(args,&e,sizeof(e)); return 0; }
