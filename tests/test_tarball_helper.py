"""
Unit tests for cortex/tarball_helper.py - Tarball/Source Build Helper.
Tests the TarballHelper class used by 'cortex tarball' commands.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.tarball_helper import (
    BuildAnalysis,
    BuildSystem,
    Dependency,
    ManualInstall,
    TarballHelper,
    run_analyze_command,
    run_cleanup_command,
    run_install_deps_command,
    run_list_command,
    run_track_command,
)


class TestBuildSystemEnum:
    """Test the BuildSystem enum values."""

    def test_all_build_systems_exist(self):
        assert BuildSystem.AUTOTOOLS.value == "autotools"
        assert BuildSystem.CMAKE.value == "cmake"
        assert BuildSystem.MESON.value == "meson"
        assert BuildSystem.MAKE.value == "make"
        assert BuildSystem.PYTHON.value == "python"
        assert BuildSystem.UNKNOWN.value == "unknown"


class TestDependencyDataclass:
    """Test the Dependency dataclass."""

    def test_basic_creation(self):
        dep = Dependency(name="zlib", dep_type="library")
        assert dep.name == "zlib"
        assert dep.dep_type == "library"
        assert dep.apt_package is None
        assert dep.required is True
        assert dep.found is False

    def test_full_creation(self):
        dep = Dependency(
            name="zlib.h",
            dep_type="header",
            apt_package="zlib1g-dev",
            required=True,
            found=True,
        )
        assert dep.apt_package == "zlib1g-dev"
        assert dep.found is True


class TestManualInstallDataclass:
    """Test the ManualInstall dataclass."""

    def test_basic_creation(self):
        install = ManualInstall(
            name="myapp",
            source_dir="/tmp/myapp-1.0",
            installed_at="2024-01-01T00:00:00",
        )
        assert install.name == "myapp"
        assert install.packages_installed == []
        assert install.prefix == "/usr/local"


class TestTarballHelperInit:
    """Test TarballHelper initialization."""

    def test_init_creates_history_dir(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            assert helper.history_file.parent.exists()


class TestDetectBuildSystem:
    """Test the detect_build_system method."""

    def test_detect_cmake(self, tmp_path):
        (tmp_path / "CMakeLists.txt").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.CMAKE

    def test_detect_meson(self, tmp_path):
        (tmp_path / "meson.build").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.MESON

    def test_detect_autotools_configure_ac(self, tmp_path):
        (tmp_path / "configure.ac").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.AUTOTOOLS

    def test_detect_autotools_configure(self, tmp_path):
        (tmp_path / "configure").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.AUTOTOOLS

    def test_detect_python_setup_py(self, tmp_path):
        (tmp_path / "setup.py").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.PYTHON

    def test_detect_python_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.PYTHON

    def test_detect_make(self, tmp_path):
        (tmp_path / "Makefile").touch()
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.MAKE

    def test_detect_unknown(self, tmp_path):
        helper = TarballHelper()
        assert helper.detect_build_system(tmp_path) == BuildSystem.UNKNOWN

    def test_detect_invalid_path(self, tmp_path):
        helper = TarballHelper()
        with pytest.raises(ValueError, match="Not a directory"):
            helper.detect_build_system(tmp_path / "nonexistent")


class TestAnalyzeCMake:
    """Test CMake analysis."""

    def test_analyze_cmake_find_package(self, tmp_path):
        cmake_content = """
cmake_minimum_required(VERSION 3.10)
project(MyProject)
find_package(OpenSSL REQUIRED)
find_package(ZLIB)
"""
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)

        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.CMAKE
        pkg_names = [d.name for d in analysis.dependencies]
        assert "openssl" in pkg_names
        assert "zlib" in pkg_names

    def test_analyze_cmake_pkg_check_modules(self, tmp_path):
        cmake_content = """
pkg_check_modules(GLIB REQUIRED glib-2.0)
"""
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)

        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        pkg_names = [d.name for d in analysis.dependencies]
        assert "glib-2.0" in pkg_names


class TestAnalyzeAutotools:
    """Test Autotools analysis."""

    def test_analyze_autotools_check_headers(self, tmp_path):
        configure_content = """
