"""
Tests for permission configuration module.
"""

import pytest

from cortex.permissions import config


def test_dangerous_permissions():
    """Test DANGEROUS_PERMISSIONS dictionary"""
    assert 0o777 in config.DANGEROUS_PERMISSIONS
    assert 0o666 in config.DANGEROUS_PERMISSIONS
    assert 0o000 in config.DANGEROUS_PERMISSIONS

    # Check descriptions contain relevant info
    desc_777 = config.DANGEROUS_PERMISSIONS[0o777]
    desc_666 = config.DANGEROUS_PERMISSIONS[0o666]

    assert isinstance(desc_777, str)
    assert isinstance(desc_666, str)
    assert "rwx" in desc_777.lower() or "777" in desc_777
    assert "rw-" in desc_666.lower() or "666" in desc_666


def test_world_writable_flag():
    """Test WORLD_WRITABLE_FLAG"""
    import stat

    assert config.WORLD_WRITABLE_FLAG == 0o002
    assert config.WORLD_WRITABLE_FLAG == stat.S_IWOTH


def test_ignore_patterns():
    """Test IGNORE_PATTERNS list"""
    assert isinstance(config.IGNORE_PATTERNS, list)
    assert len(config.IGNORE_PATTERNS) > 0

    # Check some common patterns
    assert any("/proc/" in p for p in config.IGNORE_PATTERNS)
    assert any(".git/" in p for p in config.IGNORE_PATTERNS)
    assert any("__pycache__" in p for p in config.IGNORE_PATTERNS)


def test_sensitive_files():
    """Test SENSITIVE_FILES list"""
    assert isinstance(config.SENSITIVE_FILES, list)
    assert ".env" in config.SENSITIVE_FILES
    assert ".ssh/id_rsa" in config.SENSITIVE_FILES


def test_recommended_permissions():
    """Test RECOMMENDED_PERMISSIONS dictionary"""
    assert "directory" in config.RECOMMENDED_PERMISSIONS
    assert "executable" in config.RECOMMENDED_PERMISSIONS
    assert "config_file" in config.RECOMMENDED_PERMISSIONS
    assert "secret_file" in config.RECOMMENDED_PERMISSIONS

    assert config.RECOMMENDED_PERMISSIONS["directory"] == 0o755
    assert config.RECOMMENDED_PERMISSIONS["secret_file"] == 0o600


def test_docker_recommended_permissions():
    """Test DOCKER_RECOMMENDED_PERMISSIONS"""
    assert "volume_directory" in config.DOCKER_RECOMMENDED_PERMISSIONS
    assert "compose_file" in config.DOCKER_RECOMMENDED_PERMISSIONS
    assert config.DOCKER_RECOMMENDED_PERMISSIONS["compose_file"] == 0o644
