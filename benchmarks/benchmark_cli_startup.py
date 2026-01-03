import subprocess
import time


def benchmark():
    start = time.perf_counter()
    subprocess.run(
        ["python", "-m", "cortex", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return time.perf_counter() - start


if __name__ == "__main__":
    runs = 5
    times = [benchmark() for _ in range(runs)]
    print(f"CLI Startup Avg: {sum(times)/runs:.4f} seconds")
