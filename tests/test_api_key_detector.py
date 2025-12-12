"""Tests for the API key auto-detection module.

Tests Issue #255: Auto-detect API keys from common locations
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from cortex.api_key_detector import (
    Provider,
    DetectedKey,
    APIKeyDetector,
    auto_configure_api_key,
    get_detection_summary,
    validate_detected_key,
    KEY_PATTERNS,
    ENV_VAR_NAMES,
)


class TestDetectedKey:
    """Tests for DetectedKey dataclass."""

    def test_masked_key_long(self):
        """Test key masking for long keys."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-api03-abcdefghijklmnop",
            source="~/.bashrc",
            env_var="ANTHROPIC_API_KEY"
        )
        masked = key.masked_key
        assert masked.startswith("sk-ant-a")
        assert masked.endswith("mnop")
        assert "..." in masked

    def test_masked_key_short(self):
        """Test key masking for short keys."""
        key = DetectedKey(
            provider=Provider.OPENAI,
            key="sk-short",
            source="test",
            env_var="OPENAI_API_KEY"
        )
        masked = key.masked_key
        assert masked == "********"


class TestKeyPatterns:
    """Tests for API key regex patterns."""

    def test_anthropic_export_pattern(self):
        """Test Anthropic key detection with export."""
        import re
        content = 'export ANTHROPIC_API_KEY="sk-ant-api03-test123"'
        for pattern in KEY_PATTERNS[Provider.ANTHROPIC]:
            match = re.search(pattern, content)
            if match:
                assert match.group(1) == "sk-ant-api03-test123"
                return
        pytest.fail("Pattern should match export statement")

    def test_anthropic_simple_pattern(self):
        """Test Anthropic key detection without export."""
        import re
        content = "ANTHROPIC_API_KEY=sk-ant-api03-simple"
        for pattern in KEY_PATTERNS[Provider.ANTHROPIC]:
            match = re.search(pattern, content)
            if match:
                assert match.group(1) == "sk-ant-api03-simple"
                return
        pytest.fail("Pattern should match simple assignment")

    def test_openai_export_pattern(self):
        """Test OpenAI key detection with export."""
        import re
        content = "export OPENAI_API_KEY='sk-proj-test456'"
        for pattern in KEY_PATTERNS[Provider.OPENAI]:
            match = re.search(pattern, content)
            if match:
                assert match.group(1) == "sk-proj-test456"
                return
        pytest.fail("Pattern should match export statement")

    def test_env_file_format(self):
        """Test key detection in .env file format."""
        import re
        content = 'ANTHROPIC_API_KEY="sk-ant-test-envfile"'
        for pattern in KEY_PATTERNS[Provider.ANTHROPIC]:
            match = re.search(pattern, content)
            if match:
                assert "sk-ant-test-envfile" in match.group(1)
                return
        pytest.fail("Pattern should match .env format")


