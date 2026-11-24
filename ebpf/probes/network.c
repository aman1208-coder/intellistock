/* TCP tracepoint hook aggregates retransmission counts in a BPF map. */
#include <uapi/linux/ptrace.h>
BPF_ARRAY(retransmits, u64, 1);
TRACEPOINT_PROBE(tcp, tcp_retransmit_skb) { int key=0; u64 *n=retransmits.lookup(&key); if(n) __sync_fetch_and_add(n,1); return 0; }
