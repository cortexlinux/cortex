import os
from unittest.mock import MagicMock, patch

import pytest

from cortex.permission_manager import PermissionManager


@pytest.fixture
def manager():
    """Fixture to initialize PermissionManager with a dummy path."""
    # Use normpath to ensure slashes are correct for the current OS
    return PermissionManager(os.path.normpath("/dummy/path"))


def test_diagnose_finds_root_files(manager):
    """Test that diagnose correctly identifies root-owned files (UID 0)."""
    with patch("os.walk") as mock_walk, patch("os.stat") as mock_stat:

        # Build paths dynamically based on the OS
        base = os.path.normpath("/dummy/path")
        locked_file = os.path.join(base, "locked.txt")
        normal_file = os.path.join(base, "normal.txt")

        # Mocking a directory structure
        mock_walk.return_value = [(base, [], ["locked.txt", "normal.txt"])]

        # Define mock stat objects
        root_stat = MagicMock()
        root_stat.st_uid = 0  # Root UID

        user_stat = MagicMock()
        user_stat.st_uid = 1000  # Normal User UID

        # side_effect returns root_stat for the first call, user_stat for the second
        mock_stat.side_effect = [root_stat, user_stat]

        results = manager.diagnose()

        assert len(results) == 1
        # Use normpath for the comparison to prevent / vs \ failures
        assert os.path.normpath(locked_file) in [os.path.normpath(r) for r in results]


def test_check_compose_config_suggests_fix(manager, capsys):
    """Test that it detects missing 'user:' in docker-compose.yml."""
    with (
        patch("os.path.exists", return_value=True),
        patch(
            "builtins.open",
            MagicMock(
                return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: "version: '3'"))
            ),
        ),
    ):

        manager.check_compose_config()
        # Verify the tip is printed to the console
        captured = capsys.readouterr()


@patch("subprocess.run")
@patch("platform.system", return_value="Linux")
def test_fix_permissions_executes_chown(mock_platform, mock_run, manager):
    """Test that fix_permissions triggers the correct sudo chown command."""
    # 'create=True' allows us to mock getuid/getgid even on Windows
    with (
        patch("os.getuid", create=True, return_value=1000),
        patch("os.getgid", create=True, return_value=1000),
    ):

        test_file = os.path.normpath("/path/to/file1.txt")
        files = [test_file]
        success = manager.fix_permissions(files)

        assert success is True
        # Ensure chown uses correct UID:GID and flags
        mock_run.assert_called_once_with(
            ["sudo", "chown", "1000:1000", test_file], check=True, capture_output=True
        )
