import time
import argparse
from cortex.cli import CortexCLI


def benchmark():
    cli = CortexCLI(verbose=False)

    start = time.perf_counter()
    for _ in range(3000):
        parser = argparse.ArgumentParser()
        parser.add_argument("command", nargs="?")
        parser.parse_args(["status"])
    return time.perf_counter() - start


if __name__ == "__main__":
    duration = benchmark()
    print(f"Command Parsing Time: {duration:.4f} seconds")
