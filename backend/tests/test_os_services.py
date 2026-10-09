"""Unit tests for deadlock avoidance and inventory job scheduling."""

import unittest
from concurrent.futures import ThreadPoolExecutor

from app.services.banker import (
    configure_warehouse_resources,
    get_warehouse_state,
    is_safe_state,
    request_allocation,
    reset_warehouse_state,
)
from app.services.priority_scheduler import (
    HIGH_PRIORITY,
    NORMAL_PRIORITY,
    URGENT_PRIORITY,
    PriorityScheduler,
    priority_for_stock,
)


class BankersAlgorithmTests(unittest.TestCase):
    def test_classic_safe_state_returns_complete_safe_sequence(self) -> None:
        available = [3, 3, 2]
        allocation = [
            [0, 1, 0],
            [2, 0, 0],
            [3, 0, 2],
            [2, 1, 1],
            [0, 0, 2],
        ]
        need = [
            [7, 4, 3],
            [1, 2, 2],
            [6, 0, 0],
            [0, 1, 1],
            [4, 3, 1],
        ]

        safe, sequence = is_safe_state(available, allocation, need)

        self.assertTrue(safe)
        self.assertEqual(sequence, [1, 3, 4, 0, 2])

    def test_unsafe_state_returns_false(self) -> None:
        safe, sequence = is_safe_state(
            [0, 0, 0],
            [[1, 0, 0], [0, 1, 0]],
            [[0, 1, 0], [1, 0, 0]],
        )

        self.assertFalse(safe)
        self.assertEqual(sequence, [])

    def test_request_allocation_denies_unsafe_request(self) -> None:
        warehouse_id = 930002
        try:
            configure_warehouse_resources(warehouse_id, [3, 3, 2], [3, 3, 2])
            self.assertTrue(
                request_allocation(
                    warehouse_id,
                    [1, 0, 0],
                    process_id="inbound-a",
                    max_claim=[3, 2, 2],
                )
            )
            self.assertFalse(
                request_allocation(
                    warehouse_id,
                    [2, 3, 0],
                    process_id="inbound-b",
                    max_claim=[3, 3, 2],
                )
            )
        finally:
            reset_warehouse_state(warehouse_id)

    def test_reset_warehouse_state_restores_capacity(self) -> None:
        warehouse_id = 930003
        try:
            configure_warehouse_resources(warehouse_id, [9, 6, 4], [9, 6, 4])
            approved = request_allocation(
                warehouse_id,
                [2, 1, 1],
                process_id="reset-demo",
                max_claim=[4, 3, 2],
            )
            self.assertTrue(approved)
            state = get_warehouse_state(warehouse_id)
            self.assertIsNotNone(state)
            self.assertEqual(state["available"], [7, 5, 3])

            reset_warehouse_state(warehouse_id)
            self.assertIsNone(get_warehouse_state(warehouse_id))
        finally:
            reset_warehouse_state(warehouse_id)


class PrioritySchedulerTests(unittest.TestCase):
    def test_stock_levels_map_to_expected_priorities(self) -> None:
        self.assertEqual(priority_for_stock(0, 10), URGENT_PRIORITY)
        self.assertEqual(priority_for_stock(3, 10), HIGH_PRIORITY)
        self.assertEqual(priority_for_stock(10, 10), NORMAL_PRIORITY)

    def test_jobs_pop_in_priority_order_and_preserve_equal_priority_order(self) -> None:
        scheduler = PriorityScheduler()
        normal = scheduler.enqueue(NORMAL_PRIORITY, "routine_audit")
        high = scheduler.enqueue(HIGH_PRIORITY, "inventory_check", product_id=2)
        urgent = scheduler.enqueue(URGENT_PRIORITY, "inventory_check", product_id=1)
        another_urgent = scheduler.enqueue(URGENT_PRIORITY, "inventory_check", product_id=3)

        jobs = scheduler.snapshot()

        self.assertEqual([job.priority for job in jobs], [1, 1, 2, 3])
        self.assertEqual([job.id for job in jobs], [urgent.id, another_urgent.id, high.id, normal.id])
        self.assertEqual(scheduler.pop_next(), urgent)

    def test_concurrent_enqueues_keep_all_jobs(self) -> None:
        scheduler = PriorityScheduler()

        def enqueue_job(index: int) -> None:
            scheduler.enqueue(
                index % 3 + 1,
                "inventory_check",
                product_id=index + 1,
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(enqueue_job, range(100)))

        jobs = scheduler.snapshot()
        self.assertEqual(len(jobs), 100)
        self.assertEqual(len({job.id for job in jobs}), 100)
        self.assertEqual([job.priority for job in jobs], sorted(job.priority for job in jobs))


if __name__ == "__main__":
    unittest.main()