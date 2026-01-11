import re
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.role_manager import RoleManager


@pytest.fixture
def temp_cortex_dir(tmp_path):
    """
    Creates a temporary directory for testing file I/O.

    This prevents the tests from writing to or reading from the actual
    user home directory (~/.cortex), ensuring a clean, isolated environment.
    """
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    return cortex_dir


@pytest.fixture
def role_manager(temp_cortex_dir):
    """
    Provides a pre-configured RoleManager instance.

    The instance is pointed to a temporary .env file within the test-isolated
    directory to prevent accidental side effects on the host system.
    """
    env_path = temp_cortex_dir / ".env"
    return RoleManager(env_path=env_path)


def test_get_system_context_fact_gathering(temp_cortex_dir):
    """
    Verifies that RoleManager correctly aggregates system facts and active persona.

    Ensures that the 'Sensing Layer' accurately detects present binaries,
    identifies hardware acceleration flags, and tokenizes shell history patterns
    into a synchronized Single Source of Truth for the AI.
    """
    env_path = temp_cortex_dir / ".env"
    manager = RoleManager(env_path=env_path)

    # Patch shutil.which to simulate binary presence and Path.home to redirect I/O
    with (
        patch("cortex.role_manager.shutil.which") as mock_which,
        patch("cortex.role_manager.Path.home", return_value=temp_cortex_dir),
    ):
        # Create a mock history file to test activity pattern sensing
        bash_history = temp_cortex_dir / ".bash_history"
        bash_history.write_text("git commit -m 'feat'\npip install torch\n", encoding="utf-8")

        # Simulate a environment where Nginx is present but GPU tools are not
        mock_which.side_effect = lambda x: "/usr/bin/" + x if x in ["nginx"] else None

        context = manager.get_system_context()

        # Factual Validation
        assert "nginx" in context["binaries"]
        assert context["has_gpu"] is False
        assert "intent:version_control" in context["patterns"]
        assert context["active_role"] == "undefined"


def test_get_shell_patterns_privacy_hardening(role_manager, temp_cortex_dir, monkeypatch):
    """
    Tests the privacy-hardening and normalization logic of shell history sensing.

    Validates:
    1. Zsh extended history metadata (epochs/timestamps) is stripped.
    2. Leading environment variable assignments (e.g., API keys) are removed.
    3. Absolute paths are reduced to their basenames to hide local directory structures.
    4. Malformed quotes are handled gracefully without crashing shlex.
    """
    monkeypatch.setattr("cortex.role_manager.Path.home", lambda: temp_cortex_dir)

    history_file = temp_cortex_dir / ".bash_history"
    # Mixed data: Zsh format, ENV assignment, Absolute Path, and a Malformed Quote
    content = (
        ": 1612345678:0;git pull\n"
        "DATABASE_URL=secret psql -d db\n"
        "/usr/local/bin/docker build .\n"
        "echo 'unclosed quote\n"
    )
    history_file.write_text(content, encoding="utf-8")

    patterns = role_manager._get_shell_patterns()

    # Verify metadata and path stripping
    assert "intent:version_control" in patterns  # ": 16123...;git" -> "git"
    assert "intent:psql" in patterns  # "DB_URL=... psql" -> "psql"
    assert "intent:container" in patterns  # "docker" is mapped to "container"
    assert "intent:echo" in patterns  # Fallback for quoting errors


def test_get_shell_patterns_failure_handling(role_manager, temp_cortex_dir, monkeypatch):
    """
    Verifies the robustness of the sensing layer under restricted environments.

    Ensures that RoleManager does not crash if history files exist but are
    unreadable due to PermissionErrors, instead returning an empty pattern list.
    """
    monkeypatch.setattr("cortex.role_manager.Path.home", lambda: temp_cortex_dir)
    history_file = temp_cortex_dir / ".bash_history"
    history_file.touch()

    # Simulate a file that exists but cannot be read by the current user
    with patch.object(Path, "read_text", side_effect=PermissionError("Access Denied")):
        patterns = role_manager._get_shell_patterns()
        assert patterns == []


def test_save_role_formatting_preservation(role_manager, temp_cortex_dir):
    """
    Tests that RoleManager respects and preserves existing shell formatting.

    Verifies that updating a role in a file that already uses 'export' and
    quotes does not overwrite the line with a generic 'KEY=VALUE' format,
    preserving the user's manual style choices.
    """
    env_path = temp_cortex_dir / ".env"
    env_path.write_text('export CORTEX_SYSTEM_ROLE="initial"\n', encoding="utf-8")

    role_manager.save_role("updated")

    content = env_path.read_text()
    # Ensure update happened while maintaining 'export' and double quotes
    assert 'export CORTEX_SYSTEM_ROLE="updated"' in content
    # Verify no line duplication occurred
    assert content.count("CORTEX_SYSTEM_ROLE") == 1


