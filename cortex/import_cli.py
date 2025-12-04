"""
CLI commands for importing dependencies from requirements files.

Usage:
    cortex import requirements.txt
    cortex import package.json
    cortex import --all
    cortex import --detect
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from cortex.requirements_importer import (
    RequirementsImporter,
    PackageManager,
)


def create_import_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the import subcommand parser."""
    import_parser = subparsers.add_parser(
        'import',
        help='Import dependencies from requirements files',
        description='Parse and install dependencies from requirements.txt, package.json, '
                    'Gemfile, Cargo.toml, or go.mod files.'
    )

    import_parser.add_argument(
        'file',
        nargs='?',
        help='Requirements file to import (e.g., requirements.txt, package.json)'
    )

    import_parser.add_argument(
        '--all', '-a',
        action='store_true',
        dest='import_all',
        help='Import from all detected requirements files'
    )

    import_parser.add_argument(
        '--detect', '-d',
        action='store_true',
        help='Detect requirements files without importing'
    )

    import_parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be installed without actually installing'
    )

    import_parser.add_argument(
        '--dev',
        action='store_true',
        help='Include dev dependencies'
    )

    import_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    import_parser.add_argument(
        '--dir',
        type=str,
        default='.',
        help='Directory to search for requirements files (default: current directory)'
    )

    import_parser.set_defaults(func=handle_import)

    return import_parser


def handle_import(args: argparse.Namespace) -> int:
    """Handle the import command."""
    importer = RequirementsImporter(
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    # Detect mode - just list found files
    if args.detect:
        files = importer.detect_files(args.dir)
        if files:
            print("Detected requirements files:")
            for f in files:
                print(f"  - {f}")
            return 0
        else:
            print("No requirements files detected.")
            return 0

    # Import all mode
    if args.import_all:
        files = importer.detect_files(args.dir)
        if not files:
            print("No requirements files detected.")
            return 1

        print(f"Found {len(files)} requirements file(s)")
        results = []
        for file_path in files:
            result = importer.parse_file(file_path)
            results.append(result)

            total_deps = len(result.dependencies)
            if args.dev:
                total_deps += len(result.dev_dependencies)

            print(f"\n{file_path} ({result.package_manager.value}):")
            print(f"  Dependencies: {len(result.dependencies)}")
            if result.dev_dependencies:
                print(f"  Dev dependencies: {len(result.dev_dependencies)}")

            if result.errors:
                print(f"  Warnings: {len(result.errors)}")
                for err in result.errors:
                    print(f"    - {err}")

            # Install
            success, message = importer.install(result, include_dev=args.dev)
            status = "OK" if success else "FAILED"
            print(f"  Install: [{status}] {message}")

        return 0

    # Single file mode
    if args.file:
        file_path = args.file
        if not Path(file_path).exists():
            print(f"Error: File not found: {file_path}")
            return 1

        result = importer.parse_file(file_path)

        print(f"\nParsing {file_path} ({result.package_manager.value})...")

        if result.errors:
            print("\nWarnings:")
            for err in result.errors:
                print(f"  - {err}")

        print(f"\nDependencies ({len(result.dependencies)}):")
        for dep in result.dependencies:
            version_str = f" ({dep.version})" if dep.version else ""
            print(f"  - {dep.name}{version_str}")

        if result.dev_dependencies:
            print(f"\nDev dependencies ({len(result.dev_dependencies)}):")
            for dep in result.dev_dependencies:
                version_str = f" ({dep.version})" if dep.version else ""
                print(f"  - {dep.name}{version_str}")

        # Install
        print("\nInstalling...")
        success, message = importer.install(result, include_dev=args.dev)

        if success:
            print(f"Success: {message}")
            return 0
        else:
            print(f"Failed: {message}")
            return 1

    # No file specified
    print("Error: Please specify a file or use --all/--detect")
    print("\nUsage:")
    print("  cortex import requirements.txt")
    print("  cortex import package.json")
    print("  cortex import --all")
    print("  cortex import --detect")
    return 1


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for standalone CLI."""
    parser = argparse.ArgumentParser(
        prog='cortex-import',
        description='Import dependencies from requirements files'
    )

    # Create a temporary subparsers for standalone use
    subparsers = parser.add_subparsers(dest='command')
    create_import_parser(subparsers)

    # Also support direct usage without 'import' subcommand
    parser.add_argument(
        'file',
        nargs='?',
        help='Requirements file to import'
    )
    parser.add_argument('--all', '-a', action='store_true', dest='import_all')
    parser.add_argument('--detect', '-d', action='store_true')
    parser.add_argument('--dry-run', '-n', action='store_true')
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--dir', type=str, default='.')
    parser.set_defaults(func=handle_import)

    parsed_args = parser.parse_args(args)

    if hasattr(parsed_args, 'func'):
        return parsed_args.func(parsed_args)

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
