/* BCC tracepoint example: sched_wakeup/sched_switch feed kernel maps for
 * run-queue delay and on-CPU time. The verifier checks memory and control flow. */
#include <uapi/linux/ptrace.h>
BPF_HASH(wakeup_ns, u32, u64);
BPF_HISTOGRAM(runq_latency_us);
TRACEPOINT_PROBE(sched, sched_wakeup) { u32 pid=args->pid; u64 now=bpf_ktime_get_ns(); wakeup_ns.update(&pid,&now); return 0; }
TRACEPOINT_PROBE(sched, sched_switch) { u32 pid=args->next_pid; u64 *ts=wakeup_ns.lookup(&pid); if(ts){runq_latency_us.increment(bpf_log2l((bpf_ktime_get_ns()-*ts)/1000+1)); wakeup_ns.delete(&pid);} return 0; }