AC_CHECK_HEADERS([zlib.h openssl/ssl.h])
"""
        (tmp_path / "configure.ac").write_text(configure_content)

        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.AUTOTOOLS
        dep_names = [d.name for d in analysis.dependencies]
        assert "zlib.h" in dep_names

    def test_analyze_autotools_pkg_check_modules(self, tmp_path):
        configure_content = """
PKG_CHECK_MODULES([DEPS], [libcurl >= 7.0])
"""
        (tmp_path / "configure.ac").write_text(configure_content)

        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        pkg_names = [d.name for d in analysis.dependencies]
        assert "libcurl" in pkg_names


class TestAnalyzeMeson:
    """Test Meson analysis."""

    def test_analyze_meson_dependency(self, tmp_path):
        meson_content = """
project('myproject', 'c')
dep_glib = dependency('glib-2.0')
dep_gtk = dependency('gtk+-3.0')
"""
        (tmp_path / "meson.build").write_text(meson_content)

        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.MESON
        pkg_names = [d.name for d in analysis.dependencies]
        assert "glib-2.0" in pkg_names
        assert "gtk+-3.0" in pkg_names


class TestGenerateBuildCommands:
    """Test build command generation."""

    def test_cmake_commands(self, tmp_path):
        (tmp_path / "CMakeLists.txt").touch()
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "cmake .." in analysis.build_commands
        assert "make -j$(nproc)" in analysis.build_commands

    def test_autotools_commands(self, tmp_path):
        (tmp_path / "configure").touch()
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "./configure" in analysis.build_commands
        assert "make -j$(nproc)" in analysis.build_commands

    def test_meson_commands(self, tmp_path):
        (tmp_path / "meson.build").touch()
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "meson setup build" in analysis.build_commands
        assert "ninja -C build" in analysis.build_commands


class TestInstallDependencies:
    """Test dependency installation."""

    def test_install_deps_dry_run(self):
        helper = TarballHelper()
        result = helper.install_dependencies(["zlib1g-dev", "libssl-dev"], dry_run=True)
        assert result is True

    def test_install_deps_empty_list(self):
        helper = TarballHelper()
        result = helper.install_dependencies([])
        assert result is True

    def test_install_deps_success(self):
        helper = TarballHelper()
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            result = helper.install_dependencies(["zlib1g-dev"])
        assert result is True

    def test_install_deps_failure(self):
        helper = TarballHelper()
        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            result = helper.install_dependencies(["nonexistent-pkg"])
        assert result is False


class TestFindAlternative:
    """Test finding packaged alternatives."""

    def test_find_alternative_exact_match(self):
        helper = TarballHelper()
        mock_result = MagicMock(returncode=0, stdout="nginx - small, powerful web server")
        with patch("subprocess.run", return_value=mock_result):
            result = helper.find_alternative("nginx")
        assert result == "nginx"

    def test_find_alternative_not_found(self):
        helper = TarballHelper()
        mock_result = MagicMock(returncode=0, stdout="")
        with patch("subprocess.run", return_value=mock_result):
            result = helper.find_alternative("nonexistent")
        assert result is None


class TestInstallationTracking:
    """Test installation tracking functionality."""

    def test_track_installation(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
                packages_installed=["libfoo-dev"],
            )
            helper.track_installation(install)

            # Verify saved
            installations = helper.list_installations()
            assert len(installations) == 1
            assert installations[0].name == "myapp"

    def test_list_empty_installations(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            installations = helper.list_installations()
            assert installations == []

    def test_cleanup_installation(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
            )
            helper.track_installation(install)

            # Cleanup
            result = helper.cleanup_installation("myapp", dry_run=True)
            assert result is True

    def test_cleanup_not_found(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            result = helper.cleanup_installation("nonexistent", dry_run=True)
            assert result is False


class TestCheckInstalled:
    """Test checking if dependencies are installed."""

    def test_check_tool_found(self, tmp_path):
        (tmp_path / "CMakeLists.txt").write_text("project(test)")
        helper = TarballHelper()

        with patch("shutil.which", return_value="/usr/bin/cmake"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                analysis = helper.analyze(tmp_path)

        cmake_dep = next((d for d in analysis.dependencies if d.name == "cmake"), None)
        assert cmake_dep is not None
        assert cmake_dep.found is True

    def test_check_pkg_config(self, tmp_path):
        (tmp_path / "meson.build").write_text("dependency('glib-2.0')")
        helper = TarballHelper()

        with patch("shutil.which", return_value=None):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="install ok installed")
                analysis = helper.analyze(tmp_path)

        # Check that analysis completed without error
        assert analysis.build_system == BuildSystem.MESON


class TestRunCommands:
    """Test the run_* command functions."""

    def test_run_analyze_command(self, tmp_path):
        (tmp_path / "CMakeLists.txt").write_text("project(test)")
        with patch("shutil.which", return_value=None):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                run_analyze_command(str(tmp_path))

    def test_run_list_command(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            run_list_command()

    def test_run_track_command(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            run_track_command("myapp", "/tmp/source", ["pkg1", "pkg2"])

    def test_run_cleanup_command_dry_run(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            # First track something
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
            )
            helper.track_installation(install)

            # Then cleanup
            run_cleanup_command("myapp", dry_run=True)

    def test_run_install_deps_command(self, tmp_path):
        (tmp_path / "CMakeLists.txt").write_text("project(test)")
        with patch("shutil.which", return_value="/usr/bin/cmake"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="install ok installed")
                run_install_deps_command(str(tmp_path), dry_run=True)


class TestHeaderPackageMappings:
    """Test header to package mappings."""

    def test_common_headers_mapped(self):
        helper = TarballHelper()
        assert helper.HEADER_PACKAGES["zlib.h"] == "zlib1g-dev"
        assert helper.HEADER_PACKAGES["openssl/ssl.h"] == "libssl-dev"
        assert helper.HEADER_PACKAGES["curl/curl.h"] == "libcurl4-openssl-dev"

    def test_pkgconfig_packages_mapped(self):
        helper = TarballHelper()
        assert helper.PKGCONFIG_PACKAGES["openssl"] == "libssl-dev"
        assert helper.PKGCONFIG_PACKAGES["glib-2.0"] == "libglib2.0-dev"


class TestAnalyzePython:
    """Test Python build system analysis."""

    def test_analyze_python_setup_py(self, tmp_path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.PYTHON
        dep_names = [d.name for d in analysis.dependencies]
        assert "python3-dev" in dep_names
        assert "pip" in dep_names

    def test_analyze_python_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.PYTHON
        assert "pip install ." in analysis.build_commands


class TestAnalyzeCMakeAdvanced:
    """Test advanced CMake analysis scenarios."""

    def test_analyze_cmake_check_include_file(self, tmp_path):
        cmake_content = """
