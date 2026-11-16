"""Bounded polling for observable calculator state, not elapsed settle sleeps."""
from time import monotonic

from collectors.common import FetchError


def wait_until(page, predicate, description: str, timeout_ms: int = 15000):
    deadline = monotonic() + timeout_ms / 1000
    while True:
        value = predicate()
        if value:
            return value
        if monotonic() >= deadline:
            raise FetchError(f'timed out waiting for {description}')
        page.wait_for_timeout(100)  # polling interval, never a readiness assumption
