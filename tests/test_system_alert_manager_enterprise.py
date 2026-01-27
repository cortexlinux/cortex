"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.

Comprehensive enterprise tests for SystemAlertManager.

Tests all enterprise security features including:
- Input validation and sanitization
- Data encryption for sensitive fields
- Rate limiting protection
- Audit logging
- Database integrity checks
- Backup and recovery
- Performance monitoring
"""

import datetime
import json
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cx.system_alert_manager import (
    SystemAlertManager,
    AlertType,
    AlertSeverity,
    AlertStatus,
    UserTier,
    RevenueEventType,
    SecurityValidator,
    ValidationException,
    SecurityException,
    DataEncryption,
    RateLimiter
)


class TestSecurityValidator(unittest.TestCase):
    """Test enterprise input validation."""

    def setUp(self):
        self.validator = SecurityValidator()

    def test_email_validation(self):
        """Test email validation with security requirements."""
        # Valid emails
        self.assertTrue(self.validator.validate_email("user@example.com"))
        self.assertTrue(self.validator.validate_email("test.email+tag@domain.co.uk"))
        self.assertTrue(self.validator.validate_email("user123@test-domain.com"))

        # Invalid emails
        self.assertFalse(self.validator.validate_email(""))
        self.assertFalse(self.validator.validate_email("invalid-email"))
        self.assertFalse(self.validator.validate_email("@domain.com"))
        self.assertFalse(self.validator.validate_email("user@"))
        self.assertFalse(self.validator.validate_email("user@.com"))
        self.assertFalse(self.validator.validate_email("user space@domain.com"))

        # Length limits
        self.assertFalse(self.validator.validate_email("a" * 250 + "@domain.com"))

    def test_user_id_validation(self):
        """Test user ID format validation."""
        # Valid user IDs
        self.assertTrue(self.validator.validate_user_id("user123"))
        self.assertTrue(self.validator.validate_user_id("test-user"))
        self.assertTrue(self.validator.validate_user_id("test_user"))
        self.assertTrue(self.validator.validate_user_id("USER123"))

        # Invalid user IDs
        self.assertFalse(self.validator.validate_user_id(""))
        self.assertFalse(self.validator.validate_user_id("user@123"))
        self.assertFalse(self.validator.validate_user_id("user 123"))
        self.assertFalse(self.validator.validate_user_id("user.123"))
        self.assertFalse(self.validator.validate_user_id("user#123"))

        # Length limits
        self.assertFalse(self.validator.validate_user_id("a" * 130))

    def test_amount_validation(self):
        """Test monetary amount validation."""
        # Valid amounts
        self.assertTrue(self.validator.validate_amount(Decimal("29.99")))
        self.assertTrue(self.validator.validate_amount(100.50))
        self.assertTrue(self.validator.validate_amount("0"))
        self.assertTrue(self.validator.validate_amount("999999999.99"))

        # Invalid amounts
        self.assertFalse(self.validator.validate_amount(-1))
        self.assertFalse(self.validator.validate_amount("invalid"))
        self.assertFalse(self.validator.validate_amount(None))
        self.assertFalse(self.validator.validate_amount("1000000000.00"))  # Too large

    def test_text_sanitization(self):
        """Test text input sanitization."""
        # Normal text
        self.assertEqual(
            self.validator.sanitize_text("Hello World!"),
            "Hello World!"
        )

        # Control characters (should be removed except newlines/tabs)
        self.assertEqual(
            self.validator.sanitize_text("Hello\x00World\x01"),
            "HelloWorld"
        )

        # Newlines and tabs preserved
        self.assertEqual(
            self.validator.sanitize_text("Hello\nWorld\tTest"),
            "Hello\nWorld\tTest"
        )

        # Length limits
        long_text = "a" * 2000
        result = self.validator.sanitize_text(long_text, max_length=100)
        self.assertEqual(len(result), 100)

        # Empty input
        self.assertEqual(self.validator.sanitize_text(""), "")
        self.assertEqual(self.validator.sanitize_text(None), "")

    def test_json_metadata_validation(self):
        """Test JSON metadata security validation."""
        # Valid metadata
        self.assertTrue(self.validator.validate_json_metadata({"key": "value"}))
        self.assertTrue(self.validator.validate_json_metadata([1, 2, 3]))
        self.assertTrue(self.validator.validate_json_metadata("string"))
        self.assertTrue(self.validator.validate_json_metadata(123))
        self.assertTrue(self.validator.validate_json_metadata(None))

        # Invalid metadata (too large - 1MB+ JSON)
        large_dict = {"data": "x" * (1024 * 1024 + 1)}
        self.assertFalse(self.validator.validate_json_metadata(large_dict))

        # Non-serializable objects
        self.assertFalse(self.validator.validate_json_metadata(object()))


class TestDataEncryption(unittest.TestCase):
    """Test enterprise data encryption."""

    def setUp(self):
        from cryptography.fernet import Fernet
        self.encryption_key = Fernet.generate_key()
        self.encryptor = DataEncryption(self.encryption_key)

    def test_encryption_decryption(self):
        """Test basic encryption and decryption."""
        original_data = "sensitive@example.com"

        # Encrypt
        encrypted = self.encryptor.encrypt(original_data)
        self.assertNotEqual(encrypted, original_data)
        self.assertTrue(len(encrypted) > len(original_data))

        # Decrypt
        decrypted = self.encryptor.decrypt(encrypted)
        self.assertEqual(decrypted, original_data)

    def test_empty_data_handling(self):
        """Test encryption of empty/None data."""
        # Empty string
        self.assertEqual(self.encryptor.encrypt(""), "")
        self.assertEqual(self.encryptor.decrypt(""), "")

        # None handling should not cause errors
        self.assertEqual(self.encryptor.encrypt(None), None)

    def test_unicode_handling(self):
        """Test encryption of unicode characters."""
        unicode_data = "test@tëst.com 🔒"
        encrypted = self.encryptor.encrypt(unicode_data)
        decrypted = self.encryptor.decrypt(encrypted)
        self.assertEqual(decrypted, unicode_data)


class TestRateLimiter(unittest.TestCase):
    """Test enterprise rate limiting."""

    def test_rate_limiting(self):
        """Test basic rate limiting functionality."""
        limiter = RateLimiter(max_requests=3, window_seconds=1)

        # First 3 requests should be allowed
        self.assertTrue(limiter.is_allowed("test_user"))
        self.assertTrue(limiter.is_allowed("test_user"))
        self.assertTrue(limiter.is_allowed("test_user"))

        # 4th request should be denied
        self.assertFalse(limiter.is_allowed("test_user"))

    def test_rate_limiting_different_users(self):
        """Test rate limiting for different identifiers."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        # Different users should have separate limits
        self.assertTrue(limiter.is_allowed("user1"))
        self.assertTrue(limiter.is_allowed("user2"))
        self.assertTrue(limiter.is_allowed("user1"))
        self.assertTrue(limiter.is_allowed("user2"))

        # Both users should now be at limit
        self.assertFalse(limiter.is_allowed("user1"))
        self.assertFalse(limiter.is_allowed("user2"))

    def test_rate_limiting_window_reset(self):
        """Test rate limiting window reset."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)

        # Use up the limit
        self.assertTrue(limiter.is_allowed("test_user"))
        self.assertTrue(limiter.is_allowed("test_user"))
        self.assertFalse(limiter.is_allowed("test_user"))

        # Simulate time passing (we'll test the logic manually)
        import time
        with patch('time.time') as mock_time:
            # Advance time by 2 seconds
            mock_time.return_value = time.time() + 2
            # Should be allowed again
            self.assertTrue(limiter.is_allowed("test_user"))


class TestSystemAlertManagerEnterprise(unittest.TestCase):
    """Test enterprise features of SystemAlertManager."""

    def setUp(self):
        """Set up test environment with temporary database."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = Path(self.temp_dir.name) / "test_alerts.db"
        self.manager = SystemAlertManager(db_path=self.test_db_path)

    def tearDown(self):
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_alert_creation_with_validation(self):
        """Test alert creation with enterprise validation."""
        # Valid alert creation
        alert_id = self.manager.create_alert(
            AlertType.SYSTEM_HEALTH,
            AlertSeverity.NORMAL,
            "test_source",
            "Test Alert",
            "This is a test alert message"
        )
        self.assertGreater(alert_id, 0)

        # Test input validation failures
        with self.assertRaises(ValidationException):
            self.manager.create_alert(
                "invalid_type",  # Not an AlertType enum
                AlertSeverity.NORMAL,
                "test_source",
                "Test Alert",
                "Message"
            )

        with self.assertRaises(ValidationException):
            self.manager.create_alert(
                AlertType.SYSTEM_HEALTH,
                AlertSeverity.NORMAL,
                "",  # Empty source
                "Test Alert",
                "Message"
            )

        with self.assertRaises(ValidationException):
            self.manager.create_alert(
                AlertType.SYSTEM_HEALTH,
                AlertSeverity.NORMAL,
                "test_source",
                "",  # Empty title
                "Message"
            )

    def test_text_sanitization_in_alerts(self):
        """Test that text inputs are properly sanitized."""
        # Test with control characters
        alert_id = self.manager.create_alert(
            AlertType.SYSTEM_HEALTH,
            AlertSeverity.NORMAL,
            "test\x00source\x01",  # Control characters
            "Test\x02Alert",
            "Message\x03with\x04control\x05chars"
        )

        # Verify alert was created and text was sanitized
        alerts = self.manager.query_alerts(limit=1)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]

        # Control characters should be removed
        self.assertNotIn('\x00', alert['source'])
        self.assertNotIn('\x01', alert['source'])
        self.assertNotIn('\x02', alert['title'])

    def test_user_profile_creation_with_encryption(self):
        """Test user profile creation with email encryption."""
        # Create user profile
        profile = self.manager.create_user_profile(
            user_id="test_user_001",
            email="test@example.com",
            tier=UserTier.PRO
        )

        # Verify profile was created
        self.assertEqual(profile.user_id, "test_user_001")
        self.assertEqual(profile.email, "test@example.com")
        self.assertTrue(len(profile.referral_code), 12)

        # Verify email is encrypted in database
        with sqlite3.connect(str(self.test_db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM user_profiles WHERE user_id = ?", ("test_user_001",))
            stored_email = cursor.fetchone()[0]

            # Stored email should not match original (encrypted)
            self.assertNotEqual(stored_email, "test@example.com")

            # But it should decrypt to original
            decrypted_email = self.manager.encryptor.decrypt(stored_email)
            self.assertEqual(decrypted_email, "test@example.com")

    def test_user_validation_failures(self):
        """Test user profile validation failures."""
        # Invalid user ID
        with self.assertRaises(ValidationException):
            self.manager.create_user_profile(
                user_id="invalid@user",  # Contains @
                email="test@example.com",
                tier=UserTier.PRO
            )

        # Invalid email
        with self.assertRaises(ValidationException):
            self.manager.create_user_profile(
                user_id="test_user",
                email="invalid-email",  # Invalid format
                tier=UserTier.PRO
            )

        # Duplicate user ID
        self.manager.create_user_profile(
            user_id="duplicate_user",
            email="first@example.com",
            tier=UserTier.PRO
        )

        with self.assertRaises(SecurityException):
            self.manager.create_user_profile(
                user_id="duplicate_user",  # Same user ID
                email="second@example.com",
                tier=UserTier.PRO
            )

    def test_founding_member_detection(self):
        """Test founding member detection for first 1,000 users."""
        # Create a user - should be founding member
        profile = self.manager.create_user_profile(
            user_id="founding_001",
            email="founding@example.com",
            tier=UserTier.PRO
        )

        self.assertTrue(profile.founding_member)

    def test_rate_limiting_protection(self):
        """Test that rate limiting protects against abuse."""
        # Override rate limiter with very low limits for testing
        original_limiter = self.manager.rate_limiter
        self.manager.rate_limiter = RateLimiter(max_requests=2, window_seconds=60)

        try:
            # First 2 alert creations should succeed
            alert1 = self.manager.create_alert(
                AlertType.SYSTEM_HEALTH,
                AlertSeverity.NORMAL,
                "test_source",
                "Alert 1",
                "First alert"
            )
            self.assertGreater(alert1, 0)

            alert2 = self.manager.create_alert(
                AlertType.SYSTEM_HEALTH,
                AlertSeverity.NORMAL,
                "test_source",
                "Alert 2",
                "Second alert"
            )
            self.assertGreater(alert2, 0)

            # Third should fail with rate limit
            with self.assertRaises(SecurityException) as cm:
                self.manager.create_alert(
                    AlertType.SYSTEM_HEALTH,
                    AlertSeverity.NORMAL,
                    "test_source",
                    "Alert 3",
                    "Third alert"
                )

            self.assertIn("Rate limit exceeded", str(cm.exception))

        finally:
            # Restore original rate limiter
            self.manager.rate_limiter = original_limiter

    def test_database_backup_functionality(self):
        """Test database backup creation."""
        # Create some test data
        self.manager.create_alert(
            AlertType.SYSTEM_HEALTH,
            AlertSeverity.NORMAL,
            "test_source",
            "Test Alert",
            "Test message"
        )

        # Create backup
        backup_path = Path(self.temp_dir.name) / "test_backup.db"
        result = self.manager.backup_database(backup_path)

        self.assertTrue(result)
        self.assertTrue(backup_path.exists())

        # Verify backup contains data
        backup_manager = SystemAlertManager(db_path=backup_path)
        alerts = backup_manager.query_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['title'], "Test Alert")

    def test_database_optimization(self):
        """Test database optimization functionality."""
        # Create some test data
        for i in range(10):
            self.manager.create_alert(
                AlertType.SYSTEM_HEALTH,
                AlertSeverity.NORMAL,
                f"source_{i}",
                f"Alert {i}",
                f"Message {i}"
            )

        # Test optimization
        result = self.manager.optimize_database()
        self.assertTrue(result)

    def test_integrity_validation(self):
        """Test database integrity validation."""
        # Create test data
        self.manager.create_alert(
            AlertType.SYSTEM_HEALTH,
            AlertSeverity.NORMAL,
            "test_source",
            "Test Alert",
            "Test message"
        )

        # Run integrity check
        integrity_results = self.manager.validate_database_integrity()

        self.assertTrue(integrity_results['integrity_check'])
        self.assertTrue(integrity_results['foreign_key_check'])
        self.assertTrue(integrity_results['data_consistency'])
        self.assertEqual(len(integrity_results['errors']), 0)

    def test_performance_metrics(self):
        """Test performance metrics collection."""
        # Create some test data
        self.manager.create_alert(
            AlertType.SYSTEM_HEALTH,
            AlertSeverity.NORMAL,
            "test_source",
            "Test Alert",
            "Test message"
        )

        metrics = self.manager.get_performance_metrics()

        self.assertIn('database', metrics)
        self.assertIn('operations', metrics)
        self.assertIn('security', metrics)

        self.assertGreater(metrics['database']['size_bytes'], 0)
        self.assertEqual(metrics['database']['alert_count'], 1)
        self.assertTrue(metrics['security']['encryption_enabled'])
        self.assertTrue(metrics['security']['rate_limiting_enabled'])

    def test_health_check_functionality(self):
        """Test comprehensive health check."""
        health = self.manager.health_check()

        self.assertIn('status', health)
        self.assertIn('checks', health)
        self.assertIn('timestamp', health)

        # Should have various health checks
        checks = health['checks']
        self.assertIn('database_connectivity', checks)
        self.assertIn('encryption', checks)
        self.assertIn('security_config', checks)

        self.assertTrue(checks['database_connectivity'])
        self.assertTrue(checks['encryption'])

    def test_revenue_event_recording(self):
        """Test revenue event recording with validation."""
        # Create user first
        user = self.manager.create_user_profile(
            user_id="revenue_user",
            email="revenue@example.com",
            tier=UserTier.PRO
        )

        # Record revenue event
        event_id = self.manager.record_revenue_event(
            user_id=user.user_id,
            event_type=RevenueEventType.SUBSCRIPTION,
            amount=Decimal("29.99"),
            metadata={"plan": "pro_monthly"}
        )

        self.assertIsNotNone(event_id)

    def test_referral_system_integrity(self):
        """Test referral system data integrity."""
        # Create referrer
        referrer = self.manager.create_user_profile(
            user_id="referrer_001",
            email="referrer@example.com",
            tier=UserTier.FOUNDING
        )

        # Create referred user
        referred = self.manager.create_user_profile(
            user_id="referred_001",
            email="referred@example.com",
            tier=UserTier.PRO,
            referred_by_code=referrer.referral_code
        )

        # Record revenue event for referred user
        event_id = self.manager.record_revenue_event(
            user_id=referred.user_id,
            event_type=RevenueEventType.SUBSCRIPTION,
            amount=Decimal("29.99")
        )

        # Check referral stats
        stats = self.manager.get_user_referral_stats(referrer.user_id)
        self.assertEqual(stats['total_referrals'], 1)
        self.assertGreater(stats['lifetime_referral_revenue'], 0)
        self.assertEqual(len(stats['referred_users']), 1)


class TestSecurityCompliance(unittest.TestCase):
    """Test enterprise security compliance features."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = Path(self.temp_dir.name) / "security_test.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_permissions(self):
        """Test that database files have secure permissions."""
        manager = SystemAlertManager(db_path=self.test_db_path)

        # Check database file permissions
        stat_info = self.test_db_path.stat()
        permissions = oct(stat_info.st_mode)[-3:]

        # Should be 600 (readable/writable by owner only)
        # Note: This test might fail on some systems/filesystems
        # that don't support Unix permissions
        if os.name != 'nt':  # Skip on Windows
            self.assertEqual(permissions, '600')

    def test_sql_injection_protection(self):
        """Test protection against SQL injection attempts."""
        manager = SystemAlertManager(db_path=self.test_db_path)

        # Attempt SQL injection in various fields
        # These should be safely escaped by parameterized queries
        malicious_inputs = [
            "'; DROP TABLE alerts; --",
            "'; INSERT INTO alerts VALUES (1,1,1,1,1,1,1,1,1,1); --",
            "' OR 1=1 --",
            "'; DELETE FROM user_profiles; --"
        ]

        for malicious_input in malicious_inputs:
            try:
                # These should not cause database corruption
                alert_id = manager.create_alert(
                    AlertType.SECURITY,
                    AlertSeverity.CRITICAL,
                    f"malicious_source_{malicious_input}",
                    f"Alert {malicious_input}",
                    f"Message {malicious_input}"
                )

                # If alert was created, verify database is still intact
                if alert_id > 0:
                    alerts = manager.query_alerts()
                    # Should still be able to query without errors
                    self.assertIsInstance(alerts, list)

            except (ValidationException, SecurityException):
                # Validation/security exceptions are expected and good
                pass

    def test_audit_logging(self):
        """Test that audit logging captures security events."""
        manager = SystemAlertManager(db_path=self.test_db_path)

        # Enable audit logging
        manager.security_config.audit_sensitive_operations = True

        # Perform auditable operations
        with patch('cx.system_alert_manager.logger') as mock_logger:
            manager.create_alert(
                AlertType.SECURITY,
                AlertSeverity.CRITICAL,
                "audit_test",
                "Audit Test Alert",
                "Testing audit logging"
            )

            # Verify audit log entries were created
            mock_logger.info.assert_called()

            # Check that audit messages contain operation name
            audit_calls = [call for call in mock_logger.info.call_args_list
                          if 'AUDIT:' in str(call)]
            self.assertGreater(len(audit_calls), 0)


if __name__ == '__main__':
    # Run comprehensive enterprise security tests
    unittest.main(verbosity=2)