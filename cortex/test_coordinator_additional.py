import unittest
from unittest.mock import Mock, patch
import subprocess
import tempfile
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.coordinator import (
    InstallationCoordinator,
    InstallationStep,
    StepStatus
)


class TestCoordinatorAdditional(unittest.TestCase):
    """Additional comprehensive tests for InstallationCoordinator"""
    
    @patch('subprocess.run')
    def test_execute_command_timeout_expired(self, mock_run):
        """Test proper handling of subprocess.TimeoutExpired exception"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 1000", timeout=1)
        
        coordinator = InstallationCoordinator(["sleep 1000"], timeout=1)
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        self.assertEqual(result.steps[0].status, StepStatus.FAILED)
        self.assertIn("timed out", result.steps[0].error)
        self.assertIsNotNone(result.steps[0].end_time)
    
    @patch('subprocess.run')
    def test_rollback_with_no_commands(self, mock_run):
        """Test rollback when no rollback commands are registered"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result
        
        coordinator = InstallationCoordinator(["fail"], enable_rollback=True)
        # Don't add any rollback commands
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        # Rollback should not fail even with no commands
    
    @patch('subprocess.run')
    def test_rollback_with_multiple_commands(self, mock_run):
        """Test rollback executes multiple commands in reverse order"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result
        
        coordinator = InstallationCoordinator(["fail"], enable_rollback=True)
        coordinator.add_rollback_command("cleanup1")
        coordinator.add_rollback_command("cleanup2")
        coordinator.add_rollback_command("cleanup3")
        
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        # Verify rollback was attempted (at least 4 calls: 1 for fail + 3 for rollback)
        self.assertGreaterEqual(mock_run.call_count, 4)
    
    @patch('subprocess.run')
    def test_rollback_command_failure(self, mock_run):
        """Test that rollback continues even if a rollback command fails"""
        call_count = [0]
        
        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First command fails
                result = Mock()
                result.returncode = 1
                result.stdout = ""
                result.stderr = "error"
                return result
            else:
                # Rollback commands also fail
                raise RuntimeError()
        
        mock_run.side_effect = side_effect
        
        coordinator = InstallationCoordinator(["fail"], enable_rollback=True)
        coordinator.add_rollback_command("cleanup1")
        coordinator.add_rollback_command("cleanup2")
        
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        # Should attempt all rollback commands despite failures
        self.assertGreaterEqual(call_count[0], 3)
    
    @patch('subprocess.run')
    def test_rollback_disabled(self, mock_run):
        """Test that rollback doesn't execute when disabled"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result
        
        coordinator = InstallationCoordinator(["fail"], enable_rollback=False)
        coordinator.add_rollback_command("cleanup")
        
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        # Only one call for the failed command, no rollback
        self.assertEqual(mock_run.call_count, 1)
    
    @patch('subprocess.run')
    def test_verify_installation_with_failures(self, mock_run):
        """Test verification when some commands fail"""
        call_count = [0]
        
        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            result = Mock()
            # First call is execute (success), then alternating verify results
            if call_count[0] == 1:
                result.returncode = 0  # Execute succeeds
            else:
                # Verification: 2=fail, 3=success, 4=fail
                result.returncode = 0 if call_count[0] % 2 == 1 else 1
            result.stdout = "output"
            result.stderr = ""
            return result
        
        mock_run.side_effect = side_effect
        
        coordinator = InstallationCoordinator(["echo test"])
        coordinator.execute()
        
        verify_results = coordinator.verify_installation([
            "docker --version",
            "systemctl is-active docker",
            "docker ps"
        ])
        
        self.assertEqual(len(verify_results), 3)
        self.assertFalse(verify_results["docker --version"])
        self.assertTrue(verify_results["systemctl is-active docker"])
        self.assertFalse(verify_results["docker ps"])
    
    @patch('subprocess.run')
    def test_verify_installation_with_exception(self, mock_run):
        """Test verification when a command raises an exception"""
        call_count = [0]
        
        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call is execute
                result = Mock()
                result.returncode = 0
                result.stdout = "success"
                result.stderr = ""
                return result
            else:
                # Verification calls
                raise RuntimeError()
        
        mock_run.side_effect = side_effect
        
        coordinator = InstallationCoordinator(["echo test"])
        coordinator.execute()
        
        verify_results = coordinator.verify_installation(["docker --version"])
        
        self.assertFalse(verify_results["docker --version"])
    
    @patch('subprocess.run')
    def test_verify_installation_timeout(self, mock_run):
        """Test verification command timeout handling"""
        call_count = [0]
        
        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                result = Mock()
                result.returncode = 0
                result.stdout = "success"
                result.stderr = ""
                return result
            else:
                raise subprocess.TimeoutExpired(cmd="test", timeout=30)
        
        mock_run.side_effect = side_effect
        
        coordinator = InstallationCoordinator(["echo test"])
        coordinator.execute()
        
        verify_results = coordinator.verify_installation(["long_running_cmd"])
        
        self.assertFalse(verify_results["long_running_cmd"])
    
    @patch('subprocess.run')
    def test_get_summary_with_mixed_statuses(self, mock_run):
        """Test get_summary with steps in different states"""
        call_count = [0]
        
        def side_effect(*_args, **_kwargs):
            call_count[0] += 1
            result = Mock()
            if call_count[0] <= 2:
                result.returncode = 0
            else:
                result.returncode = 1
            result.stdout = "output"
            result.stderr = "error" if result.returncode != 0 else ""
            return result
        
        mock_run.side_effect = side_effect
        
        coordinator = InstallationCoordinator(
            ["cmd1", "cmd2", "cmd3", "cmd4"],
            stop_on_error=True
        )
        coordinator.execute()
        
        summary = coordinator.get_summary()
        
        self.assertEqual(summary["total_steps"], 4)
        self.assertEqual(summary["success"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(len(summary["steps"]), 4)
    
    def test_log_file_write_error_handling(self):
        """Test that log file write errors are handled gracefully"""
        coordinator = InstallationCoordinator(
            ["echo test"],
            log_file="/invalid/path/that/does/not/exist/logfile.log"
        )
        
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "success"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            # Should not raise exception even if log file can't be written
            result = coordinator.execute()
            self.assertTrue(result.success)
    
    @patch('subprocess.run')
    def test_empty_commands_list(self, mock_run):
        """Test coordinator with empty commands list"""
        coordinator = InstallationCoordinator([])
        result = coordinator.execute()
        
        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 0)
        self.assertEqual(result.failed_step, None)
        mock_run.assert_not_called()
    
    @patch('subprocess.run')
    def test_step_return_code_captured(self, mock_run):
        """Test that step return codes are properly captured"""
        mock_result = Mock()
        mock_result.returncode = 42
        mock_result.stdout = "output"
        mock_result.stderr = "error"
        mock_run.return_value = mock_result
        
        coordinator = InstallationCoordinator(["cmd"])
        result = coordinator.execute()
        
        self.assertEqual(result.steps[0].return_code, 42)
    
    @patch('subprocess.run')
    def test_step_output_and_error_captured(self, mock_run):
        """Test that stdout and stderr are properly captured"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Standard output here"
        mock_result.stderr = "Standard error here"
        mock_run.return_value = mock_result
        
        coordinator = InstallationCoordinator(["cmd"])
        result = coordinator.execute()
        
        self.assertEqual(result.steps[0].output, "Standard output here")
        self.assertEqual(result.steps[0].error, "Standard error here")
    
    def test_step_duration_not_calculated_without_times(self):
        """Test that duration is None when times are not set"""
        step = InstallationStep(command="test", description="Test")
        self.assertIsNone(step.duration())
        
        step.start_time = 100.0
        self.assertIsNone(step.duration())
    
    def test_installation_result_with_no_failure(self):
        """Test InstallationResult when no steps failed"""
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "success"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            coordinator = InstallationCoordinator(["cmd1", "cmd2"])
            result = coordinator.execute()
            
            self.assertTrue(result.success)
            self.assertIsNone(result.failed_step)
            self.assertIsNone(result.error_message)
    
    @patch('subprocess.run')
    def test_custom_timeout_value(self, mock_run):
        """Test coordinator with custom timeout value"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)
        
        coordinator = InstallationCoordinator(["sleep 100"], timeout=10)
        result = coordinator.execute()
        
        self.assertFalse(result.success)
        self.assertIn("10 seconds", result.steps[0].error)
    
    def test_export_log_creates_valid_json(self):
        """Test that export_log creates a valid JSON file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            export_file = f.name
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "success"
                mock_result.stderr = ""
                mock_run.return_value = mock_result
                
                coordinator = InstallationCoordinator(["echo test", "echo test2"])
                coordinator.execute()
                coordinator.export_log(export_file)
            
            import json
            with open(export_file, 'r') as f:
                data = json.load(f)
                self.assertIn("total_steps", data)
                self.assertIn("success", data)
                self.assertIn("failed", data)
                self.assertIn("skipped", data)
                self.assertIn("steps", data)
                self.assertEqual(len(data["steps"]), 2)
        finally:
            if os.path.exists(export_file):
                os.unlink(export_file)


if __name__ == '__main__':
    unittest.main()