"""
Unit tests for cortex/systemd_helper.py - Systemd Service Helper.
Tests the SystemdHelper class used by 'cortex systemd' commands.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cortex.systemd_helper import (
    ServiceState,
    ServiceStatus,
    SystemdHelper,
    run_deps_command,
    run_diagnose_command,
    run_generate_command,
    run_status_command,
)


class TestServiceStateEnum:
    """Test the ServiceState enum values."""

    def test_all_states_exist(self):
        assert ServiceState.RUNNING.value == "running"
        assert ServiceState.STOPPED.value == "stopped"
        assert ServiceState.FAILED.value == "failed"
        assert ServiceState.INACTIVE.value == "inactive"
        assert ServiceState.ACTIVATING.value == "activating"
        assert ServiceState.DEACTIVATING.value == "deactivating"
        assert ServiceState.UNKNOWN.value == "unknown"


class TestServiceStatusDataclass:
    """Test the ServiceStatus dataclass."""

    def test_basic_creation(self):
        status = ServiceStatus(
            name="nginx",
            state=ServiceState.RUNNING,
        )
        assert status.name == "nginx"
        assert status.state == ServiceState.RUNNING
        assert status.description == ""
        assert status.pid is None

    def test_full_creation(self):
        status = ServiceStatus(
            name="nginx",
            state=ServiceState.RUNNING,
            description="A high performance web server",
            load_state="loaded",
            active_state="active",
            sub_state="running",
            pid=1234,
            memory="50MB",
            cpu="100ms",
            started_at="2024-01-01",
            exit_code=0,
            main_pid_code="exited",
        )
        assert status.pid == 1234
        assert status.memory == "50MB"


class TestSystemdHelperInit:
    """Test SystemdHelper initialization."""

    def test_init_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "systemd 252"

        with patch("subprocess.run", return_value=mock_result):
            helper = SystemdHelper()
            assert helper is not None

    def test_init_systemd_not_available(self):
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="systemd is not available"):
                SystemdHelper()

    def test_init_systemctl_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="systemctl command not found"):
                SystemdHelper()

    def test_init_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            with pytest.raises(RuntimeError, match="Timeout"):
                SystemdHelper()


class TestGetServiceStatus:
    """Test the get_service_status method."""

    @pytest.fixture
    def helper(self):
        """Create a helper instance with mocked init."""
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    def test_empty_service_name(self, helper):
        with pytest.raises(ValueError, match="Service name cannot be empty"):
            helper.get_service_status("")

    def test_running_service(self, helper):
        mock_output = """LoadState=loaded
ActiveState=active
SubState=running
Description=The NGINX HTTP Server
MainPID=1234
MemoryCurrent=52428800
CPUUsageNSec=1000000000
ActiveEnterTimestamp=Mon 2024-01-01 00:00:00 UTC
ExecMainStatus=0
ExecMainCode=exited
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("nginx")

        assert status.name == "nginx"
        assert status.state == ServiceState.RUNNING
        assert status.pid == 1234
        assert status.description == "The NGINX HTTP Server"

    def test_failed_service(self, helper):
        mock_output = """LoadState=loaded
ActiveState=failed
SubState=failed
Description=My Service
MainPID=0
ExecMainStatus=1
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("myservice")

        assert status.state == ServiceState.FAILED
        assert status.exit_code == 1

    def test_inactive_service(self, helper):
        mock_output = """LoadState=loaded
ActiveState=inactive
SubState=dead
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("stopped-service")

        assert status.state == ServiceState.INACTIVE

    def test_activating_service(self, helper):
        mock_output = """LoadState=loaded
ActiveState=activating
SubState=start
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("starting-service")

        assert status.state == ServiceState.ACTIVATING

    def test_deactivating_service(self, helper):
        mock_output = """LoadState=loaded
