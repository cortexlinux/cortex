#!/usr/bin/env python3
"""
Unit tests for the User Preferences System
Tests all functionality of the PreferencesManager class
"""

import unittest
import tempfile
import shutil
import json
import yaml
from pathlib import Path
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from user_preferences import (
    PreferencesManager,
    UserPreferences,
    VerbosityLevel,
    AICreativity,
    ConfirmationSettings,
    AutoUpdateSettings,
    AISettings,
    PackageSettings
)


class TestUserPreferences(unittest.TestCase):
    """Test UserPreferences dataclass"""
    
    def test_default_preferences(self):
        """Test default preference values"""
        prefs = UserPreferences()
        
        self.assertEqual(prefs.verbosity, VerbosityLevel.NORMAL.value)
        self.assertTrue(prefs.confirmations.before_install)
        self.assertTrue(prefs.auto_update.check_on_start)
        self.assertEqual(prefs.ai.model, "claude-sonnet-4")
        self.assertEqual(prefs.ai.creativity, AICreativity.BALANCED.value)
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary"""
        prefs = UserPreferences()
        prefs_dict = prefs.to_dict()
        
        self.assertIsInstance(prefs_dict, dict)
        self.assertIn('verbosity', prefs_dict)
        self.assertIn('confirmations', prefs_dict)
        self.assertIn('ai', prefs_dict)
        self.assertIn('packages', prefs_dict)
    
    def test_from_dict_conversion(self):
        """Test creation from dictionary"""
        data = {
            'verbosity': 'debug',
            'confirmations': {'before_install': False},
            'ai': {'model': 'gpt-4', 'creativity': 'creative'},
            'packages': {'prefer_latest': True}
        }
        
        prefs = UserPreferences.from_dict(data)
        
        self.assertEqual(prefs.verbosity, 'debug')
        self.assertFalse(prefs.confirmations.before_install)
        self.assertEqual(prefs.ai.model, 'gpt-4')
        self.assertTrue(prefs.packages.prefer_latest)


class TestConfirmationSettings(unittest.TestCase):
    """Test ConfirmationSettings dataclass"""
    
    def test_default_settings(self):
        """Test default confirmation settings"""
        settings = ConfirmationSettings()
        
        self.assertTrue(settings.before_install)
        self.assertTrue(settings.before_remove)
        self.assertFalse(settings.before_upgrade)
        self.assertTrue(settings.before_system_changes)
    
    def test_to_dict(self):
        """Test dictionary conversion"""
        settings = ConfirmationSettings(before_install=False)
        settings_dict = settings.to_dict()
        
        self.assertIsInstance(settings_dict, dict)
        self.assertFalse(settings_dict['before_install'])


class TestAutoUpdateSettings(unittest.TestCase):
    """Test AutoUpdateSettings dataclass"""
    
    def test_default_settings(self):
        """Test default auto-update settings"""
        settings = AutoUpdateSettings()
        
        self.assertTrue(settings.check_on_start)
        self.assertFalse(settings.auto_install)
        self.assertEqual(settings.frequency_hours, 24)


class TestAISettings(unittest.TestCase):
    """Test AISettings dataclass"""
    
    def test_default_settings(self):
        """Test default AI settings"""
        settings = AISettings()
        
        self.assertEqual(settings.model, "claude-sonnet-4")
        self.assertEqual(settings.creativity, AICreativity.BALANCED.value)
        self.assertTrue(settings.explain_steps)
        self.assertTrue(settings.suggest_alternatives)
        self.assertEqual(settings.max_suggestions, 5)


class TestPackageSettings(unittest.TestCase):
    """Test PackageSettings dataclass"""
    
    def test_default_settings(self):
        """Test default package settings"""
        settings = PackageSettings()
        
        self.assertEqual(settings.default_sources, ["official"])
        self.assertFalse(settings.prefer_latest)
        self.assertTrue(settings.auto_cleanup)
        self.assertTrue(settings.backup_before_changes)


class TestPreferencesManager(unittest.TestCase):
    """Test PreferencesManager class"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_path = self.test_dir / "test_config.yaml"
        self.manager = PreferencesManager(config_path=self.config_path)
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_initialization(self):
        """Test manager initialization"""
        self.assertTrue(self.test_dir.exists())
        self.assertEqual(self.manager.config_path, self.config_path)
    
    def test_load_creates_default_config(self):
        """Test that load creates default config if not exists"""
        self.assertFalse(self.config_path.exists())
        
        prefs = self.manager.load()
        
        self.assertTrue(self.config_path.exists())
        self.assertIsInstance(prefs, UserPreferences)
    
    def test_save_and_load(self):
        """Test saving and loading preferences"""
        prefs = self.manager.load()
        prefs.verbosity = VerbosityLevel.DEBUG.value
        prefs.ai.model = "gpt-4"
        
        self.manager.save()
        
        # Create new manager and load
        new_manager = PreferencesManager(config_path=self.config_path)
        loaded_prefs = new_manager.load()
        
        self.assertEqual(loaded_prefs.verbosity, VerbosityLevel.DEBUG.value)
        self.assertEqual(loaded_prefs.ai.model, "gpt-4")
    
    def test_get_preference(self):
        """Test getting preference by key"""
        self.manager.load()
        
        model = self.manager.get("ai.model")
        self.assertEqual(model, "claude-sonnet-4")
        
        before_install = self.manager.get("confirmations.before_install")
        self.assertTrue(before_install)
    
    def test_get_nonexistent_preference(self):
        """Test getting nonexistent preference returns default"""
        self.manager.load()
        
        value = self.manager.get("nonexistent.key", default="default_value")
        self.assertEqual(value, "default_value")
    
    def test_set_preference(self):
        """Test setting preference"""
        self.manager.load()
        
        self.manager.set("ai.model", "gpt-4-turbo")
        self.assertEqual(self.manager.get("ai.model"), "gpt-4-turbo")
        
        self.manager.set("confirmations.before_install", False)
        self.assertFalse(self.manager.get("confirmations.before_install"))
    
    def test_set_invalid_preference(self):
        """Test setting invalid preference raises error"""
        self.manager.load()
        
        with self.assertRaises(ValueError):
            self.manager.set("invalid.key", "value")
        
        with self.assertRaises(ValueError):
            self.manager.set("verbosity", "invalid_level")
    
    def test_set_confirmation_non_boolean(self):
        """Test setting confirmation with non-boolean value"""
        self.manager.load()
        
        with self.assertRaises(ValueError):
            self.manager.set("confirmations.before_install", "not_boolean")
    
    def test_reset_all_preferences(self):
        """Test resetting all preferences to defaults"""
        self.manager.load()
        
        # Change some values
        self.manager.set("ai.model", "gpt-4")
        self.manager.set("verbosity", VerbosityLevel.DEBUG.value)
        
        # Reset all
        self.manager.reset()
        
        # Verify defaults
        self.assertEqual(self.manager.get("ai.model"), "claude-sonnet-4")
        self.assertEqual(self.manager.get("verbosity"), VerbosityLevel.NORMAL.value)
    
    def test_reset_specific_preference(self):
        """Test resetting specific preference"""
        self.manager.load()
        
        self.manager.set("ai.model", "gpt-4")
        self.manager.reset("ai.model")
        
        self.assertEqual(self.manager.get("ai.model"), "claude-sonnet-4")
    
    def test_validate_valid_config(self):
        """Test validation of valid configuration"""
        self.manager.load()
        
        errors = self.manager.validate()
        self.assertEqual(len(errors), 0)
    
    def test_validate_invalid_verbosity(self):
        """Test validation catches invalid verbosity"""
        self.manager.load()
        self.manager._preferences.verbosity = "invalid"
        
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("verbosity" in e.lower() for e in errors))
    
    def test_validate_invalid_creativity(self):
        """Test validation catches invalid creativity level"""
        self.manager.load()
        self.manager._preferences.ai.creativity = "invalid"
        
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("creativity" in e.lower() for e in errors))
    
    def test_validate_invalid_frequency(self):
        """Test validation catches invalid update frequency"""
        self.manager.load()
        self.manager._preferences.auto_update.frequency_hours = 0
        
        errors = self.manager.validate()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("frequency" in e.lower() for e in errors))
    
    def test_backup_creation(self):
        """Test backup file creation"""
        self.manager.load()
        self.manager.save()
        
        # Modify and save again to trigger backup
        self.manager.set("ai.model", "gpt-4")
        self.manager.save(backup=True)
        
        # Check for backup files
        backup_files = list(self.test_dir.glob("*.backup.*"))
        self.assertGreater(len(backup_files), 0)
    
    def test_export_json(self):
        """Test exporting preferences to JSON"""
        self.manager.load()
        
        export_path = self.test_dir / "export.json"
        self.manager.export_json(export_path)
        
        self.assertTrue(export_path.exists())
        
        with open(export_path, 'r') as f:
            data = json.load(f)
        
        self.assertIn('verbosity', data)
        self.assertIn('ai', data)
    
    def test_import_json(self):
        """Test importing preferences from JSON"""
        # Create JSON file
        import_data = {
            'verbosity': 'verbose',
            'ai': {'model': 'gpt-4-turbo', 'creativity': 'creative'},
            'confirmations': {'before_install': False},
            'auto_update': {'check_on_start': False},
            'packages': {'default_sources': ['official']},
            'theme': 'dark',
            'language': 'en',
            'timezone': 'UTC'
        }
        
        import_path = self.test_dir / "import.json"
        with open(import_path, 'w') as f:
            json.dump(import_data, f)
        
        # Import
        self.manager.import_json(import_path)
        
        # Verify
        self.assertEqual(self.manager.get('verbosity'), 'verbose')
        self.assertEqual(self.manager.get('ai.model'), 'gpt-4-turbo')
        self.assertFalse(self.manager.get('confirmations.before_install'))
    
    def test_import_invalid_json(self):
        """Test importing invalid JSON raises error"""
        import_data = {
            'verbosity': 'invalid_level',
            'ai': {'model': 'unknown_model'},
            'confirmations': {},
            'auto_update': {},
            'packages': {'default_sources': ['official']},
            'theme': 'default',
            'language': 'en',
            'timezone': 'UTC'
        }
        
        import_path = self.test_dir / "invalid.json"
        with open(import_path, 'w') as f:
            json.dump(import_data, f)
        
        with self.assertRaises(ValueError):
            self.manager.import_json(import_path)
    
    def test_get_config_info(self):
        """Test getting configuration info"""
        self.manager.load()
        
        info = self.manager.get_config_info()
        
        self.assertIn('config_path', info)
        self.assertIn('exists', info)
        self.assertIn('writable', info)
        self.assertTrue(info['exists'])
    
    def test_list_all_preferences(self):
        """Test listing all preferences"""
        self.manager.load()
        
        all_prefs = self.manager.list_all()
        
        self.assertIsInstance(all_prefs, dict)
        self.assertIn('verbosity', all_prefs)
        self.assertIn('confirmations', all_prefs)
        self.assertIn('ai', all_prefs)
        self.assertIn('packages', all_prefs)
    
    def test_yaml_format(self):
        """Test that saved config is valid YAML"""
        self.manager.load()
        self.manager.save()
        
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        self.assertIsInstance(data, dict)
        self.assertIn('verbosity', data)
    
    def test_concurrent_access(self):
        """Test handling of concurrent access"""
        manager1 = PreferencesManager(config_path=self.config_path)
        manager2 = PreferencesManager(config_path=self.config_path)
        
        prefs1 = manager1.load()
        prefs2 = manager2.load()
        
        manager1.set("ai.model", "gpt-4")
        manager1.save()
        
        # Manager2 should be able to reload
        manager2.load()
        self.assertEqual(manager2.get("ai.model"), "gpt-4")
    
    def test_invalid_yaml_handling(self):
        """Test handling of invalid YAML file"""
        # Write invalid YAML
        with open(self.config_path, 'w') as f:
            f.write("invalid: yaml: content: !!!")
        
        with self.assertRaises(ValueError):
            self.manager.load()
    
    def test_missing_directory_creation(self):
        """Test that missing directories are created"""
        nested_path = self.test_dir / "nested" / "dir" / "config.yaml"
        manager = PreferencesManager(config_path=nested_path)
        
        self.assertTrue(nested_path.parent.exists())


