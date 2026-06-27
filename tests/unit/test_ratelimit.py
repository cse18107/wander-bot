from mcp_server.ratelimit import TokenBucket


def test_bucket_allows_burst_then_blocks() -> None:
    bucket = TokenBucket(rate_per_sec=0, burst=3)
    assert bucket.allow()
    assert bucket.allow()
    assert bucket.allow()
    assert bucket.allow() is False  # burst exhausted, no refill at rate 0