def test_get_saved_role_tolerant_parsing_advanced(role_manager, temp_cortex_dir):
    """
    Verifies the tolerant parsing logic for existing environment files.

    Validates that the parser:
    1. Ignores inline comments.
    2. Handles flexible whitespace around the equals sign.
    3. Respects shell semantics where the 'last' match in the file wins.
    """
    env_path = temp_cortex_dir / ".env"
    content = (
        "CORTEX_SYSTEM_ROLE=first\n"
        "export CORTEX_SYSTEM_ROLE = 'second' # Manual override comment\n"
    )
    env_path.write_text(content, encoding="utf-8")

    # 'second' should win as it is defined last
    assert role_manager.get_saved_role() == "second"


def test_locked_write_concurrency_degraded_logging(role_manager, monkeypatch, caplog):
    """
    Verifies the system's ability to signal safety risks in exotic environments.

    Tests the scenario where neither fcntl (POSIX) nor msvcrt (Windows) locking
    backends are available, ensuring the system logs a warning about degraded
    concurrency protection.
    """
    monkeypatch.setattr("cortex.role_manager.fcntl", None)
    monkeypatch.setattr("cortex.role_manager.msvcrt", None)

    role_manager.save_role("test-role")
    # Verify the warning was issued to the log
    assert "No file locking backend available" in caplog.text


def test_error_handling_atomic_write(role_manager):
    """
    Ensures file I/O failures are wrapped in RuntimeErrors with context.

    Validates that system-level errors (like a full disk) are caught during
    the atomic write process and reported back to the CLI with a helpful message.
    """
    with patch("builtins.open", side_effect=OSError("Disk Full")):
        with pytest.raises(RuntimeError, match="Could not persist role"):
            role_manager.save_role("any-role")


def test_get_system_context_no_history(role_manager, temp_cortex_dir, monkeypatch):
    """
    Validates context gathering functionality for new/clean installations.

    Gathering context should still work smoothly if no shell history files or
    binaries are present, reverting to 'undefined' persona states.
    """
    monkeypatch.setattr("cortex.role_manager.Path.exists", lambda x: False)
    context = role_manager.get_system_context()

    assert context["patterns"] == []
    assert context["active_role"] == "undefined"


def test_save_role_slug_validation(role_manager):
    """
    Test the boundary validation for role identifiers (slugs).

    Ensures that only safe alphanumeric strings with mid-string dashes/underscores
    are allowed, preventing malicious injection or malformed identifiers.
    """
    # Valid variants
    valid_slugs = ["ml", "ML-Workstation", "dev_ops", "a"]
    for slug in valid_slugs:
        role_manager.save_role(slug)
        assert role_manager.get_saved_role() == slug

    # Invalid variants (starting/ending with special chars or newline injection)
    invalid_slugs = ["-dev", "dev-", "dev\n", "role!", ""]
    for slug in invalid_slugs:
        with pytest.raises(ValueError):
            role_manager.save_role(slug)


def test_shell_pattern_redaction_robustness(role_manager, temp_cortex_dir, monkeypatch):
    """
    Verifies per-line PII redaction and exact placeholder mapping.

    Ensures that sensitive technical commands (containing keys/secrets) are
    replaced by a hardcoded placeholder, while maintaining the correct sequence
    of the activity history.
    """
    monkeypatch.setattr("cortex.role_manager.Path.home", lambda: temp_cortex_dir)
    bash_history = temp_cortex_dir / ".bash_history"
    leaking_commands = (
        "export MY_API_KEY=abc123\n" 'curl -H "X-Api-Key: secret" http://api.com\n' "ls -la\n"
    )
    bash_history.write_text(leaking_commands, encoding="utf-8")

    patterns = role_manager._get_shell_patterns()

    # Secrets must be unreachable
    assert not any("abc123" in p for p in patterns)
    assert patterns.count("<redacted>") == 2
    assert "intent:ls" in patterns


def test_get_shell_patterns_opt_out(role_manager, monkeypatch):
    """
    Verify the privacy opt-out mechanism via environment flag.
    """
    monkeypatch.setenv("CORTEX_SENSE_HISTORY", "false")
    assert role_manager._get_shell_patterns() == []


def test_locked_write_windows_fallback(role_manager, monkeypatch):
    """
    Mocks the Windows NT platform to verify msvcrt locking path coverage.

    Ensures that when running on a Windows environment, the RoleManager
    correctly switches from fcntl to the msvcrt byte-range locking backend.
    """
    mock_msvcrt = MagicMock()
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("cortex.role_manager.msvcrt", mock_msvcrt)
    monkeypatch.setattr("cortex.role_manager.fcntl", None)

    role_manager.save_role("win-test")
    # Verify msvcrt.locking was the backend utilized
    assert mock_msvcrt.locking.called


def test_get_shell_patterns_corrupted_data(role_manager, temp_cortex_dir, monkeypatch):
    """
    Verify stability when history files contain binary or non-UTF-8 data.

    Ensures the 'replace' error handler correctly swaps corrupted bytes for
    Unicode replacement characters rather than raising a decoding exception.
    """
    monkeypatch.setattr("pathlib.Path.home", lambda: temp_cortex_dir)
    history_file = temp_cortex_dir / ".bash_history"

    # Write explicit binary corruption between two valid commands
    history_file.write_bytes(b"ls -la\n\xff\xfe\xfd\ngit commit -m 'test'")

    patterns = role_manager._get_shell_patterns()
    assert "intent:ls" in patterns
    assert "intent:version_control" in patterns
