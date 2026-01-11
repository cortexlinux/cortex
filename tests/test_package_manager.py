import pytest
from unittest.mock import MagicMock, patch, call
from cortex.package_manager import UnifiedPackageManager

@pytest.fixture
def package_manager():
    return UnifiedPackageManager()

@pytest.fixture
def mock_subprocess():
    with patch("subprocess.check_call") as mock:
        yield mock

@pytest.fixture
def mock_shutil():
    with patch("shutil.which") as mock:
        yield mock

class TestUnifiedPackageManager:
    def test_init_detects_backends(self, mock_shutil):
        # Setup
        mock_shutil.side_effect = lambda x: "/usr/bin/" + x if x in ["snap", "flatpak"] else None
        
        # Execute
        pm = UnifiedPackageManager()
        
        # Verify
        assert pm.snap_avail is True
        assert pm.flatpak_avail is True

    def test_init_detects_missing_backends(self, mock_shutil):
        # Setup
        mock_shutil.return_value = None
        
        # Execute
        pm = UnifiedPackageManager()
        
        # Verify
        assert pm.snap_avail is False
        assert pm.flatpak_avail is False

    @patch("cortex.package_manager.Prompt.ask")
    def test_install_snap_choice(self, mock_prompt, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = True
        package_manager.flatpak_avail = True
        mock_prompt.return_value = "snap"
        
        # Execute
        package_manager.install("vlc")
        
        # Verify
        mock_subprocess.assert_called_with(["sudo", "snap", "install", "vlc"], timeout=300)

    @patch("cortex.package_manager.Prompt.ask")
    def test_install_flatpak_choice(self, mock_prompt, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = True
        package_manager.flatpak_avail = True
        mock_prompt.return_value = "flatpak"
        
        # Execute
        package_manager.install("vlc")
        
        # Verify
        # Default scope is user
        mock_subprocess.assert_called_with(["flatpak", "install", "-y", "--user", "vlc"], timeout=300)

    def test_install_flatpak_system_scope(self, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = False
        package_manager.flatpak_avail = True
        
        # Execute
        package_manager.install("vlc", scope="system")
        
        # Verify
        mock_subprocess.assert_called_with(["flatpak", "install", "-y", "--system", "vlc"], timeout=300)

    def test_remove_snap(self, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = True
        package_manager.flatpak_avail = False
        
        # Execute
        package_manager.remove("vlc")
        
        # Verify
        mock_subprocess.assert_called_with(["sudo", "snap", "remove", "vlc"], timeout=300)

    def test_validation_invalid_package(self, package_manager, mock_subprocess):
        # Execute
        package_manager.install("vlc; rm -rf /")
        
        # Verify
        mock_subprocess.assert_not_called()

    def test_validation_valid_package(self, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = True
        package_manager.flatpak_avail = False
        
        # Execute
        package_manager.install("vlc-media_player.1")
        
        # Verify
        mock_subprocess.assert_called()

    def test_dry_run(self, package_manager, mock_subprocess):
        # Setup
        package_manager.snap_avail = True
        package_manager.flatpak_avail = False
        
        # Execute
        package_manager.install("vlc", dry_run=True)
        
        # Verify
        mock_subprocess.assert_not_called()

    def test_list_packages(self, package_manager):
        # Just ensure it runs without error (prints to console)
        package_manager.list_packages()

    def test_check_permissions(self, package_manager):
        # Just ensure it runs without error
        package_manager.check_permissions("vlc")