cmake_minimum_required(VERSION 3.10)
CHECK_INCLUDE_FILE("zlib.h" HAVE_ZLIB)
CHECK_INCLUDE_FILE('pthread.h' HAVE_PTHREAD)
"""
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        dep_names = [d.name for d in analysis.dependencies]
        assert "zlib.h" in dep_names
        assert "pthread.h" in dep_names

    def test_analyze_cmake_empty_file(self, tmp_path):
        # CMakeLists.txt exists but is empty - should still add cmake as tool
        (tmp_path / "CMakeLists.txt").write_text("")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.CMAKE
        dep_names = [d.name for d in analysis.dependencies]
        assert "cmake" in dep_names


class TestAnalyzeAutotoolsAdvanced:
    """Test advanced Autotools analysis scenarios."""

    def test_analyze_autotools_ac_check_lib(self, tmp_path):
        configure_content = """
AC_CHECK_LIB([z], [deflate])
AC_CHECK_LIB(crypto, EVP_EncryptInit)
"""
        (tmp_path / "configure.ac").write_text(configure_content)
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        dep_names = [d.name for d in analysis.dependencies]
        assert "z" in dep_names
        assert "crypto" in dep_names

    def test_analyze_autotools_configure_in(self, tmp_path):
        # Test configure.in fallback
        (tmp_path / "configure.in").write_text("AC_CHECK_HEADERS([stdio.h])")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.AUTOTOOLS

    def test_analyze_autotools_no_config_files(self, tmp_path):
        # Empty dir - analysis returns early
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        helper = TarballHelper()
        # Call _analyze_autotools directly on empty dir
        analysis = BuildAnalysis(build_system=BuildSystem.AUTOTOOLS, source_dir=subdir)
        helper._analyze_autotools(subdir, analysis)
        # Should have no dependencies (early return)
        assert len(analysis.dependencies) == 0


class TestAnalyzeMesonAdvanced:
    """Test advanced Meson analysis scenarios."""

    def test_analyze_meson_empty_file(self, tmp_path):
        (tmp_path / "meson.build").write_text("")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.MESON
        # Should still have meson and ninja as tools
        dep_names = [d.name for d in analysis.dependencies]
        assert "meson" in dep_names
        assert "ninja" in dep_names


class TestGenerateBuildCommandsAdvanced:
    """Test build command generation for all systems."""

    def test_python_commands(self, tmp_path):
        (tmp_path / "setup.py").touch()
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "pip install ." in analysis.build_commands

    def test_make_commands(self, tmp_path):
        (tmp_path / "Makefile").touch()
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "make -j$(nproc)" in analysis.build_commands
        assert "sudo make install" in analysis.build_commands

    def test_unknown_commands(self, tmp_path):
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert analysis.build_system == BuildSystem.UNKNOWN
        assert "# Unable to determine build commands" in analysis.build_commands

    def test_autotools_needs_autoreconf(self, tmp_path):
        # Only configure.ac, no configure script
        (tmp_path / "configure.ac").write_text("AC_INIT([test], [1.0])")
        helper = TarballHelper()
        with patch.object(helper, "_check_installed"):
            analysis = helper.analyze(tmp_path)

        assert "autoreconf -fi" in analysis.build_commands


class TestFindAlternativeAdvanced:
    """Test find_alternative with lib prefix fallback."""

    def test_find_alternative_lib_prefix_dev(self):
        helper = TarballHelper()

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if "^libfoo" in cmd:
                result.stdout = "libfoo-dev - Foo library development files\nlibfoo1 - Foo library"
            else:
                result.stdout = ""
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = helper.find_alternative("foo")

        assert result == "libfoo-dev"

    def test_find_alternative_lib_prefix_no_dev(self):
        helper = TarballHelper()

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if "^libbar" in cmd:
                result.stdout = "libbar1 - Bar library"
            else:
                result.stdout = ""
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = helper.find_alternative("bar")

        assert result == "libbar1"


class TestCleanupAdvanced:
    """Test cleanup with packages."""

    def test_cleanup_dry_run_with_packages(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
                packages_installed=["libfoo-dev", "libbar-dev"],
            )
            helper.track_installation(install)

            result = helper.cleanup_installation("myapp", dry_run=True)
            assert result is True
            # Installation should still exist (dry run)
            installations = helper.list_installations()
            assert len(installations) == 1

    def test_cleanup_actual_no_packages(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
            )
            helper.track_installation(install)

            result = helper.cleanup_installation("myapp", dry_run=False)
            assert result is True
            # Installation should be removed
            installations = helper.list_installations()
            assert len(installations) == 0

    def test_cleanup_actual_with_packages_decline(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
                packages_installed=["libfoo-dev"],
            )
            helper.track_installation(install)

            with patch("cortex.tarball_helper.Confirm.ask", return_value=False):
                result = helper.cleanup_installation("myapp", dry_run=False)
            assert result is True

    def test_cleanup_actual_with_packages_confirm(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
                packages_installed=["libfoo-dev"],
            )
            helper.track_installation(install)

            with patch("cortex.tarball_helper.Confirm.ask", return_value=True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    result = helper.cleanup_installation("myapp", dry_run=False)

            assert result is True
            mock_run.assert_called_once()


class TestLoadHistoryErrors:
    """Test _load_history error handling."""

    def test_load_history_corrupt_json(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            # Write corrupt JSON
            helper.history_file.write_text("{invalid json}")
            # Should return empty dict
            result = helper._load_history()
            assert result == {}

    def test_load_history_valid_json(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            helper.history_file.write_text('{"app": {"source_dir": "/tmp"}}')
            result = helper._load_history()
            assert "app" in result


class TestRunCommandsAdvanced:
    """Test run_* command functions with more scenarios."""

    def test_run_analyze_command_not_found(self, tmp_path):
        # Non-existent directory
        run_analyze_command(str(tmp_path / "nonexistent"))

    def test_run_analyze_command_with_alternative(self, tmp_path):
        (tmp_path / "nginx-1.0").mkdir()
        (tmp_path / "nginx-1.0" / "CMakeLists.txt").write_text("project(nginx)")

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if "apt-cache" in cmd:
                result.stdout = "nginx - web server"
            else:
                result.stdout = ""
            result.returncode = 0
            return result

        with patch("shutil.which", return_value=None):
            with patch("subprocess.run", side_effect=mock_run):
                run_analyze_command(str(tmp_path / "nginx-1.0"))

    def test_run_install_deps_command_not_found(self, tmp_path):
        run_install_deps_command(str(tmp_path / "nonexistent"))

    def test_run_install_deps_command_with_missing_deps(self, tmp_path):
        cmake_content = "find_package(OpenSSL REQUIRED)"
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)

        with patch("shutil.which", return_value=None):
            with patch("subprocess.run") as mock_run:
                # First call: dpkg-query returns not installed
                # Second call: apt install
                mock_run.return_value = MagicMock(returncode=1, stdout="")
                run_install_deps_command(str(tmp_path), dry_run=True)

    def test_run_list_command_with_installations(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            helper = TarballHelper()
            install = ManualInstall(
                name="myapp",
                source_dir="/tmp/myapp",
                installed_at="2024-01-01",
                packages_installed=["pkg1", "pkg2"],
            )
            helper.track_installation(install)

            run_list_command()

    def test_run_cleanup_command_not_found(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            run_cleanup_command("nonexistent")


class TestCheckInstalledAdvanced:
    """Test _check_installed with different dependency types."""

    def test_check_installed_pkg_config_found(self, tmp_path):
        # CMake pkg_check_modules creates pkg-config type dependencies
        cmake_content = "pkg_check_modules(GLIB REQUIRED glib-2.0)"
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)
        helper = TarballHelper()

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if "pkg-config" in cmd:
                result.returncode = 0  # Package found
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("shutil.which", return_value=None):
            with patch("subprocess.run", side_effect=mock_run):
                analysis = helper.analyze(tmp_path)

        glib_dep = next((d for d in analysis.dependencies if d.name == "glib-2.0"), None)
        assert glib_dep is not None
        assert glib_dep.dep_type == "pkg-config"
        assert glib_dep.found is True

    def test_check_installed_apt_package(self, tmp_path):
        cmake_content = "find_package(OpenSSL REQUIRED)"
        (tmp_path / "CMakeLists.txt").write_text(cmake_content)
        helper = TarballHelper()

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if "dpkg-query" in cmd:
                result.returncode = 0
                result.stdout = "install ok installed"
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("shutil.which", return_value=None):
            with patch("subprocess.run", side_effect=mock_run):
                analysis = helper.analyze(tmp_path)

        ssl_dep = next((d for d in analysis.dependencies if d.name == "openssl"), None)
        assert ssl_dep is not None
        assert ssl_dep.found is True


class TestAnalyzeEdgeCases:
    """Test edge cases for analyze methods."""

    def test_analyze_cmake_no_file(self, tmp_path):
        # Call _analyze_cmake directly when CMakeLists.txt doesn't exist
        helper = TarballHelper()
        analysis = BuildAnalysis(build_system=BuildSystem.CMAKE, source_dir=tmp_path)
        helper._analyze_cmake(tmp_path, analysis)
        # Should have no dependencies (early return)
        assert len(analysis.dependencies) == 0

    def test_analyze_meson_no_file(self, tmp_path):
        # Call _analyze_meson directly when meson.build doesn't exist
        helper = TarballHelper()
        analysis = BuildAnalysis(build_system=BuildSystem.MESON, source_dir=tmp_path)
        helper._analyze_meson(tmp_path, analysis)
        # Should have no dependencies (early return)
        assert len(analysis.dependencies) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
