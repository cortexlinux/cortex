import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter, APIProvider


class TestCommandInterpreter(unittest.TestCase):
    
    def setUp(self):
        self.api_key = "test-api-key"
        openai_stub = SimpleNamespace(OpenAI=Mock())
        anthropic_stub = SimpleNamespace(Anthropic=Mock())
        self.sys_modules_patcher = patch.dict(sys.modules, {
            'openai': openai_stub,
            'anthropic': anthropic_stub,
        })
        self.sys_modules_patcher.start()
        self.addCleanup(self.sys_modules_patcher.stop)
    
    @patch('openai.OpenAI')
    def test_initialization_openai(self, mock_openai):
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        self.assertEqual(interpreter.provider, APIProvider.OPENAI)
        self.assertEqual(interpreter.model, "gpt-4o")
        mock_openai.assert_called_once_with(api_key=self.api_key)
    
    @patch('anthropic.Anthropic')
    def test_initialization_claude(self, mock_anthropic):
        interpreter = CommandInterpreter(api_key=self.api_key, provider="claude")
        self.assertEqual(interpreter.provider, APIProvider.CLAUDE)
        self.assertEqual(interpreter.model, "claude-3-5-sonnet-20241022")
        mock_anthropic.assert_called_once_with(api_key=self.api_key)
    
    @patch('openai.OpenAI')
    def test_initialization_custom_model(self, mock_openai):
        interpreter = CommandInterpreter(
            api_key=self.api_key,
            provider="openai",
            model="gpt-4-turbo"
        )
        self.assertEqual(interpreter.model, "gpt-4-turbo")
    
    @patch.dict(os.environ, {}, clear=True)
    @patch.dict(sys.modules, {'requests': Mock()})
    def test_initialization_kimi(self):
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        self.assertEqual(interpreter.provider, APIProvider.KIMI)
        self.assertEqual(interpreter.model, "kimi-k2-turbo-preview")
    
    @patch('requests.post')
    def test_call_kimi_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"commands": ["apt update", "apt install curl"]}'}}]
        }
        mock_post.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        result = interpreter._call_kimi("install curl")
        
        self.assertEqual(result, ["apt update", "apt install curl"])
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("Authorization", call_args[1]["headers"])
        self.assertEqual(call_args[1]["headers"]["Authorization"], f"Bearer {self.api_key}")
    
    @patch('requests.post')
    def test_call_kimi_failure(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        
        with self.assertRaises(RuntimeError):
            interpreter._call_kimi("install docker")

    def test_parse_commands_valid_json(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        response = '{"commands": ["apt update", "apt install docker"]}'
        result = interpreter._parse_commands(response)
        self.assertEqual(result, ["apt update", "apt install docker"])
    
    def test_parse_commands_with_markdown(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        response = '```json\n{"commands": ["echo test"]}\n```'
        result = interpreter._parse_commands(response)
        self.assertEqual(result, ["echo test"])
    
    def test_parse_commands_invalid_json(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        with self.assertRaises(ValueError):
            interpreter._parse_commands("invalid json")
    
    def test_validate_commands_safe(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        commands = ["apt update", "apt install docker", "systemctl start docker"]
        result = interpreter._validate_commands(commands)
        self.assertEqual(result, commands)
    
    def test_validate_commands_dangerous(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        commands = ["apt update", "rm -rf /", "apt install docker"]
        result = interpreter._validate_commands(commands)
        self.assertEqual(result, ["apt update", "apt install docker"])
    
    def test_validate_commands_dd_pattern(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        commands = ["apt update", "dd if=/dev/zero of=/dev/sda"]
        result = interpreter._validate_commands(commands)
        self.assertEqual(result, ["apt update"])
    
    @patch('openai.OpenAI')
    def test_parse_empty_input(self, mock_openai):
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        
        with self.assertRaises(ValueError):
            interpreter.parse("")
    
    @patch('openai.OpenAI')
    def test_call_openai_success(self, mock_openai):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"commands": ["apt update"]}'
        mock_client.chat.completions.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        result = interpreter._call_openai("install docker")
        self.assertEqual(result, ["apt update"])
    
    @patch('openai.OpenAI')
    def test_call_openai_failure(self, mock_openai):
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        with self.assertRaises(RuntimeError):
            interpreter._call_openai("install docker")

    @patch('anthropic.Anthropic')
    def test_call_claude_success(self, mock_anthropic):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = '{"commands": ["apt update"]}'
        mock_client.messages.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="claude")
        interpreter.client = mock_client
        
        result = interpreter._call_claude("install docker")
        self.assertEqual(result, ["apt update"])
    
    @patch('anthropic.Anthropic')
    def test_call_claude_failure(self, mock_anthropic):
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="claude")
        interpreter.client = mock_client
        
        with self.assertRaises(RuntimeError):
            interpreter._call_claude("install docker")
    
    @patch('openai.OpenAI')
    def test_parse_with_validation(self, mock_openai):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"commands": ["apt update", "rm -rf /"]}'
        mock_client.chat.completions.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        result = interpreter.parse("test command", validate=True)
        self.assertEqual(result, ["apt update"])
    
    @patch('openai.OpenAI')
    def test_parse_without_validation(self, mock_openai):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"commands": ["apt update", "rm -rf /"]}'
        mock_client.chat.completions.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        result = interpreter.parse("test command", validate=False)
        self.assertEqual(result, ["apt update", "rm -rf /"])
    
    @patch('openai.OpenAI')
    def test_parse_with_context(self, mock_openai):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"commands": ["apt update"]}'
        mock_client.chat.completions.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        system_info = {"os": "ubuntu", "version": "22.04"}
        result = interpreter.parse_with_context("install docker", system_info=system_info)
        
        self.assertEqual(result, ["apt update"])
        call_args = mock_client.chat.completions.create.call_args
        self.assertIn("ubuntu", call_args[1]["messages"][1]["content"])
    
    def test_system_prompt_format(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        prompt = interpreter._get_system_prompt()
        
        self.assertIn("JSON array", prompt)
        self.assertIn("bash commands", prompt)
        self.assertIn("safe", prompt)
    
    def test_validate_commands_empty_list(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        result = interpreter._validate_commands([])
        self.assertEqual(result, [])
    
    def test_parse_commands_empty_commands(self):
        interpreter = CommandInterpreter.__new__(CommandInterpreter)
        
        response = '{"commands": ["", "apt update", null, "apt install docker"]}'
        result = interpreter._parse_commands(response)
        self.assertEqual(result, ["apt update", "apt install docker"])
    
    @patch('openai.OpenAI')
    def test_parse_docker_installation(self, mock_openai):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "commands": [
                "sudo apt update",
                "sudo apt install -y docker.io",
                "sudo systemctl start docker",
                "sudo systemctl enable docker"
            ]
        })
        mock_client.chat.completions.create.return_value = mock_response
        
        interpreter = CommandInterpreter(api_key=self.api_key, provider="openai")
        interpreter.client = mock_client
        
        result = interpreter.parse("install docker")
        self.assertGreater(len(result), 0)
        self.assertTrue(any("docker" in cmd.lower() for cmd in result))


@unittest.skipUnless(
    os.environ.get('RUN_KIMI_INTEGRATION_TESTS') == '1',
    "Skipping Kimi K2 integration tests. Set RUN_KIMI_INTEGRATION_TESTS=1 to run them."
)
class TestKimiK2Integration(unittest.TestCase):
    """Integration tests for Kimi K2 API with real API calls
    
    To run these tests:
    - Set environment variable: RUN_KIMI_INTEGRATION_TESTS=1
    - Set environment variable: KIMI_API_KEY=your-api-key
    - Run: python -m unittest LLM.test_interpreter.TestKimiK2Integration -v
    """
    
    def setUp(self):
        # Use the actual API key from environment
        self.api_key = os.environ.get('KIMI_API_KEY')
        
        if not self.api_key:
            self.skipTest("KIMI_API_KEY not set for integration tests")
    
    def test_kimi_real_api_basic_request(self):
        """Test Kimi K2 with real API - basic installation request"""
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        
        result = interpreter.parse("Install curl on Ubuntu")
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertTrue(any("curl" in cmd.lower() for cmd in result))
        print(f"\n✅ Kimi K2 API Test - Generated {len(result)} commands: {result}")
    
    def test_kimi_real_api_complex_request(self):
        """Test Kimi K2 with real API - complex installation request"""
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        
        result = interpreter.parse("Install nginx web server and configure it to start on boot")
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 2)
        self.assertTrue(any("nginx" in cmd.lower() for cmd in result))
        print(f"\n✅ Kimi K2 API Complex Test - Generated {len(result)} commands: {result}")
    
    @patch.dict(os.environ, {'KIMI_DEFAULT_MODEL': 'kimi-k2-0905-preview'})
    def test_kimi_real_api_with_custom_model(self):
        """Test Kimi K2 with different model"""
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        
        result = interpreter.parse("Install git")
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertTrue(any("git" in cmd.lower() for cmd in result))
        print(f"\n✅ Kimi K2 Custom Model Test - Generated {len(result)} commands: {result}")
    
    def test_kimi_real_api_validation(self):
        """Test Kimi K2 with command validation"""
        interpreter = CommandInterpreter(api_key=self.api_key, provider="kimi")
        
        result = interpreter.parse("Install docker", validate=True)
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        # Ensure no dangerous commands passed validation
        for cmd in result:
            self.assertNotIn("rm -rf", cmd.lower())
            self.assertNotIn("dd if=", cmd.lower())
        print(f"\n✅ Kimi K2 Validation Test - Validated commands: {result}")


if __name__ == "__main__":
    unittest.main()