ActiveState=deactivating
SubState=stop
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            status = helper.get_service_status("stopping-service")

        assert status.state == ServiceState.DEACTIVATING

    def test_service_suffix_normalization(self, helper):
        mock_output = """ActiveState=active
SubState=running
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            helper.get_service_status("nginx")

        # Check that .service was appended
        call_args = mock_run.call_args[0][0]
        assert "nginx.service" in call_args


class TestExplainStatus:
    """Test the explain_status method."""

    @pytest.fixture
    def helper(self):
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    def test_explain_running_service(self, helper):
        mock_output = """ActiveState=active
SubState=running
MainPID=1234
ActiveEnterTimestamp=Mon 2024-01-01 00:00:00 UTC
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("nginx")

        assert "running normally" in explanation
        assert "1234" in explanation

    def test_explain_failed_service(self, helper):
        mock_output = """ActiveState=failed
SubState=failed
ExecMainStatus=137
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("myservice")

        assert "failed" in explanation
        assert "137" in explanation
        assert "SIGKILL" in explanation or "memory" in explanation.lower()

    def test_explain_inactive_service(self, helper):
        mock_output = """ActiveState=inactive
SubState=dead
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch("subprocess.run", return_value=mock_result):
            explanation = helper.explain_status("stopped")

        assert "not running" in explanation or "inactive" in explanation


class TestExplainExitCode:
    """Test the _explain_exit_code method."""

    @pytest.fixture
    def helper(self):
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    @pytest.mark.parametrize(
        "exit_code, expected_text",
        [
            (1, "General error"),
            (127, "Command not found"),
            (137, "SIGKILL"),
            (139, "Segmentation fault"),
            (143, "SIGTERM"),
            (999, "check service logs"),
        ],
    )
    def test_exit_code_explanations(self, helper, exit_code, expected_text):
        explanation = helper._explain_exit_code(exit_code)
        assert expected_text in explanation


class TestDiagnoseFailure:
    """Test the diagnose_failure method."""

    @pytest.fixture
    def helper(self):
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    def test_diagnose_with_permission_error(self, helper):
        status_output = """ActiveState=failed
SubState=failed
ExecMainStatus=1
"""
        journal_output = """Jan 01 00:00:00 host myservice[1234]: permission denied while opening /etc/myservice.conf
Jan 01 00:00:01 host myservice[1234]: fatal error, exiting
"""
        mock_status = MagicMock(returncode=0, stdout=status_output)
        mock_journal = MagicMock(returncode=0, stdout=journal_output)

        # diagnose_failure calls get_service_status (which calls subprocess.run)
        # then calls subprocess.run for journalctl
        with patch("subprocess.run", side_effect=[mock_status, mock_status, mock_journal]):
            report = helper.diagnose_failure("myservice")

        assert "Permission issue detected" in report
        assert "permission" in report.lower()

    def test_diagnose_with_port_conflict(self, helper):
        status_output = """ActiveState=failed
SubState=failed
"""
        journal_output = """Jan 01 00:00:00 host nginx[1234]: bind() to 0.0.0.0:80 failed: address already in use
"""
        mock_status = MagicMock(returncode=0, stdout=status_output)
        mock_journal = MagicMock(returncode=0, stdout=journal_output)

        # diagnose_failure calls get_service_status then journalctl
        with patch("subprocess.run", side_effect=[mock_status, mock_status, mock_journal]):
            report = helper.diagnose_failure("nginx")

        assert "Port conflict detected" in report

    def test_diagnose_with_missing_file(self, helper):
        status_output = """ActiveState=failed
SubState=failed
"""
        journal_output = """Jan 01 00:00:00 host myapp[1234]: /opt/myapp/bin/run: No such file or directory
"""
        mock_status = MagicMock(returncode=0, stdout=status_output)
        mock_journal = MagicMock(returncode=0, stdout=journal_output)

        with patch("subprocess.run", side_effect=[mock_status, mock_status, mock_journal]):
            report = helper.diagnose_failure("myapp")

        assert "Missing file" in report


