import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cortex.cli import CortexCLI, main
from cortex.coordinator import StepStatus, InstallationStep


class TestCortexCLIAdditional(unittest.TestCase):
    """Additional comprehensive tests for CortexCLI"""
    
    def setUp(self):
        self.cli = CortexCLI()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'openai-key', 'ANTHROPIC_API_KEY': 'claude-key'})
    def test_get_api_key_both_set_prefers_openai(self):
        """Test that OpenAI key is preferred when both are set"""
        api_key = self.cli._get_api_key()
        self.assertEqual(api_key, 'openai-key')
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'openai-key', 'ANTHROPIC_API_KEY': 'claude-key'})
    def test_get_provider_both_set_prefers_openai(self):
        """Test that OpenAI provider is chosen when both keys are set"""
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'openai')
    
    @patch.dict(os.environ, {}, clear=True)
    def test_get_provider_no_keys_defaults_openai(self):
        """Test that provider defaults to openai when no keys are set"""
        provider = self.cli._get_provider()
        self.assertEqual(provider, 'openai')
    
    def test_spinner_wraps_around(self):
        """Test that spinner index wraps around correctly"""
        self.cli.spinner_idx = len(self.cli.spinner_chars) - 1
        self.cli._animate_spinner("Testing")
        self.assertEqual(self.cli.spinner_idx, 0)
    
    def test_spinner_increments_correctly(self):
        """Test that spinner increments through all characters"""
        initial_idx = 0
        self.cli.spinner_idx = initial_idx
        for i in range(len(self.cli.spinner_chars)):
            expected_idx = (initial_idx + i + 1) % len(self.cli.spinner_chars)
            self.cli._animate_spinner("Testing")
            self.assertEqual(self.cli.spinner_idx, expected_idx)
    
    @patch('sys.stdout')
    def test_clear_line_writes_escape_sequence(self, mock_stdout):
        """Test that clear_line writes the correct escape sequence"""
        self.cli._clear_line()
        mock_stdout.write.assert_called_with('\r\033[K')
        mock_stdout.flush.assert_called_once()
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_progress_callback_success_status(self, mock_coordinator_class, mock_interpreter_class):
        """Test progress callback with SUCCESS status"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo test"]
        mock_interpreter_class.return_value = mock_interpreter
        
        captured_callback = None
        
        def capture_callback(*_, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get('progress_callback')
            mock_coordinator = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.total_duration = 1.5
            mock_coordinator.execute.return_value = mock_result
            return mock_coordinator
        
        mock_coordinator_class.side_effect = capture_callback
        
        self.cli.install("docker", execute=True)
        
        if captured_callback:
            step = InstallationStep(command="test", description="Test step")
            step.status = StepStatus.SUCCESS
            captured_callback(1, 2, step)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_progress_callback_failed_status(self, mock_coordinator_class, mock_interpreter_class):
        """Test progress callback with FAILED status"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo test"]
        mock_interpreter_class.return_value = mock_interpreter
        
        captured_callback = None
        
        def capture_callback(*_, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get('progress_callback')
            mock_coordinator = Mock()
            mock_result = Mock()
            mock_result.success = False
            mock_result.failed_step = 0
            mock_result.error_message = "error"
            mock_coordinator.execute.return_value = mock_result
            return mock_coordinator
        
        mock_coordinator_class.side_effect = capture_callback
        
        self.cli.install("docker", execute=True)
        
        if captured_callback:
            step = InstallationStep(command="test", description="Test step")
            step.status = StepStatus.FAILED
            captured_callback(1, 2, step)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_progress_callback_pending_status(self, mock_coordinator_class, mock_interpreter_class):
        """Test progress callback with PENDING/RUNNING status (default emoji)"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo test"]
        mock_interpreter_class.return_value = mock_interpreter
        
        captured_callback = None
        
        def capture_callback(*_, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get('progress_callback')
            mock_coordinator = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.total_duration = 1.5
            mock_coordinator.execute.return_value = mock_result
            return mock_coordinator
        
        mock_coordinator_class.side_effect = capture_callback
        
        self.cli.install("docker", execute=True)
        
        if captured_callback:
            step = InstallationStep(command="test", description="Test step")
            step.status = StepStatus.PENDING
            captured_callback(1, 2, step)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_failure_no_error_message(self, mock_coordinator_class, mock_interpreter_class):
        """Test execution failure without error message"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["invalid command"]
        mock_interpreter_class.return_value = mock_interpreter
        
        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.failed_step = 0
        mock_result.error_message = None
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator
        
        result = self.cli.install("docker", execute=True)
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    @patch('cortex.cli.InstallationCoordinator')
    def test_install_with_execute_failure_no_failed_step(self, mock_coordinator_class, mock_interpreter_class):
        """Test execution failure without failed_step index"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["invalid command"]
        mock_interpreter_class.return_value = mock_interpreter
        
        mock_coordinator = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.failed_step = None
        mock_result.error_message = "unknown error"
        mock_coordinator.execute.return_value = mock_result
        mock_coordinator_class.return_value = mock_coordinator
        
        result = self.cli.install("docker", execute=True)
        
        self.assertEqual(result, 1)
    
    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_with_claude_provider(self, mock_interpreter_class):
        """Test installation using Claude provider"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["apt update"]
        mock_interpreter_class.return_value = mock_interpreter
        
        result = self.cli.install("docker", execute=False)
        
        self.assertEqual(result, 0)
        mock_interpreter_class.assert_called_once_with(api_key='test-key', provider='claude')
    
    @patch('sys.argv', ['cortex', 'install', 'nginx', '--execute', '--dry-run'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_both_execute_and_dry_run(self, mock_install):
        """Test that both --execute and --dry-run can be passed"""
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('nginx', execute=True, dry_run=True)
    
    @patch('sys.argv', ['cortex', 'install', 'python 3.11'])
    @patch('cortex.cli.CortexCLI.install')
    def test_main_install_complex_software_name(self, mock_install):
        """Test installation with complex software names containing spaces"""
        mock_install.return_value = 0
        result = main()
        self.assertEqual(result, 0)
        mock_install.assert_called_once_with('python 3.11', execute=False, dry_run=False)
    
    def test_cli_initialization_spinner_chars(self):
        """Test that CLI initializes with correct spinner characters"""
        cli = CortexCLI()
        self.assertEqual(len(cli.spinner_chars), 10)
        self.assertEqual(cli.spinner_idx, 0)
        self.assertIn('⠋', cli.spinner_chars)
    
    @patch('sys.argv', ['cortex', '--help'])
    def test_main_help_flag(self):
        """Test that help flag doesn't crash"""
        with self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 0)
    
    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'})
    @patch('cortex.cli.CommandInterpreter')
    def test_install_empty_software_name(self, mock_interpreter_class):
        """Test installation with empty software name"""
        mock_interpreter = Mock()
        mock_interpreter.parse.return_value = ["echo test"]
        mock_interpreter_class.return_value = mock_interpreter
        
        self.cli.install("", execute=False)
        
        mock_interpreter.parse.assert_called_once_with("install ")


if __name__ == '__main__':
    unittest.main()