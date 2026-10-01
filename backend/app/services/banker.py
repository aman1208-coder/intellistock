"""Banker's deadlock-avoidance checks and per-warehouse resource state."""

from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import uuid4


def _validate_vector(vector: Sequence[int], width: int, name: str) -> List[int]:
    values = list(vector)
    if len(values) != width:
        raise ValueError(f"{name} must contain exactly {width} resource values")
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError(f"{name} values must be non-negative integers")
    return values


def is_safe_state(
    available: Sequence[int],
    allocation: Sequence[Sequence[int]],
    need: Sequence[Sequence[int]],
) -> Tuple[bool, List[int]]:
    """Return whether all processes can finish and their safe sequence."""
    available_values = list(available)
    process_count = len(allocation)
    if len(need) != process_count:
        raise ValueError("allocation and need must have the same process count")

    width = len(available_values)
    if width == 0:
        raise ValueError("at least one resource type is required")
    work = _validate_vector(available_values, width, "available")
    allocations = [_validate_vector(row, width, "allocation row") for row in allocation]
    needs = [_validate_vector(row, width, "need row") for row in need]

    finished = [False] * process_count
    safe_sequence: List[int] = []
    while len(safe_sequence) < process_count:
        found_process = False
        for process_index in range(process_count):
            if finished[process_index]:
                continue
            if all(
                needs[process_index][resource] <= work[resource]
                for resource in range(width)
            ):
                work = [
                    work[resource] + allocations[process_index][resource]
                    for resource in range(width)
                ]
                finished[process_index] = True
                safe_sequence.append(process_index)
                found_process = True
        if not found_process:
            return False, safe_sequence
    return True, safe_sequence


@dataclass
class _WarehouseState:
    total: List[int]
    available: List[int]
    allocation: Dict[str, List[int]] = field(default_factory=dict)
    maximum: Dict[str, List[int]] = field(default_factory=dict)


_warehouse_states: Dict[int, _WarehouseState] = {}
_state_lock = RLock()


def configure_warehouse_resources(
    warehouse_id: int,
    total_resources: Sequence[int],
    available_resources: Sequence[int],
) -> None:
    """Initialize resource state; later calls synchronize persisted capacity."""
    total = _validate_vector(total_resources, len(total_resources), "total_resources")
    available = _validate_vector(available_resources, len(total), "available_resources")
    if any(available[index] > total[index] for index in range(len(total))):
        raise ValueError("available resources cannot exceed total resources")

    with _state_lock:
        state = _warehouse_states.get(warehouse_id)
        if state is None:
            _warehouse_states[warehouse_id] = _WarehouseState(total, available)
            return
        if state.total != total:
            raise ValueError("warehouse resource totals cannot change while requests are active")
        # Capacity is persisted on Warehouse; dock and equipment availability is process-local.
        state.available[0] = available[0]


def request_allocation(
    warehouse_id: int,
    request_vector: Sequence[int],
    process_id: Optional[str] = None,
    max_claim: Optional[Sequence[int]] = None,
) -> bool:
    """Grant a process request only when it leaves the warehouse in a safe state."""
    with _state_lock:
        state = _warehouse_states.get(warehouse_id)
        if state is None:
            return False

        request = _validate_vector(request_vector, len(state.total), "request_vector")
        process_name = process_id or f"request-{uuid4().hex}"
        is_new_process = process_name not in state.maximum
        if is_new_process:
            maximum = _validate_vector(
                max_claim if max_claim is not None else request,
                len(state.total),
                "max_claim",
            )
            if any(maximum[index] > state.total[index] for index in range(len(state.total))):
                raise ValueError("max_claim cannot exceed total resources")
            state.maximum[process_name] = maximum
            state.allocation[process_name] = [0] * len(state.total)
        elif max_claim is not None:
            maximum = _validate_vector(max_claim, len(state.total), "max_claim")
            if maximum != state.maximum[process_name]:
                raise ValueError("max_claim cannot change for an active process")

        current_allocation = state.allocation[process_name]
        need = [
            state.maximum[process_name][index] - current_allocation[index]
            for index in range(len(state.total))
        ]
        if any(request[index] > need[index] for index in range(len(state.total))) or any(
            request[index] > state.available[index] for index in range(len(state.total))
        ):
            if is_new_process:
                del state.maximum[process_name]
                del state.allocation[process_name]
            return False

        next_available = [
            state.available[index] - request[index]
            for index in range(len(state.total))
        ]
        process_names = list(state.maximum)
        next_allocations = [state.allocation[name][:] for name in process_names]
        process_index = process_names.index(process_name)
        next_allocations[process_index] = [
            next_allocations[process_index][index] + request[index]
            for index in range(len(state.total))
        ]
        needs = [
            [
                state.maximum[name][index] - next_allocations[index_in_list][index]
                for index in range(len(state.total))
            ]
            for index_in_list, name in enumerate(process_names)
        ]
        safe, _ = is_safe_state(next_available, next_allocations, needs)
        if not safe:
            if is_new_process:
                del state.maximum[process_name]
                del state.allocation[process_name]
            return False

        state.available = next_available
        state.allocation[process_name] = next_allocations[process_index]
        return True


def rollback_allocation(
    warehouse_id: int,
    process_id: str,
    request_vector: Sequence[int],
) -> None:
    """Undo an in-memory grant if persisting its capacity reservation fails."""
    with _state_lock:
        state = _warehouse_states.get(warehouse_id)
        if state is None or process_id not in state.allocation:
            return
        request = _validate_vector(request_vector, len(state.total), "request_vector")
        allocation = state.allocation[process_id]
        if any(request[index] > allocation[index] for index in range(len(state.total))):
            raise ValueError("cannot roll back more resources than the process holds")
        state.available = [
            state.available[index] + request[index]
            for index in range(len(state.total))
        ]
        state.allocation[process_id] = [
            allocation[index] - request[index]
            for index in range(len(state.total))
        ]
        if not any(state.allocation[process_id]):
            del state.allocation[process_id]
            del state.maximum[process_id]


def get_warehouse_state(warehouse_id: int) -> Optional[dict]:
    """Return a detached snapshot suitable for an API response."""
    with _state_lock:
        state = _warehouse_states.get(warehouse_id)
        if state is None:
            return None
        process_names = list(state.maximum)
        allocations = [state.allocation[name][:] for name in process_names]
        needs = [
            [
                state.maximum[name][index] - state.allocation[name][index]
                for index in range(len(state.total))
            ]
            for name in process_names
        ]
        safe, sequence = is_safe_state(state.available, allocations, needs)
        return {
            "total": state.total[:],
            "available": state.available[:],
            "allocation": {name: state.allocation[name][:] for name in process_names},
            "maximum": {name: state.maximum[name][:] for name in process_names},
            "safe": safe,
            "safe_sequence": [process_names[index] for index in sequence],
        }


def reset_warehouse_state(warehouse_id: int) -> None:
    """Clear process-local state; primarily useful for isolated tests."""
    with _state_lock:
        _warehouse_states.pop(warehouse_id, None)