class TestShowDependencies:
    """Test the show_dependencies method."""

    @pytest.fixture
    def helper(self):
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    def test_show_dependencies_basic(self, helper):
        mock_output = """nginx.service
├─system.slice
│ └─-.slice
├─network.target
│ └─network-online.target
└─sysinit.target
"""
        mock_result = MagicMock(returncode=0, stdout=mock_output)

        with patch("subprocess.run", return_value=mock_result):
            tree = helper.show_dependencies("nginx")

        # Tree should be a Rich Tree object
        assert tree is not None
        assert tree.label is not None


class TestGenerateUnitFile:
    """Test the generate_unit_file method."""

    @pytest.fixture
    def helper(self):
        with patch.object(SystemdHelper, "_check_systemd_available"):
            return SystemdHelper()

    def test_basic_generation(self, helper):
        content = helper.generate_unit_file(
            description="My Test Service",
            exec_start="/usr/bin/myapp",
        )

        assert "[Unit]" in content
        assert "Description=My Test Service" in content
        assert "[Service]" in content
        assert "ExecStart=/usr/bin/myapp" in content
        assert "[Install]" in content
        assert "WantedBy=multi-user.target" in content
        assert "After=network.target" in content

    def test_with_user(self, helper):
        content = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            user="www-data",
        )

        assert "User=www-data" in content

    def test_with_working_directory(self, helper):
        content = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            working_dir="/var/lib/myapp",
        )

        assert "WorkingDirectory=/var/lib/myapp" in content

    def test_with_restart_disabled(self, helper):
        content = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            restart=False,
        )

        assert "Restart=on-failure" not in content
        assert "RestartSec" not in content

    def test_with_custom_after(self, helper):
        content = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            after=["postgresql.service", "redis.service"],
        )

        assert "After=postgresql.service redis.service" in content

    def test_with_environment(self, helper):
        content = helper.generate_unit_file(
            description="My Service",
            exec_start="/usr/bin/myapp",
            environment={"PORT": "8080", "DEBUG": "false"},
        )

        assert "Environment=PORT=8080" in content
        assert "Environment=DEBUG=false" in content


class TestRunCommands:
    """Test the run_* command functions."""

    def test_run_status_command(self):
        mock_output = """ActiveState=active
SubState=running
"""
        mock_init = MagicMock(returncode=0, stdout="systemd 252")
        mock_status = MagicMock(returncode=0, stdout=mock_output)

        with patch("subprocess.run", side_effect=[mock_init, mock_status]):
            # Should not raise
            run_status_command("nginx")

    def test_run_diagnose_command(self):
        mock_init = MagicMock(returncode=0, stdout="systemd 252")
        mock_status = MagicMock(returncode=0, stdout="ActiveState=failed\n")
        mock_journal = MagicMock(returncode=0, stdout="Error log line\n")

        # diagnose_failure calls get_service_status twice (once for status, once for explain)
        # plus journalctl
        with patch(
            "subprocess.run", side_effect=[mock_init, mock_status, mock_status, mock_journal]
        ):
            run_diagnose_command("myservice")

    def test_run_deps_command(self):
        mock_init = MagicMock(returncode=0, stdout="systemd 252")
        mock_deps = MagicMock(returncode=0, stdout="nginx.service\n├─network.target\n")

        with patch("subprocess.run", side_effect=[mock_init, mock_deps]):
            run_deps_command("nginx")

    def test_run_generate_command(self):
        mock_init = MagicMock(returncode=0, stdout="systemd 252")

        with patch("subprocess.run", return_value=mock_init):
            with patch(
                "rich.prompt.Prompt.ask",
                side_effect=[
                    "myservice",  # service name
                    "My Service",  # description
                    "/usr/bin/myapp",  # exec_start
                    "nobody",  # user
                    "/var/lib/myapp",  # working dir
                ],
            ):
                with patch(
                    "rich.prompt.Confirm.ask",
                    side_effect=[
                        False,  # run as root
                        True,  # has workdir
                        True,  # restart
                        True,  # start on boot
                    ],
                ):
                    run_generate_command()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
