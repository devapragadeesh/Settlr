"""The scheduler: call a poll function on an interval. stdlib only -- no
celery, per the plan's decision to keep Track C's operational surface small.

Injectable `sleep` and a `max_iterations` cap make this testable without a
real timer: `test_scheduler_stops_after_max_iterations` runs a full schedule
in milliseconds.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class Scheduler:
    poll_once: Callable[[], object]
    interval_seconds: float
    sleep: Callable[[float], None] = time.sleep
    max_iterations: int | None = None

    def run(self) -> list[object]:
        results = []
        iteration = 0
        while self.max_iterations is None or iteration < self.max_iterations:
            results.append(self.poll_once())
            iteration += 1
            if self.max_iterations is not None and iteration >= self.max_iterations:
                break
            self.sleep(self.interval_seconds)
        return results
