"""Benchmark command handler for Cortex CLI."""

import argparse


class BenchmarkHandler:
    """Handler for benchmark command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def benchmark(self, verbose: bool = False) -> int:
        """Run AI performance benchmark."""
        from cortex.benchmark import run_benchmark
        return run_benchmark(verbose=verbose)


def add_benchmark_parser(subparsers) -> argparse.ArgumentParser:
    """Add benchmark parser to subparsers."""
    benchmark_parser = subparsers.add_parser("benchmark", help="Run AI performance benchmark")
    benchmark_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return benchmark_parser
