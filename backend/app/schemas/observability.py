from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class DbLatency(BaseModel):
    p50_ms: float = Field(default=0, ge=0)
    p95_ms: float = Field(default=0, ge=0)
    p99_ms: float = Field(default=0, ge=0)
    slow_query_count: int = Field(default=0, ge=0)
    threshold_ms: int = Field(default=200, ge=1, le=60000)
    samples: int = Field(default=0, ge=0)


class NetworkStats(BaseModel):
    retransmits: int = Field(default=0, ge=0)
    resets: int = Field(default=0, ge=0)
    connection_failures: int = Field(default=0, ge=0)
    connection_rate: float = Field(default=0, ge=0)
    tcp_rtt_p95_ms: float = Field(default=0, ge=0)


class CpuMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_percent: float | None = Field(default=None, ge=0)
    rss_bytes: int | None = Field(default=None, ge=0)
    runq_p95_us: float | None = Field(default=None, ge=0)


class SyscallMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[Annotated[str, StringConstraints(max_length=16)], int] = Field(default_factory=dict, max_length=512)
    latency_histogram_log2_us: dict[Annotated[str, StringConstraints(max_length=8)], int] = Field(default_factory=dict, max_length=64)
    p95_us: float | None = Field(default=None, ge=0)


class SecurityEvent(BaseModel):
    timestamp: str = Field(max_length=64)
    pid: int = Field(ge=0)
    comm: str = Field(max_length=32)
    type: str = Field(max_length=64)
    details: str = Field(max_length=256)
    severity: Literal["low", "medium", "high", "critical"]


class ObservabilityStatus(BaseModel):
    collector: Literal["ebpf", "fallback"]
    active_database: Literal["postgresql", "sqlite"]
    kernel_version: str
    probes_loaded: list[str]
    last_update: str | None
    enabled: bool


class ObservabilityMetrics(BaseModel):
    collector: Literal["ebpf", "fallback"]
    timestamp: str
    cpu: dict[str, Any] = Field(default_factory=dict)
    syscalls: dict[str, Any] = Field(default_factory=dict)
    db_latency: DbLatency
    network: NetworkStats
    app_latency: dict[str, Any] = Field(default_factory=dict)
    last_update: str | None = None


class ObservabilityIngest(BaseModel):
    collector: Literal["ebpf", "fallback"] = "ebpf"
    cpu: CpuMetrics = Field(default_factory=CpuMetrics)
    syscalls: SyscallMetrics = Field(default_factory=SyscallMetrics)
    db_latency: DbLatency = Field(default_factory=DbLatency)
    network: NetworkStats = Field(default_factory=NetworkStats)
    security_events: list[SecurityEvent] = Field(default_factory=list, max_length=100)
    probes_loaded: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list, max_length=64)
