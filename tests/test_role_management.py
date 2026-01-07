import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.role_manager import RoleManager


@pytest.fixture
def temp_cortex_dir(tmp_path):
    """Creates a temporary .cortex directory for testing."""
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    return cortex_dir


def test_role_detection(temp_cortex_dir):
    """Test that roles are detected when specific binaries exist."""
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Mock shutil.which to simulate 'nginx' being installed
    with patch("shutil.which", side_effect=lambda x: "/usr/bin/nginx" if x == "nginx" else None):
        detected = manager.detect_active_roles()
        assert "Web Server" in detected
        assert "ML Workstation" not in detected


def test_save_and_get_role(temp_cortex_dir):
    """Test persisting and retrieving the system role."""
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    manager.save_role("ml-workstation")
    assert manager.get_saved_role() == "ml-workstation"

    # Verify file content
    content = env_path.read_text()
    assert "CORTEX_SYSTEM_ROLE=ml-workstation" in content


def test_custom_role_loading(temp_cortex_dir):
    """Test that custom roles from JSON are merged correctly."""
    env_path = temp_cortex_dir / ".env"
    custom_file = temp_cortex_dir / "custom_roles.json"

    custom_data = {
        "DevOps": {
            "slug": "devops-tooling",
            "binaries": ["terraform"],
            "recommendations": ["Ansible", "Kubectl"],
        }
    }
    custom_file.write_text(json.dumps(custom_data))

    manager = RoleManager(env_path=env_path)
    assert "devops-tooling" in manager.get_all_slugs()
    assert "Ansible" in manager.get_recommendations_by_slug("devops-tooling")


def test_learn_package(temp_cortex_dir):
    """Test that the system learns new packages for a role.

    Verifies that learned packages are stored as a list keyed by the role slug
    in the learned_roles.json file.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Simulate learning a new package while the role is active
    manager.learn_package("web-server", "htop")

    learned_file = temp_cortex_dir / "learned_roles.json"
    assert learned_file.exists()

    # Parse the resulting JSON to verify structure
    data = json.loads(learned_file.read_text())

    # data["web-server"] is a list of strings
    assert "htop" in data["web-server"]


def test_error_handling_save_role(temp_cortex_dir):
    """Verifies that save_role raises an error when file I/O fails.

    This test uses mocking to simulate a permission failure, ensuring the
    application's error handling and logging logic are triggered.

    Args:
        temp_cortex_dir: Pytest fixture providing a temporary directory path.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # We mock the 'builtins.open' call specifically when it tries to open the lock file
    # to simulate a system-level permission or locking error.
    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        with pytest.raises(RuntimeError) as excinfo:
            manager.save_role("web-server")

        # Verify the error message matches what we expect in the class
        assert "Could not persist role" in str(excinfo.value)


def test_load_invalid_custom_roles(temp_cortex_dir):
    """Verifies the RoleManager handles malformed custom role JSON gracefully.

    Ensures that a JSONDecodeError in the custom roles file does not crash the
    application and that default roles remain accessible.

    Args:
        temp_cortex_dir: Pytest fixture providing a temporary directory path.
    """
    env_path = temp_cortex_dir / ".env"
    custom_file = temp_cortex_dir / "custom_roles.json"

    # Simulate a corrupted or malformed configuration file
    custom_file.write_text("{ invalid json ...")

    manager = RoleManager(env_path=env_path)
    # Validate that built-in roles still load correctly despite the custom file error
    assert "web-server" in manager.get_all_slugs()


def test_learn_package_json_error(temp_cortex_dir):
    """Verifies that learn_package handles malformed learned_roles JSON.

    Validates the json.JSONDecodeError exception block by attempting to append
    data to a corrupted history file.

    Args:
        temp_cortex_dir: Pytest fixture providing a temporary directory path.
    """
    env_path = temp_cortex_dir / ".env"
    learned_file = temp_cortex_dir / "learned_roles.json"
    learned_file.write_text("not json")

    manager = RoleManager(env_path=env_path)
    # The method should catch the error and overwrite/initialize a valid structure
    manager.learn_package("ml-workstation", "numpy")
    assert learned_file.exists()
