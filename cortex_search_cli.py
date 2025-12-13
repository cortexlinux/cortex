#!/usr/bin/env python3
"""
CLI for cortex smart package search.

Usage:
    cortex search "web server"
    cortex search "postgress" --category database
    cortex search-history
    cortex search-history --clear
"""

import sys
import argparse
from pathlib import Path

from smart_search import (
    SmartPackageSearch,
    PackageCategory,
    format_search_results
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='cortex search',
        description='Smart package search with fuzzy matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex search "web server"
  cortex search "postgress"
  cortex search "database" --category database
  cortex search "nginx" --limit 5
  cortex search-history
  cortex search-history --clear

Categories:
  web_server, database, development, language, container,
  editor, security, network, monitoring, compression,
  version_control, media, system, cloud
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search for packages')
    search_parser.add_argument('query', type=str, help='Search query (can include typos)')
    search_parser.add_argument(
        '--category',
        type=str,
        choices=[cat.name.lower() for cat in PackageCategory],
        help='Filter by package category'
    )
    search_parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum number of results (default: 10)'
    )

    # History command
    history_parser = subparsers.add_parser('history', help='View search history')
    history_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Number of history entries to show (default: 20)'
    )
    history_parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear search history'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize search
    search = SmartPackageSearch()

    try:
        if args.command == 'search':
            # Convert category string to enum
            category = None
            if args.category:
                category = PackageCategory[args.category.upper()]

            # Perform search
            results, suggestions = search.search(
                args.query,
                category=category,
                limit=args.limit
            )

            # Format and display results
            output = format_search_results(results, suggestions)
            print(output)

            return 0

        elif args.command == 'history':
            if args.clear:
                # Clear history
                search.clear_history()
                print("✓ Search history cleared")
                return 0
            else:
                # Display history
                history = search.get_history(limit=args.limit)

                if not history:
                    print("No search history found.")
                    return 0

                print("\nSearch History:")
                print("=" * 80)
                print(f"{'Timestamp':<20} {'Query':<30} {'Results':<10} {'Top Result':<20}")
                print("-" * 80)

                for entry in history:
                    timestamp = entry.timestamp[:19].replace('T', ' ')
                    query = entry.query[:28] + '..' if len(entry.query) > 30 else entry.query
                    top_result = entry.top_result or "N/A"
                    top_result = top_result[:18] + '..' if len(top_result) > 20 else top_result

                    print(f"{timestamp:<20} {query:<30} {entry.results_count:<10} {top_result:<20}")

                print("=" * 80)
                return 0

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
