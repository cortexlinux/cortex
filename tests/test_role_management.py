import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.role_manager import RoleManager


@pytest.fixture
def temp_cortex_dir(tmp_path):
    """Creates a temporary directory for testing file I/O to avoid polluting user home."""
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    return cortex_dir


def test_get_system_context_fact_gathering(temp_cortex_dir):
    """
    Verifies that RoleManager correctly aggregates system facts and active persona.
    Ensures the 'Sensing Layer' provides a synchronized Single Source of Truth to the AI.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # REFINEMENT: Use real files in tmp_path instead of broad global Path mocks
    # Patch Path.home to redirect home-directory lookups to the isolated test directory
    with (
        patch("cortex.role_manager.shutil.which") as mock_which,
        patch("cortex.role_manager.Path.home", return_value=temp_cortex_dir),
    ):
        # Create a real history file in the temporary directory to ensure realistic testing
        bash_history = temp_cortex_dir / ".bash_history"
        bash_history.write_text("git commit -m 'feat'\npip install torch\n", encoding="utf-8")

        # Simulate environment state (Nginx present, No GPU)
        mock_which.side_effect = lambda x: "/usr/bin/" + x if x in ["nginx"] else None

        context = manager.get_system_context()

        # Synchronized Validation: Verify binary detection, hardware flags, and activity patterns
        assert "nginx" in context["binaries"]
        assert "nvidia-smi" not in context["binaries"]
        assert context["has_gpu"] is False
        assert "git commit -m 'feat'" in context["patterns"]
        assert context["active_role"] == "undefined"


def test_get_shell_patterns_failure_handling(temp_cortex_dir):
    """
    Verifies defensive programming: sensing should not crash if history files are unreadable.
    This satisfies robustness requirements for varied Linux environments.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # REFINEMENT: Let the file actually exist in the temp directory to avoid global Path.exists mocks
    history_file = temp_cortex_dir / ".bash_history"
    history_file.touch()

    # Use patch.home to redirect lookups and patch.object for targeted failure simulation
    with (
        patch("cortex.role_manager.Path.home", return_value=temp_cortex_dir),
        patch.object(Path, "read_text", side_effect=PermissionError("Access Denied")),
    ):
        # Should return an empty list instead of raising PermissionError
        patterns = manager._get_shell_patterns()
        assert patterns == []


def test_save_and_update_existing_role(temp_cortex_dir):
    """
    Tests the Regex logic to ensure roles are updated atomically without line duplication.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Initial save
    manager.save_role("developer")
    assert manager.get_saved_role() == "developer"

    # Update existing role (verifies pattern substitution)
    manager.save_role("data-scientist")
    assert manager.get_saved_role() == "data-scientist"

    content = env_path.read_text()
    # Ensure it replaced the key rather than appending a second one
    assert content.count("CORTEX_SYSTEM_ROLE") == 1


def test_save_role_append_to_existing_env(temp_cortex_dir):
    """Tests saving a role without overwriting other unrelated environment variables."""
    env_path = temp_cortex_dir / ".env"
    env_path.write_text("API_KEY=12345\n")

    manager = RoleManager(env_path=env_path)
    manager.save_role("web-server")

    content = env_path.read_text()
    assert "API_KEY=12345" in content
    assert "CORTEX_SYSTEM_ROLE=web-server" in content


def test_error_handling_atomic_write(temp_cortex_dir):
    """
    Ensures file I/O failures are wrapped in RuntimeErrors with clear context.
    Verifies the system doesn't crash but reports the failure to the CLI logic.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Mock open to simulate a file lock or read-only file system
    with patch("builtins.open", side_effect=PermissionError("File Locked")):
        with pytest.raises(RuntimeError) as excinfo:
            manager.save_role("any-role")

        assert "Could not persist role" in str(excinfo.value)
        # Verify exception chaining (ensures 'from e' was used)
        assert isinstance(excinfo.value.__cause__, PermissionError)


def test_get_saved_role_file_not_found(temp_cortex_dir):
    """Ensures logic handles missing .env files gracefully by returning None."""
    env_path = temp_cortex_dir / "missing.env"
    manager = RoleManager(env_path=env_path)

    assert manager.get_saved_role() is None


def test_role_persistence_idempotency(temp_cortex_dir):
    """Verifies that re-setting the same role is idempotent and doesn't bloat the file."""
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    manager.save_role("developer")
    manager.save_role("developer")

    content = env_path.read_text()
    assert content.count("CORTEX_SYSTEM_ROLE=developer") == 1


def test_get_system_context_no_history(temp_cortex_dir):
    """
    Ensures context gathering works even if shell history files do not exist.
    Tests the transition to 'undefined' role for first-time users.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Simulate missing history files and missing binaries
    with (
        patch("cortex.role_manager.Path.exists", return_value=False),
        patch("cortex.role_manager.shutil.which", return_value=None),
    ):

        context = manager.get_system_context()
        assert context["patterns"] == []
        assert context["active_role"] == "undefined"


def test_save_role_key_in_value_edge_case(temp_cortex_dir):
    """Ensure key detection doesn't match key names within other values."""
    env_path = temp_cortex_dir / ".env"
    env_path.write_text("OTHER_KEY=contains_CORTEX_SYSTEM_ROLE_text\n")

    manager = RoleManager(env_path=env_path)
    manager.save_role("web-server")

    content = env_path.read_text()
    # Should have exactly one CORTEX_SYSTEM_ROLE at line start
    assert content.count("CORTEX_SYSTEM_ROLE=") == 1
    assert "CORTEX_SYSTEM_ROLE=web-server" in content
