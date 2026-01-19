#!/usr/bin/env python3
"""
Unit tests for service extensions in ConfigManager.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from cortex.config_manager import ConfigManager


class TestConfigManagerServices(unittest.TestCase):
    def setUp(self):
        self.config_manager = ConfigManager()

    @patch("subprocess.run")
    def test_detect_services(self, mock_run):
        # Mock list-units
        mock_units = MagicMock()
        mock_units.returncode = 0
        mock_units.stdout = "test.service loaded active running Test Service\nother.service loaded inactive dead Other Service\n"

        # Mock is-enabled (called twice)
        mock_enabled = MagicMock()
        mock_enabled.returncode = 0
        mock_enabled.stdout = "enabled\n"

        mock_disabled = MagicMock()
        mock_disabled.returncode = 0
        mock_disabled.stdout = "disabled\n"

        mock_run.side_effect = [mock_units, mock_enabled, mock_disabled]

        services = self.config_manager.detect_services()

        self.assertEqual(len(services), 2)
        self.assertEqual(services[0]["name"], "test.service")
        self.assertEqual(services[0]["active_state"], "active")
        self.assertTrue(services[0]["enabled"])

        self.assertEqual(services[1]["name"], "other.service")
        self.assertEqual(services[1]["active_state"], "inactive")
        self.assertFalse(services[1]["enabled"])

    def test_categorize_service(self):
        current_map = {
            "test.service": {"name": "test.service", "active_state": "active", "enabled": True},
            "stopped.service": {
                "name": "stopped.service",
                "active_state": "inactive",
                "enabled": True,
            },
        }

        # Already correct
        srv = {"name": "test.service", "active_state": "active", "enabled": True}
        cat, data = self.config_manager._categorize_service(srv, current_map)
        self.assertEqual(cat, "already_correct")

        # Update needed
        srv = {"name": "stopped.service", "active_state": "active", "enabled": True}
        cat, data = self.config_manager._categorize_service(srv, current_map)
        self.assertEqual(cat, "update")
        self.assertEqual(data["current_state"], "inactive")

        # Missing
        srv = {"name": "new.service", "active_state": "active", "enabled": True}
        cat, data = self.config_manager._categorize_service(srv, current_map)
        self.assertEqual(cat, "missing")

    @patch("subprocess.run")
    def test_update_service(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        srv = {"name": "test.service", "active_state": "active", "enabled": True}
        success = self.config_manager._update_service(srv)

        self.assertTrue(success)
        self.assertEqual(mock_run.call_count, 2)  # enable and start

    @patch("subprocess.run")
    def test_update_service_failure(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res

        srv = {"name": "fail.service", "active_state": "active", "enabled": True}
        success = self.config_manager._update_service(srv)
        self.assertFalse(success)

    @patch("cortex.config_manager.ConfigManager.detect_services")
    @patch("cortex.config_manager.ConfigManager.detect_apt_packages")
    @patch("cortex.config_manager.ConfigManager.detect_pip_packages")
    @patch("cortex.config_manager.ConfigManager.detect_npm_packages")
    @patch("cortex.hwprofiler.HardwareProfiler.profile")
    def test_diff_configuration_with_services(
        self, mock_profile, mock_npm, mock_pip, mock_apt, mock_srv
    ):
        mock_profile.return_value = {"os": "24.04"}
        mock_apt.return_value = []
        mock_pip.return_value = []
        mock_npm.return_value = []
        mock_srv.return_value = [
            {
                "name": "test.service",
                "active_state": "active",
                "enabled": False,
                "source": "service",
            }
        ]

        template_config = {
            "os": "24.04",
            "packages": [
                {
                    "name": "test.service",
                    "active_state": "active",
                    "enabled": True,
                    "source": "service",
                },
                {
                    "name": "new.service",
                    "active_state": "active",
                    "enabled": True,
                    "source": "service",
                },
            ],
        }

        diff = self.config_manager.diff_configuration(template_config)

        self.assertEqual(len(diff["services_to_update"]), 1)
        self.assertEqual(diff["services_to_update"][0]["name"], "test.service")
        self.assertEqual(len(diff["services_missing"]), 1)
        self.assertEqual(diff["services_missing"][0]["name"], "new.service")

    @patch("cortex.config_manager.ConfigManager.diff_configuration")
    @patch("cortex.config_manager.ConfigManager._update_service")
    def test_import_services(self, mock_update, mock_diff):
        mock_update.return_value = True
        mock_diff.return_value = {
            "services_missing": [{"name": "s1"}],
            "services_to_update": [{"name": "s2"}],
        }

        config = {"packages": []}
        summary = {"installed": [], "failed": [], "services_updated": [], "services_failed": []}

        self.config_manager._import_services(config, summary)

        # summary has "services_updated" from _import_services
        self.assertEqual(len(summary["services_updated"]), 1)  # s1 is ignored as per implementation
        self.assertEqual(mock_update.call_count, 1)

    @patch("cortex.config_manager.ConfigManager.detect_services")
    @patch("cortex.config_manager.ConfigManager.detect_apt_packages")
    def test_detect_installed_packages_with_services(self, mock_apt, mock_srv):
        mock_apt.return_value = [{"name": "pkg1", "source": "apt"}]
        mock_srv.return_value = [{"name": "srv1", "source": "service"}]

        items = self.config_manager.detect_installed_packages(sources=["apt", "service"])

        self.assertEqual(len(items), 2)
        sources = [i["source"] for i in items]
        self.assertIn("apt", sources)
        self.assertIn("service", sources)

    @patch("cortex.config_manager.ConfigManager.diff_configuration")
    @patch("cortex.config_manager.ConfigManager._update_service")
    def test_import_services_failure(self, mock_update, mock_diff):
        mock_update.return_value = False
        mock_diff.return_value = {"services_to_update": [{"name": "fail-srv"}]}
        summary = {"installed": [], "failed": [], "services_updated": [], "services_failed": []}

        self.config_manager._import_services({}, summary)
        self.assertIn("service:fail-srv", summary["failed"])

    def test_categorize_service_skip(self):
        cat, data = self.config_manager._categorize_service({}, {})
        self.assertEqual(cat, "skip")

    @patch("subprocess.run")
    def test_detect_services_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        services = self.config_manager.detect_services()
        self.assertEqual(services, [])


if __name__ == "__main__":
    unittest.main()
