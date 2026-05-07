import argparse
import asyncio
import time
import httpx
import statistics

async def fetch(client: httpx.AsyncClient, url: str, headers: dict) -> float:
    start = time.perf_counter()
    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    return (time.perf_counter() - start) * 1000

async def run_scenario(name: str, client: httpx.AsyncClient, url: str, headers: dict, iterations: int = 50, concurrency: int = 5):
    print(f"\nRunning scenario: {name} ({iterations} requests, {concurrency} concurrent)")
    
    async def worker(queue):
        latencies = []
        while True:
            try:
                _ = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            lat = await fetch(client, url, headers)
            latencies.append(lat)
            queue.task_done()
        return latencies

    queue = asyncio.Queue()
    for _ in range(iterations):
        queue.put_nowait(1)
        
    tasks = [asyncio.create_task(worker(queue)) for _ in range(concurrency)]
    results = await asyncio.gather(*tasks)
    
    all_latencies = []
    for r in results:
        all_latencies.extend(r)
        
    all_latencies.sort()
    
    p50 = all_latencies[int(len(all_latencies) * 0.5)]
    p95 = all_latencies[int(len(all_latencies) * 0.95)]
    avg = sum(all_latencies) / len(all_latencies)
    
    print(f"  Avg: {avg:.2f} ms")
    print(f"  P50: {p50:.2f} ms")
    print(f"  P95: {p95:.2f} ms")
    
    return {"avg": avg, "p50": p50, "p95": p95}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    
    headers = {
        "Authorization": f"Bearer {args.token}",
        "X-API-Version": "1"
    }
    
    # We will use random pages to avoid cache for the 'After (index)' test
    # and exactly the same page to test the 'Repeated query (cached)' test.
    import random
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Warming up...")
        await fetch(client, f"{args.base_url}/api/profiles", headers)
        
        # Scenario 1: Filter by country + gender (Index hit, no cache) 
        print("\n--- Scenario 1: Filter by country + gender (Index hit, no cache) ---")
        lats = []
        for _ in range(50):
            page = random.randint(1, 100)
            lat = await fetch(client, f"{args.base_url}/api/profiles?country_id=US&gender=female&page={page}", headers)
            lats.append(lat)
        lats.sort()
        print(f"  Avg: {sum(lats)/len(lats):.2f} ms")
        print(f"  P50: {lats[int(len(lats)*0.5)]:.2f} ms")
        print(f"  P95: {lats[int(len(lats)*0.95)]:.2f} ms")
        
        # Scenario 2: Repeated query (Hits Redis Cache)
        print("\n--- Scenario 2: Repeated query (Cached) ---")
        url = f"{args.base_url}/api/profiles?country_id=GB&gender=male&page=1"
        # ensure it's cached
        await fetch(client, url, headers)
        await run_scenario("Repeated cache hits", client, url, headers, iterations=20, concurrency=3)

if __name__ == "__main__":
    asyncio.run(main())
