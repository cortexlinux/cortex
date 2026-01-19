#!/usr/bin/env python3
"""
Unit tests for TemplateManager.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from cortex.template_manager import TemplateManager


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.template_manager = TemplateManager(template_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_create_template(self, mock_export):
        mock_export.return_value = "Success"

        v1 = self.template_manager.create_template("test-template", "Description 1")
        self.assertEqual(v1, "v1")

        v2 = self.template_manager.create_template("test-template", "Description 2")
        self.assertEqual(v2, "v2")

        self.assertTrue((self.temp_dir / "test-template" / "v1" / "metadata.json").exists())
        self.assertTrue((self.temp_dir / "test-template" / "v2" / "metadata.json").exists())

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_list_templates(self, mock_export):
        self.template_manager.create_template("t1", "desc1")
        self.template_manager.create_template("t2", "desc2")

        templates = self.template_manager.list_templates()
        self.assertEqual(len(templates), 2)
        self.assertEqual(templates[0]["name"], "t1")
        self.assertEqual(templates[1]["name"], "t2")

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_get_template(self, mock_export):
        # Create a dummy config file so get_template can read it
        output_name = "test-t"
        v = self.template_manager.create_template(output_name, "desc")
        config_path = self.temp_dir / output_name / v / "template.yaml"
        with open(config_path, "w") as f:
            f.write("test: data")

        t = self.template_manager.get_template(output_name, v)
        self.assertIsNotNone(t)
        self.assertEqual(t["name"], output_name)
        self.assertEqual(t["config"]["test"], "data")

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_export_import_template(self, mock_export):
        name = "exp-template"
        v = self.template_manager.create_template(name, "to export")
        config_path = self.temp_dir / name / v / "template.yaml"
        with open(config_path, "w") as f:
            f.write("foo: bar")

        zip_path = self.temp_dir / "export.zip"
        self.template_manager.export_template(name, v, str(zip_path))

        self.assertTrue(zip_path.exists())

        # Import as new template
        new_name, new_v = self.template_manager.import_template(str(zip_path))
        self.assertEqual(new_name, name)
        # It'll be a new version since v1 exists
        self.assertIn("v1", new_v)

        imported = self.template_manager.get_template(new_name, new_v)
        self.assertEqual(imported["config"]["foo"], "bar")

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_get_template_latest(self, mock_export):
        name = "latest-test"
        self.template_manager.create_template(name, "v1")
        self.template_manager.create_template(name, "v2")

        # Create dummy files
        for v in ["v1", "v2"]:
            p = self.temp_dir / name / v
            with open(p / "template.yaml", "w") as f:
                f.write("f: b")

        t = self.template_manager.get_template(name)
        self.assertEqual(t["version"], "v2")

    def test_get_template_not_found(self):
        self.assertIsNone(self.template_manager.get_template("nonexistent"))

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_delete_template_and_version(self, mock_export):
        name = "del-test"
        self.template_manager.create_template(name, "v1")
        self.template_manager.create_template(name, "v2")

        # Delete v2
        self.assertTrue(self.template_manager.delete_template(name, "v2"))
        self.assertFalse((self.temp_dir / name / "v2").exists())
        self.assertTrue((self.temp_dir / name / "v1").exists())

        # Delete v1 -> removes whole template dir
        self.assertTrue(self.template_manager.delete_template(name, "v1"))
        self.assertFalse((self.temp_dir / name).exists())

        # Delete nonexistent
        self.assertFalse(self.template_manager.delete_template("nope"))

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_export_errors(self, mock_export):
        with self.assertRaises(ValueError):
            self.template_manager.export_template("none", "v1", "out.zip")

    def test_import_errors(self):
        # File not found
        with self.assertRaises(FileNotFoundError):
            self.template_manager.import_template("nonexistent.zip")

        # Missing metadata.json
        zip_path = self.temp_dir / "invalid.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("random.txt", "data")
        with self.assertRaises(ValueError):
            self.template_manager.import_template(str(zip_path))

    @patch("cortex.config_manager.ConfigManager.export_configuration")
    def test_list_templates_empty(self, mock_export):
        shutil.rmtree(self.temp_dir)
        self.assertEqual(self.template_manager.list_templates(), [])


if __name__ == "__main__":
    unittest.main()
