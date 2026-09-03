"""`Scheduler` -- entirely offline, no real timers (`sleep` injected)."""

from __future__ import annotations

from service.poller import Scheduler


def test_scheduler_stops_after_max_iterations() -> None:
    calls = []
    sleeps = []
    scheduler = Scheduler(poll_once=lambda: calls.append(1) or len(calls),
                           interval_seconds=5.0, sleep=sleeps.append,
                           max_iterations=3)
    results = scheduler.run()
    assert results == [1, 2, 3]
    assert len(calls) == 3
    # Sleeps between iterations, not after the last one.
    assert sleeps == [5.0, 5.0]
