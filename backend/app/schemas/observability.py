from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DbLatency(BaseModel):
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    slow_query_count: int = 0
    threshold_ms: int = 200
    samples: int = 0


class NetworkStats(BaseModel):
    retransmits: int = 0
    resets: int = 0
    connection_failures: int = 0
    connection_rate: float = 0
    tcp_rtt_p95_ms: float = 0


class SecurityEvent(BaseModel):
    timestamp: str
    pid: int
    comm: str
    type: str
    details: str
    severity: Literal["low", "medium", "high", "critical"]


class ObservabilityStatus(BaseModel):
    collector: Literal["ebpf", "fallback"]
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
    cpu: dict[str, Any] = Field(default_factory=dict)
    syscalls: dict[str, Any] = Field(default_factory=dict)
    db_latency: dict[str, Any] = Field(default_factory=dict)
    network: dict[str, Any] = Field(default_factory=dict)
    security_events: list[SecurityEvent] = Field(default_factory=list)
    probes_loaded: list[str] = Field(default_factory=list)
