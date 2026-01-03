import subprocess
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

benchmarks = [
    "benchmark_cli_startup.py",
    "benchmark_command_parsing.py",
    "benchmark_cache_ops.py",
    "benchmark_streaming.py",
]


def run(jit_enabled):
    env = os.environ.copy()
    env["PYTHON_JIT"] = "1" if jit_enabled else "0"

    # Add project root to PYTHONPATH
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    print("\n==============================")
    print("JIT ENABLED:" if jit_enabled else "JIT DISABLED:")
    print("==============================")

    for bench in benchmarks:
        subprocess.run([sys.executable, bench], env=env)


if __name__ == "__main__":
    run(False)
    run(True)
