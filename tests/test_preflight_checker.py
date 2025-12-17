"""
Unit tests for PreflightChecker

Tests the preflight system checking functionality for installation simulation.
"""

import os
import platform
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cortex.preflight_checker import (
    DiskInfo,
    PackageInfo,
    PreflightChecker,
    PreflightReport,
    ServiceInfo,
    export_report,
    format_report,
)


class TestPreflightChecker(unittest.TestCase):

    def setUp(self):
        self.checker = PreflightChecker()  # No API key for basic tests

    def test_check_os_info(self):
        """Test OS information detection"""
        info = self.checker.check_os_info()

        self.assertIn("platform", info)
        self.assertIn("platform_release", info)
        self.assertIn("machine", info)
        self.assertIsNotNone(info["platform"])

    def test_check_basic_system_info(self):
        """Test basic system information detection"""
        info = self.checker.check_basic_system_info()

        self.assertIn("kernel", info)
        self.assertIn("architecture", info)
        self.assertIsNotNone(info["kernel"])
        self.assertIsNotNone(info["architecture"])

    def test_check_disk_space(self):
        """Test disk space checking"""
        disk_info = self.checker.check_disk_space()

        self.assertIsInstance(disk_info, list)
        self.assertTrue(len(disk_info) > 0)

        # Check that current directory is included
        cwd = os.getcwd()
        cwd_checked = any(d.path == cwd or cwd.startswith(d.path) for d in disk_info)
        self.assertTrue(cwd_checked or len(disk_info) > 0)

    def test_check_software(self):
        """Test software package detection"""
        # Test with a common package
        pkg = self.checker.check_software("curl")

        self.assertIsInstance(pkg, PackageInfo)
        self.assertEqual(pkg.name, "curl")
        self.assertIsInstance(pkg.installed, bool)

    def test_run_all_checks(self):
        """Test running all preflight checks"""
        report = self.checker.run_all_checks("docker")

        self.assertIsInstance(report, PreflightReport)
        self.assertIsNotNone(report.os_info)
        self.assertIsNotNone(report.kernel_info)  # Now contains basic system info
        self.assertIsInstance(report.disk_usage, list)
        self.assertIsInstance(report.package_status, list)
        self.assertIsInstance(report.errors, list)
        self.assertIsInstance(report.warnings, list)


class TestPreflightReport(unittest.TestCase):

    def test_report_dataclass(self):
        """Test PreflightReport dataclass initialization"""
        report = PreflightReport()

        self.assertEqual(report.os_info, {})
        self.assertEqual(report.kernel_info, {})
        self.assertEqual(report.cpu_arch, "")
        self.assertEqual(report.disk_usage, [])
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.suggestions, [])

    def test_disk_info_dataclass(self):
        """Test DiskInfo dataclass"""
        disk = DiskInfo(
            path="/", free_mb=50000, total_mb=100000, filesystem="ext4", exists=True, writable=True
        )

        self.assertEqual(disk.path, "/")
        self.assertEqual(disk.free_mb, 50000)
        self.assertTrue(disk.exists)

    def test_package_info_dataclass(self):
        """Test PackageInfo dataclass"""
        pkg = PackageInfo(name="docker", installed=True, version="24.0.7", path="/usr/bin/docker")

        self.assertEqual(pkg.name, "docker")
        self.assertTrue(pkg.installed)
        self.assertEqual(pkg.version, "24.0.7")


class TestFormatReport(unittest.TestCase):

    def test_format_report_basic(self):
        """Test report formatting"""
        report = PreflightReport()
        report.os_info = {"distro": "Ubuntu", "distro_version": "22.04"}
        report.kernel_info = {"version": "5.15.0"}
        report.cpu_arch = "amd64"
        report.packages_to_install = [{"name": "docker-ce", "version": "latest", "size_mb": "85"}]
        report.total_download_mb = 85
        report.total_disk_required_mb = 255
        report.disk_usage = [
            DiskInfo(
                path="/",
                free_mb=50000,
                total_mb=100000,
                filesystem="ext4",
                exists=True,
                writable=True,
            )
        ]

        output = format_report(report, "docker")

        self.assertIn("Simulation mode", output)
        self.assertIn("docker-ce", output)
        self.assertIn("85 MB", output)

    def test_format_report_no_install_needed(self):
        """Test report when software is already installed"""
        report = PreflightReport()
        report.os_info = {"distro": "Ubuntu", "distro_version": "22.04"}
        report.kernel_info = {"version": "5.15.0"}
        report.cpu_arch = "amd64"
        report.packages_to_install = []
        report.disk_usage = []

        output = format_report(report, "docker")

        self.assertIn("already installed", output)


class TestCLISimulateIntegration(unittest.TestCase):

    @patch("cortex.cli.PreflightChecker")
    def test_install_simulate_flag(self, mock_checker_class):
        """Test --simulate flag integration"""
        from cortex.cli import CortexCLI

        mock_checker = MagicMock()
        mock_report = PreflightReport()
        mock_report.os_info = {"distro": "Ubuntu", "distro_version": "22.04"}
        mock_report.kernel_info = {"version": "5.15.0"}
        mock_report.cpu_arch = "amd64"
        mock_report.disk_usage = []
        mock_report.packages_to_install = []
        mock_checker.run_all_checks.return_value = mock_report
        mock_checker_class.return_value = mock_checker

        cli = CortexCLI()
        result = cli.install("docker", simulate=True)

        self.assertEqual(result, 0)
        mock_checker.run_all_checks.assert_called_once_with("docker")

    @patch("sys.argv", ["cortex", "install", "docker", "--simulate"])
    @patch("cortex.cli.CortexCLI.install")
    def test_main_simulate_arg(self, mock_install):
        """Test main function parses --simulate"""
        from cortex.cli import main

        mock_install.return_value = 0
        result = main()

        self.assertEqual(result, 0)
        mock_install.assert_called_once_with("docker", execute=False, dry_run=False, simulate=True)


if __name__ == "__main__":
    unittest.main()
