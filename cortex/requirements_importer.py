"""
Requirements Importer - Parse and install dependencies from various package files.

Supports:
- requirements.txt (Python/pip)
- package.json (Node.js/npm)
- Gemfile (Ruby/bundler)
- Cargo.toml (Rust/cargo)
- go.mod (Go/go modules)
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class PackageManager(Enum):
    """Supported package managers."""
    PIP = "pip"
    NPM = "npm"
    BUNDLER = "bundler"
    CARGO = "cargo"
    GO = "go"


@dataclass
class Dependency:
    """Represents a single dependency."""
    name: str
    version: Optional[str] = None
    extras: List[str] = field(default_factory=list)
    markers: Optional[str] = None
    source: Optional[str] = None  # Original file this came from

    def __str__(self) -> str:
        if self.version:
            return f"{self.name}=={self.version}"
        return self.name


@dataclass
class ParseResult:
    """Result of parsing a requirements file."""
    dependencies: List[Dependency]
    dev_dependencies: List[Dependency]
    package_manager: PackageManager
    source_file: str
    errors: List[str] = field(default_factory=list)


class RequirementsParser:
    """Parse requirements.txt files (Python/pip)."""

    @staticmethod
    def parse(file_path: str) -> ParseResult:
        """Parse a requirements.txt file."""
        dependencies = []
        errors = []

        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.PIP,
                source_file=file_path,
                errors=[f"File not found: {file_path}"]
            )

        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Skip -r (recursive includes) and other flags for now
                if line.startswith('-'):
                    if line.startswith('-r ') or line.startswith('--requirement'):
                        errors.append(f"Line {line_num}: Recursive includes not supported: {line}")
                    continue

                try:
                    dep = RequirementsParser._parse_requirement_line(line)
                    dep.source = file_path
                    dependencies.append(dep)
                except ValueError as e:
                    errors.append(f"Line {line_num}: {e}")

        return ParseResult(
            dependencies=dependencies,
            dev_dependencies=[],
            package_manager=PackageManager.PIP,
            source_file=file_path,
            errors=errors
        )

    @staticmethod
    def _parse_requirement_line(line: str) -> Dependency:
        """Parse a single requirement line."""
        # Remove inline comments
        if ' #' in line:
            line = line.split(' #')[0].strip()

        # Handle environment markers (e.g., ; python_version >= "3.8")
        markers = None
        if ';' in line:
            line, markers = line.split(';', 1)
            line = line.strip()
            markers = markers.strip()

        # Handle extras (e.g., package[extra1,extra2])
        extras = []
        extras_match = re.match(r'^([a-zA-Z0-9_-]+)\[([^\]]+)\](.*)$', line)
        if extras_match:
            name = extras_match.group(1)
            extras = [e.strip() for e in extras_match.group(2).split(',')]
            remainder = extras_match.group(3)
        else:
            # Parse name and version specifier
            # Supports: ==, >=, <=, >, <, ~=, !=
            match = re.match(r'^([a-zA-Z0-9_.-]+)\s*(.*)?$', line)
            if not match:
                raise ValueError(f"Invalid requirement: {line}")
            name = match.group(1)
            remainder = match.group(2) or ''

        # Extract version from remainder
        version = None
        if remainder:
            # Handle exact version (==)
            if '==' in remainder:
                version = remainder.split('==')[1].strip()
            # For other specifiers, store the whole thing
            elif any(op in remainder for op in ['>=', '<=', '>', '<', '~=', '!=']):
                version = remainder.strip()

        return Dependency(
            name=name,
            version=version,
            extras=extras,
            markers=markers
        )


class PackageJsonParser:
    """Parse package.json files (Node.js/npm)."""

    @staticmethod
    def parse(file_path: str) -> ParseResult:
        """Parse a package.json file."""
        dependencies = []
        dev_dependencies = []
        errors = []

        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.NPM,
                source_file=file_path,
                errors=[f"File not found: {file_path}"]
            )

        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.NPM,
                source_file=file_path,
                errors=[f"Invalid JSON: {e}"]
            )

        # Parse dependencies
        if 'dependencies' in data:
            for name, version in data['dependencies'].items():
                dep = Dependency(
                    name=name,
                    version=PackageJsonParser._normalize_version(version),
                    source=file_path
                )
                dependencies.append(dep)

        # Parse devDependencies
        if 'devDependencies' in data:
            for name, version in data['devDependencies'].items():
                dep = Dependency(
                    name=name,
                    version=PackageJsonParser._normalize_version(version),
                    source=file_path
                )
                dev_dependencies.append(dep)

        return ParseResult(
            dependencies=dependencies,
            dev_dependencies=dev_dependencies,
            package_manager=PackageManager.NPM,
            source_file=file_path,
            errors=errors
        )

    @staticmethod
    def _normalize_version(version: str) -> str:
        """Normalize npm version specifier."""
        # Remove ^ and ~ prefixes for exact matching
        # Keep as-is for installation
        return version


class GemfileParser:
    """Parse Gemfile files (Ruby/bundler)."""

    @staticmethod
    def parse(file_path: str) -> ParseResult:
        """Parse a Gemfile."""
        dependencies = []
        dev_dependencies = []
        errors = []
        current_group = None

        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.BUNDLER,
                source_file=file_path,
                errors=[f"File not found: {file_path}"]
            )

        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Track groups
                group_match = re.match(r'^group\s+:(\w+)', line)
                if group_match:
                    current_group = group_match.group(1)
                    continue

                if line == 'end':
                    current_group = None
                    continue

                # Parse gem declarations
                gem_match = re.match(r"^gem\s+['\"]([^'\"]+)['\"](?:,\s*['\"]([^'\"]+)['\"])?", line)
                if gem_match:
                    name = gem_match.group(1)
                    version = gem_match.group(2)

                    dep = Dependency(
                        name=name,
                        version=version,
                        source=file_path
                    )

                    # Assign to dev or regular dependencies based on group
                    if current_group in ('development', 'test'):
                        dev_dependencies.append(dep)
                    else:
                        dependencies.append(dep)

        return ParseResult(
            dependencies=dependencies,
            dev_dependencies=dev_dependencies,
            package_manager=PackageManager.BUNDLER,
            source_file=file_path,
            errors=errors
        )


class CargoTomlParser:
    """Parse Cargo.toml files (Rust/cargo)."""

    @staticmethod
    def parse(file_path: str) -> ParseResult:
        """Parse a Cargo.toml file."""
        dependencies = []
        dev_dependencies = []
        errors = []

        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.CARGO,
                source_file=file_path,
                errors=[f"File not found: {file_path}"]
            )

        try:
            # Simple TOML parser for Cargo.toml
            content = path.read_text()

            # Parse [dependencies] section
            deps = CargoTomlParser._parse_section(content, 'dependencies')
            for name, version in deps.items():
                dependencies.append(Dependency(
                    name=name,
                    version=version,
                    source=file_path
                ))

            # Parse [dev-dependencies] section
            dev_deps = CargoTomlParser._parse_section(content, 'dev-dependencies')
            for name, version in dev_deps.items():
                dev_dependencies.append(Dependency(
                    name=name,
                    version=version,
                    source=file_path
                ))

        except Exception as e:
            errors.append(f"Error parsing Cargo.toml: {e}")

        return ParseResult(
            dependencies=dependencies,
            dev_dependencies=dev_dependencies,
            package_manager=PackageManager.CARGO,
            source_file=file_path,
            errors=errors
        )

    @staticmethod
    def _parse_section(content: str, section: str) -> Dict[str, str]:
        """Parse a TOML section for dependencies."""
        result = {}

        # Find the section
        section_pattern = rf'^\[{re.escape(section)}\]'
        section_match = re.search(section_pattern, content, re.MULTILINE)
        if not section_match:
            return result

        # Extract content until next section or end
        start = section_match.end()
        next_section = re.search(r'^\[', content[start:], re.MULTILINE)
        if next_section:
            section_content = content[start:start + next_section.start()]
        else:
            section_content = content[start:]

        # Parse key-value pairs
        for line in section_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Simple format: name = "version"
            simple_match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]+)"', line)
            if simple_match:
                result[simple_match.group(1)] = simple_match.group(2)
                continue

            # Complex format: name = { version = "x", features = [...] }
            complex_match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*\{.*version\s*=\s*"([^"]+)"', line)
            if complex_match:
                result[complex_match.group(1)] = complex_match.group(2)

        return result


class GoModParser:
    """Parse go.mod files (Go modules)."""

    @staticmethod
    def parse(file_path: str) -> ParseResult:
        """Parse a go.mod file."""
        dependencies = []
        errors = []

        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                dependencies=[],
                dev_dependencies=[],
                package_manager=PackageManager.GO,
                source_file=file_path,
                errors=[f"File not found: {file_path}"]
            )

        in_require_block = False

        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('//'):
                    continue

                # Track require blocks
                if line == 'require (':
                    in_require_block = True
                    continue

                if line == ')':
                    in_require_block = False
                    continue

                # Parse single-line require
                single_require = re.match(r'^require\s+(\S+)\s+(\S+)', line)
                if single_require:
                    dependencies.append(Dependency(
                        name=single_require.group(1),
                        version=single_require.group(2),
                        source=file_path
                    ))
                    continue

                # Parse require block entries
                if in_require_block:
                    # Format: module/path v1.2.3
                    parts = line.split()
                    if len(parts) >= 2:
                        # Skip indirect dependencies
                        if '// indirect' not in line:
                            dependencies.append(Dependency(
                                name=parts[0],
                                version=parts[1],
                                source=file_path
                            ))

        return ParseResult(
            dependencies=dependencies,
            dev_dependencies=[],
            package_manager=PackageManager.GO,
            source_file=file_path,
            errors=errors
        )


class RequirementsImporter:
    """Main class for importing and installing dependencies."""

    # Mapping of file names to parsers
    PARSERS = {
        'requirements.txt': RequirementsParser,
        'requirements-dev.txt': RequirementsParser,
        'requirements_dev.txt': RequirementsParser,
        'package.json': PackageJsonParser,
        'Gemfile': GemfileParser,
        'Cargo.toml': CargoTomlParser,
        'go.mod': GoModParser,
    }

    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.results: List[ParseResult] = []

    def detect_files(self, directory: str = '.') -> List[str]:
        """Detect supported requirements files in a directory."""
        detected = []
        dir_path = Path(directory)

        for filename in self.PARSERS.keys():
            file_path = dir_path / filename
            if file_path.exists():
                detected.append(str(file_path))

        return detected

    def parse_file(self, file_path: str) -> ParseResult:
        """Parse a single requirements file."""
        filename = Path(file_path).name

        # Find appropriate parser
        parser = None
        for pattern, parser_class in self.PARSERS.items():
            if filename == pattern or filename.startswith('requirements'):
                if filename.endswith('.txt'):
                    parser = RequirementsParser
                else:
                    parser = parser_class
                break
            elif filename == pattern:
                parser = parser_class
                break

        if parser is None:
            # Try to guess by extension/content
            if file_path.endswith('.txt'):
                parser = RequirementsParser
            elif file_path.endswith('.json'):
                parser = PackageJsonParser
            elif file_path.endswith('.toml'):
                parser = CargoTomlParser
            elif 'Gemfile' in file_path:
                parser = GemfileParser
            elif file_path.endswith('.mod'):
                parser = GoModParser
            else:
                return ParseResult(
                    dependencies=[],
                    dev_dependencies=[],
                    package_manager=PackageManager.PIP,
                    source_file=file_path,
                    errors=[f"Unknown file type: {file_path}"]
                )

        result = parser.parse(file_path)
        self.results.append(result)
        return result

    def parse_all(self, directory: str = '.') -> List[ParseResult]:
        """Parse all detected requirements files in a directory."""
        files = self.detect_files(directory)
        results = []

        for file_path in files:
            result = self.parse_file(file_path)
            results.append(result)

        return results

    def install(self, result: ParseResult, include_dev: bool = False) -> Tuple[bool, str]:
        """Install dependencies from a parse result."""
        if self.dry_run:
            deps = result.dependencies + (result.dev_dependencies if include_dev else [])
            return True, f"[DRY RUN] Would install {len(deps)} packages via {result.package_manager.value}"

        pm = result.package_manager
        deps = result.dependencies + (result.dev_dependencies if include_dev else [])

        if not deps:
            return True, "No dependencies to install"

        try:
            if pm == PackageManager.PIP:
                return self._install_pip(deps)
            elif pm == PackageManager.NPM:
                return self._install_npm(deps)
            elif pm == PackageManager.BUNDLER:
                return self._install_bundler(result.source_file)
            elif pm == PackageManager.CARGO:
                return self._install_cargo(result.source_file)
            elif pm == PackageManager.GO:
                return self._install_go(result.source_file)
            else:
                return False, f"Unsupported package manager: {pm}"
        except Exception as e:
            return False, str(e)

    def _install_pip(self, deps: List[Dependency]) -> Tuple[bool, str]:
        """Install Python packages via pip."""
        packages = []
        for dep in deps:
            if dep.version:
                packages.append(f"{dep.name}=={dep.version}" if not any(
                    op in dep.version for op in ['>=', '<=', '>', '<', '~=', '!=']
                ) else f"{dep.name}{dep.version}")
            else:
                packages.append(dep.name)

        cmd = [sys.executable, '-m', 'pip', 'install'] + packages
        if self.verbose:
            print(f"Running: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True, f"Installed {len(packages)} packages"
        return False, result.stderr

    def _install_npm(self, deps: List[Dependency]) -> Tuple[bool, str]:
        """Install Node.js packages via npm."""
        packages = [f"{dep.name}@{dep.version}" if dep.version else dep.name for dep in deps]

        cmd = ['npm', 'install'] + packages
        if self.verbose:
            print(f"Running: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return True, f"Installed {len(packages)} packages"
        return False, result.stderr

    def _install_bundler(self, gemfile_path: str) -> Tuple[bool, str]:
        """Install Ruby gems via bundler."""
        cmd = ['bundle', 'install']
        if self.verbose:
            print(f"Running: {' '.join(cmd)}")

        env = os.environ.copy()
        env['BUNDLE_GEMFILE'] = gemfile_path

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode == 0:
            return True, "Bundle install completed"
        return False, result.stderr

    def _install_cargo(self, cargo_toml_path: str) -> Tuple[bool, str]:
        """Install Rust crates via cargo."""
        # Navigate to directory containing Cargo.toml
        cargo_dir = str(Path(cargo_toml_path).parent)

        cmd = ['cargo', 'build']
        if self.verbose:
            print(f"Running: {' '.join(cmd)} in {cargo_dir}")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cargo_dir)
        if result.returncode == 0:
            return True, "Cargo build completed"
        return False, result.stderr

    def _install_go(self, go_mod_path: str) -> Tuple[bool, str]:
        """Install Go modules."""
        go_dir = str(Path(go_mod_path).parent)

        cmd = ['go', 'mod', 'download']
        if self.verbose:
            print(f"Running: {' '.join(cmd)} in {go_dir}")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=go_dir)
        if result.returncode == 0:
            return True, "Go modules downloaded"
        return False, result.stderr

    def summary(self) -> str:
        """Generate a summary of all parsed files."""
        lines = ["Requirements Import Summary", "=" * 40]

        for result in self.results:
            lines.append(f"\n{result.source_file} ({result.package_manager.value}):")
            lines.append(f"  Dependencies: {len(result.dependencies)}")
            lines.append(f"  Dev Dependencies: {len(result.dev_dependencies)}")
            if result.errors:
                lines.append(f"  Errors: {len(result.errors)}")
                for err in result.errors:
                    lines.append(f"    - {err}")

        return '\n'.join(lines)
