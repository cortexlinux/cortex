import time

def fake_stream():
    for i in range(2000):
        yield i

def benchmark():
    start = time.perf_counter()
    for _ in fake_stream():
        pass
    return time.perf_counter() - start

if __name__ == "__main__":
    duration = benchmark()
    print(f"Streaming Time: {duration:.4f} seconds")
