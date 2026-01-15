# 🚀 Cortex JIT Benchmarking Suite

The **Cortex JIT Benchmarking Suite** is a specialized performance analysis tool designed to measure and compare the impact of the **Python 3.13+ Experimental JIT (Just-In-Time) compiler** on core Cortex operations.

As Cortex moves toward supporting modern Python features, this suite provides developers with empirical data to identify performance hotspots and quantify the speedups provided by JIT compilation.

---

## 🛠 Command Reference

The suite is fully integrated into the `cortex` CLI. Use the following commands to manage and run your benchmarks.

### 1. Environment Status

Check if your current system supports JIT and verify if it is currently active.

```bash
cortex jit-benchmark info
```

### 2. Available Tests

List the specific benchmark categories available for execution.

```bash
cortex jit-benchmark list
```

### 3. Execution

Run the full suite or target specific operations.

```bash
# Run all benchmarks with default (100) iterations
cortex jit-benchmark run

# Run a specific benchmark (cli, parse, cache, or stream)
cortex jit-benchmark run -b cache

# Customize precision with iterations
cortex jit-benchmark run -i 500

# Export results for comparison
cortex jit-benchmark run -o baseline_results.json
```

### 4. Comparison

Compare two sets of results (e.g., Baseline vs. JIT) to calculate speedup percentages.

```bash
cortex jit-benchmark compare --baseline baseline.json --jit jit_enabled.json
```

---

## 📊 Benchmark Categories

| Category | Method | Description |
|----------|--------|-------------|
| CLI Startup | _bench_cli_startup | Measures argparse initialization and CLI entry-point routing latency. |
| Command Parsing | _bench_command_parsing | Benchmarks the splitting and interpretation of complex natural language commands. |
| Cache Operations | _bench_cache_operations | Tests JSON serialization/deserialization and retrieval speed of the semantic cache. |
| Response Streaming | _bench_response_streaming | Simulates high-volume processing of LLM response chunks and string manipulation. |

---

## 🧪 Statistical Methodology

To ensure accuracy and scientific rigor, the suite employs the following logic:

- **Warmup Phase**: Every benchmark function is executed once before timing starts to ensure the CPU cache is primed and the JIT profiler has observed the code path.
- **Iterative Measurement**: Functions are run $N$ times using `time.perf_counter()` for high-resolution timing.
- **Metrics**:
  - **Mean**: The average execution time.
  - **Median**: The middle value (resistant to outliers).
  - **Std Dev**: Measures the consistency and jitter of the performance.
  - **Min/Max**: Identifies the best and worst-case scenarios.
- **Speedup Calculation**:

$$ \text{Speedup} = \frac{\text{Baseline Time}}{\text{JIT Time}} $$

$$ \text{Improvement %} = \left( \frac{\text{Baseline} - \text{JIT}}{\text{Baseline}} \right) \times 100 $$

---

## 💡 Enabling JIT for Testing

To see actual performance gains, you must be using Python 3.13 or newer. Python JIT is experimental and must be enabled via environment variables:

```bash
# Enable JIT in your current session
export PYTHON_JIT=1

# Verify activation
cortex jit-benchmark info

# Run benchmarks
cortex jit-benchmark run
```

---

## 📝 Technical Notes

- **JSON Export**: Standardized JSON format allows for cross-system performance audits and historical tracking.
- **Precision Safety**: The test suite (`tests/test_jit_benchmark.py`) uses `pytest.approx()` for all floating-point comparisons to handle micro-second timing drift across different hardware.
- **Modular Architecture**: The implementation uses a "routing" pattern in `cli.py` to keep the core CLI logic clean while supporting complex benchmarking subcommands.