class TestAPIKeyDetector:
    """Tests for APIKeyDetector class."""

    def test_detect_from_environment_anthropic(self):
        """Test detection from ANTHROPIC_API_KEY env var."""
        detector = APIKeyDetector()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-env-key"}, clear=True):
            keys = detector.detect_from_environment()

        assert len(keys) == 1
        assert keys[0].provider == Provider.ANTHROPIC
        assert keys[0].key == "sk-ant-test-env-key"
        assert keys[0].source == "environment variable"

    def test_detect_from_environment_openai(self):
        """Test detection from OPENAI_API_KEY env var."""
        detector = APIKeyDetector()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-test-key"}, clear=False):
            # Clear anthropic key if present
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            env["OPENAI_API_KEY"] = "sk-openai-test-key"

            with patch.dict(os.environ, env, clear=True):
                keys = detector.detect_from_environment()

        openai_keys = [k for k in keys if k.provider == Provider.OPENAI]
        assert len(openai_keys) == 1
        assert openai_keys[0].key == "sk-openai-test-key"

    def test_detect_from_environment_both(self):
        """Test detection when both keys are set."""
        detector = APIKeyDetector()

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-both-test",
            "OPENAI_API_KEY": "sk-both-openai"
        }, clear=True):
            keys = detector.detect_from_environment()

        assert len(keys) == 2
        providers = {k.provider for k in keys}
        assert Provider.ANTHROPIC in providers
        assert Provider.OPENAI in providers

    def test_detect_from_environment_invalid_prefix(self):
        """Test that invalid prefixes are not detected."""
        detector = APIKeyDetector()

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "invalid-key-no-prefix"
        }, clear=True):
            keys = detector.detect_from_environment()

        assert len(keys) == 0

    def test_detect_from_file(self):
        """Test detection from a file."""
        detector = APIKeyDetector()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('export ANTHROPIC_API_KEY="sk-ant-file-test-key"\n')
            f.write('# Some comment\n')
            f.write('OTHER_VAR=value\n')
            temp_path = f.name

        try:
            keys = detector._search_file(Path(temp_path))
            assert len(keys) == 1
            assert keys[0].provider == Provider.ANTHROPIC
            assert keys[0].key == "sk-ant-file-test-key"
            assert temp_path in keys[0].source
        finally:
            os.unlink(temp_path)

    def test_detect_from_file_multiple_keys(self):
        """Test detection of multiple keys from one file."""
        detector = APIKeyDetector()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('ANTHROPIC_API_KEY=sk-ant-multi-1\n')
            f.write('OPENAI_API_KEY=sk-multi-openai\n')
            temp_path = f.name

        try:
            keys = detector._search_file(Path(temp_path))
            assert len(keys) == 2
        finally:
            os.unlink(temp_path)

    def test_detect_from_nonexistent_file(self):
        """Test that nonexistent files return empty list."""
        detector = APIKeyDetector()
        keys = detector._search_file(Path("/nonexistent/path/file"))
        assert keys == []

    def test_additional_paths(self):
        """Test custom additional search paths."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('ANTHROPIC_API_KEY=sk-ant-custom-path\n')
            temp_path = f.name

        try:
            detector = APIKeyDetector(additional_paths=[temp_path])
            assert Path(temp_path) in detector.search_paths
        finally:
            os.unlink(temp_path)

    def test_detect_all_deduplicates(self):
        """Test that detect_all removes duplicate keys."""
        detector = APIKeyDetector()

        # Mock both methods to return the same key
        same_key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-duplicate-key",
            source="env",
            env_var="ANTHROPIC_API_KEY"
        )

        with patch.object(detector, 'detect_from_environment', return_value=[same_key]):
            with patch.object(detector, 'detect_from_files', return_value=[same_key]):
                keys = detector.detect_all()

        # Should only have one key despite being found twice
        assert len(keys) == 1

    def test_get_best_key_prefers_anthropic(self):
        """Test that Anthropic keys are preferred by default."""
        detector = APIKeyDetector()

        anthropic_key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-preferred",
            source="env",
            env_var="ANTHROPIC_API_KEY"
        )
        openai_key = DetectedKey(
            provider=Provider.OPENAI,
            key="sk-not-preferred",
            source="env",
            env_var="OPENAI_API_KEY"
        )

        with patch.object(detector, 'detect_all', return_value=[openai_key, anthropic_key]):
            best = detector.get_best_key()

        assert best.provider == Provider.ANTHROPIC

    def test_get_best_key_respects_preference(self):
        """Test that preferred provider is respected."""
        detector = APIKeyDetector()

        anthropic_key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-key",
            source="env",
            env_var="ANTHROPIC_API_KEY"
        )
        openai_key = DetectedKey(
            provider=Provider.OPENAI,
            key="sk-openai-key",
            source="env",
            env_var="OPENAI_API_KEY"
        )

        with patch.object(detector, 'detect_all', return_value=[anthropic_key, openai_key]):
            best = detector.get_best_key(preferred_provider=Provider.OPENAI)

        assert best.provider == Provider.OPENAI

    def test_get_best_key_no_keys(self):
        """Test get_best_key when no keys available."""
        detector = APIKeyDetector()

        with patch.object(detector, 'detect_all', return_value=[]):
            best = detector.get_best_key()

        assert best is None


class TestAutoConfigureApiKey:
    """Tests for auto_configure_api_key function."""

    def test_auto_configure_sets_env(self):
        """Test that auto_configure sets environment variable."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-auto-config",
            source="test",
            env_var="ANTHROPIC_API_KEY"
        )

        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.get_best_key.return_value = key

            # Clear the env var first
            with patch.dict(os.environ, {}, clear=True):
                result = auto_configure_api_key(set_env=True)

                assert result == key
                assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-auto-config"

    def test_auto_configure_no_set_env(self):
        """Test auto_configure with set_env=False."""
        key = DetectedKey(
            provider=Provider.OPENAI,
            key="sk-no-set-env",
            source="test",
            env_var="OPENAI_API_KEY"
        )

        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.get_best_key.return_value = key

            with patch.dict(os.environ, {}, clear=True):
                result = auto_configure_api_key(set_env=False)

                assert result == key
                assert "OPENAI_API_KEY" not in os.environ

    def test_auto_configure_no_key_found(self):
        """Test auto_configure when no key is found."""
        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.get_best_key.return_value = None

            result = auto_configure_api_key()

            assert result is None

    def test_auto_configure_preferred_provider(self):
        """Test auto_configure with preferred provider."""
        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.get_best_key.return_value = None

            auto_configure_api_key(preferred_provider="openai")

            mock_instance.get_best_key.assert_called_with(
                preferred_provider=Provider.OPENAI
            )


