import time

from skibot.riot.rate_limiter import SlidingWindowRateLimiter


def test_blocks_when_window_full():
    rl = SlidingWindowRateLimiter([(2, 0.3)])
    t0 = time.monotonic()
    for _ in range(3):
        rl.acquire()
    assert time.monotonic() - t0 >= 0.3


def test_no_wait_under_limit():
    rl = SlidingWindowRateLimiter([(100, 120.0)])
    t0 = time.monotonic()
    for _ in range(10):
        rl.acquire()
    assert time.monotonic() - t0 < 0.5