class TestEnums(unittest.TestCase):
    """Test enum classes"""
    
    def test_verbosity_levels(self):
        """Test VerbosityLevel enum"""
        self.assertEqual(VerbosityLevel.QUIET.value, "quiet")
        self.assertEqual(VerbosityLevel.NORMAL.value, "normal")
        self.assertEqual(VerbosityLevel.VERBOSE.value, "verbose")
        self.assertEqual(VerbosityLevel.DEBUG.value, "debug")
    
    def test_ai_creativity(self):
        """Test AICreativity enum"""
        self.assertEqual(AICreativity.CONSERVATIVE.value, "conservative")
        self.assertEqual(AICreativity.BALANCED.value, "balanced")
        self.assertEqual(AICreativity.CREATIVE.value, "creative")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_path = self.test_dir / "test_config.yaml"
        self.manager = PreferencesManager(config_path=self.config_path)
    
    def tearDown(self):
        """Clean up test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_empty_config_file(self):
        """Test handling of empty config file"""
        # Create empty file
        self.config_path.touch()
        
        prefs = self.manager.load()
        self.assertIsInstance(prefs, UserPreferences)
    
    def test_save_without_load(self):
        """Test that save without load raises error"""
        with self.assertRaises(RuntimeError):
            self.manager.save()
    
    def test_set_without_load(self):
        """Test that set without load loads automatically"""
        self.manager.set("ai.model", "gpt-4")
        self.assertEqual(self.manager.get("ai.model"), "gpt-4")
    
    def test_nested_key_access(self):
        """Test deeply nested key access"""
        self.manager.load()
        
        # Set nested value
        self.manager.set("ai.max_suggestions", 10)
        
        # Get nested value
        value = self.manager.get("ai.max_suggestions")
        self.assertEqual(value, 10)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestUserPreferences))
    suite.addTests(loader.loadTestsFromTestCase(TestConfirmationSettings))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoUpdateSettings))
    suite.addTests(loader.loadTestsFromTestCase(TestAISettings))
    suite.addTests(loader.loadTestsFromTestCase(TestPackageSettings))
    suite.addTests(loader.loadTestsFromTestCase(TestPreferencesManager))
    suite.addTests(loader.loadTestsFromTestCase(TestEnums))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