class TestGetDetectionSummary:
    """Tests for get_detection_summary function."""

    def test_summary_with_keys(self):
        """Test summary when keys are found."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-summary-test",
            source="~/.bashrc",
            env_var="ANTHROPIC_API_KEY"
        )

        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.detect_all.return_value = [key]
            mock_instance.search_paths = []

            summary = get_detection_summary()

        assert summary["found"] is True
        assert summary["count"] == 1
        assert len(summary["keys"]) == 1
        assert summary["keys"][0]["provider"] == "anthropic"

    def test_summary_no_keys(self):
        """Test summary when no keys found."""
        with patch('cortex.api_key_detector.APIKeyDetector') as MockDetector:
            mock_instance = MockDetector.return_value
            mock_instance.detect_all.return_value = []
            mock_instance.search_paths = []

            summary = get_detection_summary()

        assert summary["found"] is False
        assert summary["count"] == 0


class TestValidateDetectedKey:
    """Tests for validate_detected_key function."""

    def test_valid_anthropic_key(self):
        """Test validation of valid Anthropic key."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-api03-validkey12345678",
            source="test",
            env_var="ANTHROPIC_API_KEY"
        )
        is_valid, error = validate_detected_key(key)
        assert is_valid is True
        assert error is None

    def test_valid_openai_key(self):
        """Test validation of valid OpenAI key."""
        key = DetectedKey(
            provider=Provider.OPENAI,
            key="sk-proj-validkey123456789012",
            source="test",
            env_var="OPENAI_API_KEY"
        )
        is_valid, error = validate_detected_key(key)
        assert is_valid is True
        assert error is None

    def test_invalid_anthropic_prefix(self):
        """Test validation fails for wrong Anthropic prefix."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-wrong-prefix123456789",
            source="test",
            env_var="ANTHROPIC_API_KEY"
        )
        is_valid, error = validate_detected_key(key)
        assert is_valid is False
        assert "sk-ant-" in error

    def test_invalid_openai_prefix(self):
        """Test validation fails for wrong OpenAI prefix."""
        key = DetectedKey(
            provider=Provider.OPENAI,
            key="wrong-openai-key12345",
            source="test",
            env_var="OPENAI_API_KEY"
        )
        is_valid, error = validate_detected_key(key)
        assert is_valid is False
        assert "sk-" in error

    def test_short_key(self):
        """Test validation fails for too short key."""
        key = DetectedKey(
            provider=Provider.ANTHROPIC,
            key="sk-ant-short",
            source="test",
            env_var="ANTHROPIC_API_KEY"
        )
        is_valid, error = validate_detected_key(key)
        assert is_valid is False
        assert "short" in error.lower()


class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_bashrc_detection(self):
        """Test detecting key from a realistic .bashrc file."""
        bashrc_content = """
# ~/.bashrc

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# API Keys
export ANTHROPIC_API_KEY="sk-ant-api03-realkey123456789"

# Aliases
alias ll='ls -la'
"""
        detector = APIKeyDetector()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.bashrc', delete=False) as f:
            f.write(bashrc_content)
            temp_path = f.name

        try:
            keys = detector._search_file(Path(temp_path))
            assert len(keys) == 1
            assert keys[0].key == "sk-ant-api03-realkey123456789"
        finally:
            os.unlink(temp_path)

    def test_env_file_detection(self):
        """Test detecting key from a realistic .env file."""
        env_content = """
# Environment variables for development
DATABASE_URL=postgres://localhost/dev
REDIS_URL=redis://localhost:6379

# LLM API Keys
ANTHROPIC_API_KEY=sk-ant-api03-envfilekey789
OPENAI_API_KEY=sk-proj-envfilekey123

# Feature flags
DEBUG=true
"""
        detector = APIKeyDetector()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            temp_path = f.name

        try:
            keys = detector._search_file(Path(temp_path))
            assert len(keys) == 2

            providers = {k.provider for k in keys}
            assert Provider.ANTHROPIC in providers
            assert Provider.OPENAI in providers
        finally:
            os.unlink(temp_path)
