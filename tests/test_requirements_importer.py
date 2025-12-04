"""
Tests for the Requirements Importer module.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.requirements_importer import (
    CargoTomlParser,
    Dependency,
    GemfileParser,
    GoModParser,
    PackageJsonParser,
    PackageManager,
    ParseResult,
    RequirementsImporter,
    RequirementsParser,
)


class TestDependency:
    """Tests for the Dependency dataclass."""

    def test_dependency_str_with_version(self):
        dep = Dependency(name="flask", version="2.0.1")
        assert str(dep) == "flask==2.0.1"

    def test_dependency_str_without_version(self):
        dep = Dependency(name="flask")
        assert str(dep) == "flask"

    def test_dependency_with_extras(self):
        dep = Dependency(name="requests", version="2.28.0", extras=["security", "socks"])
        assert dep.extras == ["security", "socks"]

    def test_dependency_with_markers(self):
        dep = Dependency(name="pywin32", markers='sys_platform == "win32"')
        assert dep.markers == 'sys_platform == "win32"'


class TestRequirementsParser:
    """Tests for Python requirements.txt parser."""

    def test_parse_simple_requirements(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\nrequests\ndjango\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.PIP
        assert len(result.dependencies) == 3
        assert result.dependencies[0].name == "flask"
        assert result.dependencies[1].name == "requests"
        assert result.dependencies[2].name == "django"

    def test_parse_with_versions(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask==2.0.1\nrequests>=2.28.0\ndjango~=4.0\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 3
        assert result.dependencies[0].version == "2.0.1"
        assert result.dependencies[1].version == ">=2.28.0"
        assert result.dependencies[2].version == "~=4.0"

    def test_parse_with_comments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("# This is a comment\nflask==2.0.1\n# Another comment\nrequests\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2

    def test_parse_with_inline_comments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask==2.0.1 # web framework\nrequests # HTTP library\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "flask"
        assert result.dependencies[0].version == "2.0.1"

    def test_parse_with_extras(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("requests[security,socks]\nflask[async]\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "requests"
        assert result.dependencies[0].extras == ["security", "socks"]
        assert result.dependencies[1].extras == ["async"]

    def test_parse_with_markers(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('pywin32; sys_platform == "win32"\nuvloop; sys_platform != "win32"\n')
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert result.dependencies[0].markers == 'sys_platform == "win32"'

    def test_parse_empty_lines(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\n\n\nrequests\n\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2

    def test_parse_file_not_found(self):
        result = RequirementsParser.parse("/nonexistent/requirements.txt")

        assert len(result.dependencies) == 0
        assert len(result.errors) == 1
        assert "File not found" in result.errors[0]

    def test_parse_recursive_includes_warning(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\n-r dev-requirements.txt\nrequests\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert len(result.errors) == 1
        assert "Recursive includes not supported" in result.errors[0]


class TestPackageJsonParser:
    """Tests for Node.js package.json parser."""

    def test_parse_simple_package_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = {
                "name": "test-project",
                "dependencies": {
                    "express": "^4.18.0",
                    "lodash": "~4.17.21"
                }
            }
            json.dump(data, f)
            f.flush()

            result = PackageJsonParser.parse(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.NPM
        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "express"
        assert result.dependencies[0].version == "^4.18.0"

    def test_parse_with_dev_dependencies(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = {
                "dependencies": {
                    "express": "^4.18.0"
                },
                "devDependencies": {
                    "jest": "^29.0.0",
                    "eslint": "^8.0.0"
                }
            }
            json.dump(data, f)
            f.flush()

            result = PackageJsonParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 1
        assert len(result.dev_dependencies) == 2
        assert result.dev_dependencies[0].name == "jest"

    def test_parse_empty_package_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"name": "empty-project"}, f)
            f.flush()

            result = PackageJsonParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 0
        assert len(result.dev_dependencies) == 0
        assert len(result.errors) == 0

    def test_parse_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            f.flush()

            result = PackageJsonParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.errors) == 1
        assert "Invalid JSON" in result.errors[0]

    def test_parse_file_not_found(self):
        result = PackageJsonParser.parse("/nonexistent/package.json")

        assert len(result.errors) == 1
        assert "File not found" in result.errors[0]


class TestGemfileParser:
    """Tests for Ruby Gemfile parser."""

    def test_parse_simple_gemfile(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("gem 'rails', '7.0.0'\ngem 'pg'\ngem 'puma', '~> 5.0'\n")
            f.flush()

            result = GemfileParser.parse(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.BUNDLER
        assert len(result.dependencies) == 3
        assert result.dependencies[0].name == "rails"
        assert result.dependencies[0].version == "7.0.0"
        assert result.dependencies[1].name == "pg"
        assert result.dependencies[1].version is None

    def test_parse_with_groups(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            content = """
