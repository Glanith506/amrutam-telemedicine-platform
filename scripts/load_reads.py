"""Small read-only smoke benchmark, not a capacity certification."""

import argparse, time, math
from concurrent.futures import ThreadPoolExecutor
import httpx

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:8000")
p.add_argument("--requests", type=int, default=60)
p.add_argument("--concurrency", type=int, default=4)
a = p.parse_args()
if not 1 <= a.requests <= 100000 or not 1 <= a.concurrency <= 256:
    raise SystemExit("Invalid bounds")


def get(_):
    t = time.perf_counter()
    try:
        r = httpx.get(a.url.rstrip("/") + "/doctors", timeout=10)
        status = r.status_code
    except httpx.HTTPError:
        status = 0
    return time.perf_counter() - t, status


with ThreadPoolExecutor(a.concurrency) as pool:
    results = list(pool.map(get, range(a.requests)))
latencies = sorted(x[0] * 1000 for x in results)
print(
    {
        "requests": len(results),
        "errors": sum(x[1] != 200 for x in results),
        "p95_ms": round(latencies[math.ceil(len(latencies) * 0.95) - 1], 2),
    }
)
