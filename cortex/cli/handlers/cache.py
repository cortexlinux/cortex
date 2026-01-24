"""Cache command handler for Cortex CLI."""

import argparse


class CacheHandler:
    """Handler for cache command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def cache(self, args: argparse.Namespace) -> int:
        """Handle cache command."""
        from cortex.cache import handle_cache
        return handle_cache(args)


def add_cache_parser(subparsers) -> argparse.ArgumentParser:
    """Add cache parser to subparsers."""
    cache_parser = subparsers.add_parser("cache", help="Cache operations")
    cache_subs = cache_parser.add_subparsers(dest="cache_action", help="Cache actions")

    cache_subs.add_parser("stats", help="Show cache statistics")
    cache_subs.add_parser("clear", help="Clear all cache")
    cache_subs.add_parser("invalidate", help="Invalidate specific cache entries")

    return cache_parser