gem 'rails', '7.0.0'

group :development do
  gem 'rubocop'
end

group :test do
  gem 'rspec', '3.12.0'
end

gem 'pg'
"""
            f.write(content)
            f.flush()

            result = GemfileParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2  # rails, pg
        assert len(result.dev_dependencies) == 2  # rubocop, rspec

    def test_parse_with_comments(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("# This is a Gemfile\ngem 'rails'\n# Another gem\ngem 'pg'\n")
            f.flush()

            result = GemfileParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2

    def test_parse_double_quotes(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write('gem "rails", "7.0.0"\ngem "pg"\n')
            f.flush()

            result = GemfileParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "rails"

    def test_parse_file_not_found(self):
        result = GemfileParser.parse("/nonexistent/Gemfile")

        assert len(result.errors) == 1
        assert "File not found" in result.errors[0]


class TestCargoTomlParser:
    """Tests for Rust Cargo.toml parser."""

    def test_parse_simple_cargo_toml(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            content = """
[package]
name = "test-project"
version = "0.1.0"

[dependencies]
serde = "1.0"
tokio = "1.28"
"""
            f.write(content)
            f.flush()

            result = CargoTomlParser.parse(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.CARGO
        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "serde"
        assert result.dependencies[0].version == "1.0"

    def test_parse_with_dev_dependencies(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            content = """
[dependencies]
serde = "1.0"

[dev-dependencies]
criterion = "0.5"
"""
            f.write(content)
            f.flush()

            result = CargoTomlParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 1
        assert len(result.dev_dependencies) == 1
        assert result.dev_dependencies[0].name == "criterion"

    def test_parse_complex_dependency(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            content = """
[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "1.28"
"""
            f.write(content)
            f.flush()

            result = CargoTomlParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "serde"
        assert result.dependencies[0].version == "1.0"

    def test_parse_no_dependencies(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            content = """
[package]
name = "test"
version = "0.1.0"
"""
            f.write(content)
            f.flush()

            result = CargoTomlParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 0
        assert len(result.errors) == 0

    def test_parse_file_not_found(self):
        result = CargoTomlParser.parse("/nonexistent/Cargo.toml")

        assert len(result.errors) == 1
        assert "File not found" in result.errors[0]


class TestGoModParser:
    """Tests for Go go.mod parser."""

    def test_parse_simple_go_mod(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mod', delete=False) as f:
            content = """module example.com/myproject

go 1.21

require github.com/gin-gonic/gin v1.9.1
require github.com/spf13/cobra v1.7.0
"""
            f.write(content)
            f.flush()

            result = GoModParser.parse(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.GO
        assert len(result.dependencies) == 2
        assert result.dependencies[0].name == "github.com/gin-gonic/gin"
        assert result.dependencies[0].version == "v1.9.1"

    def test_parse_require_block(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mod', delete=False) as f:
            content = """module example.com/myproject

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/spf13/cobra v1.7.0
    github.com/stretchr/testify v1.8.4
)
"""
            f.write(content)
            f.flush()

            result = GoModParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 3

    def test_parse_skip_indirect(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mod', delete=False) as f:
            content = """module example.com/myproject

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    golang.org/x/sys v0.8.0 // indirect
)
"""
            f.write(content)
            f.flush()

            result = GoModParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 1
        assert result.dependencies[0].name == "github.com/gin-gonic/gin"

    def test_parse_with_comments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mod', delete=False) as f:
            content = """module example.com/myproject

// This is a comment
go 1.21

require github.com/gin-gonic/gin v1.9.1
"""
            f.write(content)
            f.flush()

            result = GoModParser.parse(f.name)

        os.unlink(f.name)

        assert len(result.dependencies) == 1

    def test_parse_file_not_found(self):
        result = GoModParser.parse("/nonexistent/go.mod")

        assert len(result.errors) == 1
        assert "File not found" in result.errors[0]


class TestRequirementsImporter:
    """Tests for the main RequirementsImporter class."""

    def test_detect_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "requirements.txt").write_text("flask\n")
            (Path(tmpdir) / "package.json").write_text('{"dependencies":{}}')

            importer = RequirementsImporter()
            detected = importer.detect_files(tmpdir)

        assert len(detected) == 2
        assert any("requirements.txt" in f for f in detected)
        assert any("package.json" in f for f in detected)

    def test_detect_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            importer = RequirementsImporter()
            detected = importer.detect_files(tmpdir)

        assert len(detected) == 0

    def test_parse_file_auto_detect_txt(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\nrequests\n")
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.PIP
        assert len(result.dependencies) == 2

    def test_parse_file_auto_detect_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"dependencies": {"express": "^4.0.0"}}, f)
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)

        os.unlink(f.name)

        assert result.package_manager == PackageManager.NPM

    def test_parse_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").write_text("flask\ndjango\n")
            (Path(tmpdir) / "package.json").write_text(
                '{"dependencies":{"express":"^4.0.0"}}'
            )

            importer = RequirementsImporter()
            results = importer.parse_all(tmpdir)

        assert len(results) == 2

    def test_dry_run_install(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\nrequests\n")
            f.flush()

            importer = RequirementsImporter(dry_run=True)
            result = importer.parse_file(f.name)
            success, message = importer.install(result)

        os.unlink(f.name)

        assert success
        assert "[DRY RUN]" in message
        assert "2 packages" in message

    def test_summary(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\nrequests\n")
            f.flush()

            importer = RequirementsImporter()
            importer.parse_file(f.name)
            summary = importer.summary()

        os.unlink(f.name)

        assert "Requirements Import Summary" in summary
        assert "Dependencies: 2" in summary

    @patch('cortex.requirements_importer.subprocess.run')
    def test_install_pip(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask==2.0.1\nrequests\n")
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)
            success, message = importer.install(result)

        os.unlink(f.name)

        assert success
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'pip' in ' '.join(call_args)
        assert 'install' in call_args

    @patch('cortex.requirements_importer.subprocess.run')
    def test_install_npm(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"dependencies": {"express": "^4.0.0"}}, f)
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)
            success, message = importer.install(result)

        os.unlink(f.name)

        assert success
        mock_run.assert_called_once()

    @patch('cortex.requirements_importer.subprocess.run')
    def test_install_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Installation failed"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("nonexistent-package-12345\n")
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)
            success, message = importer.install(result)

        os.unlink(f.name)

        assert not success
        assert "Installation failed" in message

    def test_install_empty_dependencies(self):
        importer = RequirementsImporter()
        result = ParseResult(
            dependencies=[],
            dev_dependencies=[],
            package_manager=PackageManager.PIP,
            source_file="test.txt"
        )

        success, message = importer.install(result)

        assert success
        assert "No dependencies" in message

    def test_install_with_dev_dependencies(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            data = {
                "dependencies": {"express": "^4.0.0"},
                "devDependencies": {"jest": "^29.0.0"}
            }
            json.dump(data, f)
            f.flush()

            importer = RequirementsImporter(dry_run=True)
            result = importer.parse_file(f.name)
            success, message = importer.install(result, include_dev=True)

        os.unlink(f.name)

        assert success
        assert "2 packages" in message  # Both express and jest


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_unknown_file_type(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False) as f:
            f.write("some content")
            f.flush()

            importer = RequirementsImporter()
            result = importer.parse_file(f.name)

        os.unlink(f.name)

        assert "Unknown file type" in result.errors[0]

    def test_requirements_with_hashes(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask==2.0.1 --hash=sha256:abc123\n")
            f.flush()

            result = RequirementsParser.parse(f.name)

        os.unlink(f.name)

        # Should still parse the package (hash is ignored for simplicity)
        assert len(result.dependencies) == 1

    def test_gemfile_complex_syntax(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            content = """
source 'https://rubygems.org'

gem 'rails', '7.0.0'
gem 'pg', '>= 0.18', '< 2.0'
"""
            f.write(content)
            f.flush()

            result = GemfileParser.parse(f.name)

        os.unlink(f.name)

        # Should parse both gems
        assert len(result.dependencies) == 2

    def test_verbose_mode(self, capsys):
        importer = RequirementsImporter(verbose=True, dry_run=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("flask\n")
            f.flush()

            result = importer.parse_file(f.name)
            importer.install(result)

        os.unlink(f.name)
        # Verbose mode should not crash, dry run prevents actual output


class TestIntegration:
    """Integration tests with real file structures."""

    def test_full_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a realistic project structure
            (Path(tmpdir) / "requirements.txt").write_text(
                "flask==2.0.1\nrequests>=2.28.0\n"
            )
            (Path(tmpdir) / "package.json").write_text(json.dumps({
                "name": "test-project",
                "dependencies": {"express": "^4.18.0"},
                "devDependencies": {"jest": "^29.0.0"}
            }))

            importer = RequirementsImporter(dry_run=True)

            # Detect files
            files = importer.detect_files(tmpdir)
            assert len(files) == 2

            # Parse all
            results = importer.parse_all(tmpdir)
            assert len(results) == 2

            # Get summary
            summary = importer.summary()
            assert "pip" in summary.lower()
            assert "npm" in summary.lower()

            # Dry run install
            for result in results:
                success, message = importer.install(result)
                assert success
                assert "[DRY RUN]" in message
