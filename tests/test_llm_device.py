#!/usr/bin/env python3
"""
Unit tests for Cortex /dev/llm Virtual Device

Tests cover:
- Session management
- Configuration handling
- Path parsing
- Mock LLM client
- FUSE operations (getattr, readdir, read, write)
- History tracking
- Metrics
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.kernel_features.llm_device import (
    SessionConfig,
    Message,
    Session,
    Metrics,
    MockLLMClient,
    LLMDevice,
)


class TestSessionConfig(unittest.TestCase):
    """Test SessionConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SessionConfig()
        self.assertEqual(config.model, "claude-3-5-sonnet-20241022")
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.max_tokens, 4096)
        self.assertEqual(config.system_prompt, "")

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SessionConfig(
            model="claude-3-opus-20240229",
            temperature=0.5,
            max_tokens=2048,
            system_prompt="You are a helpful assistant."
        )
        self.assertEqual(config.model, "claude-3-opus-20240229")
        self.assertEqual(config.temperature, 0.5)
        self.assertEqual(config.max_tokens, 2048)
        self.assertEqual(config.system_prompt, "You are a helpful assistant.")

    def test_to_json(self):
        """Test JSON serialization."""
        config = SessionConfig(temperature=0.9)
        json_str = config.to_json()
        data = json.loads(json_str)
        self.assertEqual(data["temperature"], 0.9)
        self.assertIn("model", data)
        self.assertIn("max_tokens", data)

    def test_from_json_valid(self):
        """Test JSON deserialization with valid data."""
        json_str = '{"model": "test-model", "temperature": 0.5, "max_tokens": 1000, "system_prompt": "test"}'
        config = SessionConfig.from_json(json_str)
        self.assertEqual(config.model, "test-model")
        self.assertEqual(config.temperature, 0.5)
        self.assertEqual(config.max_tokens, 1000)

    def test_from_json_invalid(self):
        """Test JSON deserialization with invalid data returns defaults."""
        config = SessionConfig.from_json("invalid json")
        self.assertEqual(config.model, "claude-3-5-sonnet-20241022")

    def test_from_json_partial(self):
        """Test JSON deserialization with partial data."""
        json_str = '{"temperature": 0.3}'
        config = SessionConfig.from_json(json_str)
        self.assertEqual(config.temperature, 0.3)
        # Other fields should be defaults
        self.assertEqual(config.max_tokens, 4096)


class TestMessage(unittest.TestCase):
    """Test Message dataclass."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = Message(role="user", content="Hello")
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "Hello")
        self.assertIsInstance(msg.timestamp, float)

    def test_to_dict(self):
        """Test conversion to API format."""
        msg = Message(role="assistant", content="Hi there!")
        d = msg.to_dict()
        self.assertEqual(d, {"role": "assistant", "content": "Hi there!"})


class TestSession(unittest.TestCase):
    """Test Session dataclass."""

    def test_session_creation(self):
        """Test creating a session."""
        session = Session(id="test-session")
        self.assertEqual(session.id, "test-session")
        self.assertEqual(len(session.messages), 0)
        self.assertEqual(session.prompt_buffer, "")
        self.assertEqual(session.response_buffer, "")

    def test_add_message(self):
        """Test adding messages to session."""
        session = Session(id="test")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0].role, "user")
        self.assertEqual(session.messages[1].content, "Hi!")

    def test_get_messages_for_api(self):
        """Test getting messages in API format."""
        session = Session(id="test")
        session.add_message("user", "Question")
        session.add_message("assistant", "Answer")

        messages = session.get_messages_for_api()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], {"role": "user", "content": "Question"})

    def test_get_history(self):
        """Test getting formatted history."""
        session = Session(id="test")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        history = session.get_history()
        self.assertIn("USER:", history)
        self.assertIn("ASSISTANT:", history)
        self.assertIn("Hello", history)
        self.assertIn("Hi!", history)

    def test_clear_history(self):
        """Test clearing session history."""
        session = Session(id="test")
        session.add_message("user", "Hello")
        session.prompt_buffer = "test"
        session.response_buffer = "response"

        session.clear_history()

        self.assertEqual(len(session.messages), 0)
        self.assertEqual(session.prompt_buffer, "")
        self.assertEqual(session.response_buffer, "")


class TestMetrics(unittest.TestCase):
    """Test Metrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = Metrics()
        self.assertEqual(metrics.total_requests, 0)
        self.assertEqual(metrics.total_tokens, 0)
        self.assertEqual(metrics.total_errors, 0)

    def test_to_json(self):
        """Test JSON serialization."""
        metrics = Metrics()
        metrics.total_requests = 10
        metrics.total_tokens = 5000

        json_str = metrics.to_json()
        data = json.loads(json_str)

        self.assertEqual(data["status"], "running")
        self.assertEqual(data["total_requests"], 10)
        self.assertEqual(data["total_tokens"], 5000)
        self.assertIn("uptime_seconds", data)
        self.assertIn("requests_per_minute", data)


class TestMockLLMClient(unittest.TestCase):
    """Test MockLLMClient."""

    def test_complete_returns_response(self):
        """Test mock client returns response."""
        client = MockLLMClient(latency=0.01)
        response, tokens = client.complete(
            model="test",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            temperature=0.7
        )

        self.assertIn("[Mock Response", response)
        self.assertIn("Hello", response)
        self.assertIsInstance(tokens, int)
        self.assertGreater(tokens, 0)

    def test_complete_increments_count(self):
        """Test call count increments."""
        client = MockLLMClient(latency=0.01)

        client.complete("m", [{"role": "user", "content": "1"}], 100, 0.7)
        client.complete("m", [{"role": "user", "content": "2"}], 100, 0.7)

        self.assertEqual(client._call_count, 2)


class TestLLMDevice(unittest.TestCase):
    """Test LLMDevice FUSE filesystem."""

    def setUp(self):
        """Create device for testing."""
        self.device = LLMDevice(use_mock=True)

    def test_init_creates_default_session(self):
        """Test default session is created on init."""
        self.assertIn("default", self.device.sessions)

    def test_parse_path_root(self):
        """Test parsing root path."""
        ptype, name, file = self.device._parse_path("/")
        self.assertEqual(ptype, "root")
        self.assertIsNone(name)
        self.assertIsNone(file)

    def test_parse_path_model(self):
        """Test parsing model path."""
        ptype, name, file = self.device._parse_path("/claude")
        self.assertEqual(ptype, "model")
        self.assertEqual(name, "claude")

    def test_parse_path_model_file(self):
        """Test parsing model file path."""
        ptype, name, file = self.device._parse_path("/claude/prompt")
        self.assertEqual(ptype, "model_file")
        self.assertEqual(name, "claude")
        self.assertEqual(file, "prompt")

    def test_parse_path_sessions(self):
        """Test parsing sessions path."""
        ptype, name, file = self.device._parse_path("/sessions")
        self.assertEqual(ptype, "sessions")

    def test_parse_path_session(self):
        """Test parsing session path."""
        ptype, name, file = self.device._parse_path("/sessions/my-session")
        self.assertEqual(ptype, "session")
        self.assertEqual(name, "my-session")

    def test_parse_path_session_file(self):
        """Test parsing session file path."""
        ptype, name, file = self.device._parse_path("/sessions/test/prompt")
        self.assertEqual(ptype, "session_file")
        self.assertEqual(name, "test")
        self.assertEqual(file, "prompt")

    def test_parse_path_status(self):
        """Test parsing status path."""
        ptype, name, file = self.device._parse_path("/status")
        self.assertEqual(ptype, "status")

    def test_parse_path_unknown(self):
        """Test parsing unknown path."""
        ptype, name, file = self.device._parse_path("/unknown/path")
        self.assertEqual(ptype, "unknown")

    def test_getattr_root(self):
        """Test getattr for root directory."""
        attrs = self.device.getattr("/")
        self.assertTrue(attrs["st_mode"] & 0o40000)  # Is directory

    def test_getattr_model_dir(self):
        """Test getattr for model directory."""
        attrs = self.device.getattr("/claude")
        self.assertTrue(attrs["st_mode"] & 0o40000)

    def test_getattr_status_file(self):
        """Test getattr for status file."""
        attrs = self.device.getattr("/status")
        self.assertFalse(attrs["st_mode"] & 0o40000)  # Is file
        self.assertGreater(attrs["st_size"], 0)

    def test_readdir_root(self):
        """Test listing root directory."""
        entries = self.device.readdir("/", None)
        self.assertIn(".", entries)
        self.assertIn("..", entries)
        self.assertIn("claude", entries)
        self.assertIn("sessions", entries)
        self.assertIn("status", entries)

    def test_readdir_model(self):
        """Test listing model directory."""
        entries = self.device.readdir("/claude", None)
        self.assertIn("prompt", entries)
        self.assertIn("response", entries)
        self.assertIn("config", entries)

    def test_readdir_sessions(self):
        """Test listing sessions directory."""
        entries = self.device.readdir("/sessions", None)
        self.assertIn("default", entries)

    def test_read_status(self):
        """Test reading status file."""
        data = self.device.read("/status", 10000, 0, None)
        status = json.loads(data.decode())
        self.assertEqual(status["status"], "running")

    def test_write_prompt_and_read_response(self):
        """Test writing prompt and reading response."""
        # Write prompt
        prompt = b"What is 2+2?"
        written = self.device.write("/claude/prompt", prompt, 0, None)
        self.assertEqual(written, len(prompt))

        # Read response
        response = self.device.read("/claude/response", 10000, 0, None)
        self.assertIn(b"Mock Response", response)

    def test_session_creation_via_prompt(self):
        """Test session created when writing to new session."""
        self.device.write("/sessions/new-session/prompt", b"Hello", 0, None)
        self.assertIn("new-session", self.device.sessions)

    def test_read_history(self):
        """Test reading session history."""
        # Add some messages
        self.device.write("/sessions/default/prompt", b"Hello", 0, None)

        # Read history
        history = self.device.read("/sessions/default/history", 10000, 0, None)
        self.assertIn(b"USER:", history)
        self.assertIn(b"Hello", history)

    def test_write_config(self):
        """Test writing configuration."""
        config = b'{"temperature": 0.5}'
        self.device.write("/sessions/default/config", config, 0, None)

        session = self.device.sessions["default"]
        self.assertEqual(session.config.temperature, 0.5)

    def test_read_config(self):
        """Test reading configuration."""
        data = self.device.read("/sessions/default/config", 10000, 0, None)
        config = json.loads(data.decode())
        self.assertIn("model", config)
        self.assertIn("temperature", config)

    def test_clear_history_via_write(self):
        """Test clearing history via write to clear file."""
        # Add a message
        self.device.write("/sessions/default/prompt", b"Test", 0, None)
        self.assertGreater(len(self.device.sessions["default"].messages), 0)

        # Clear
        self.device.write("/sessions/default/clear", b"", 0, None)
        self.assertEqual(len(self.device.sessions["default"].messages), 0)

    def test_mkdir_creates_session(self):
        """Test mkdir creates new session."""
        self.device.mkdir("/sessions/new-session", 0o755)
        self.assertIn("new-session", self.device.sessions)

    def test_rmdir_deletes_session(self):
        """Test rmdir deletes session."""
        self.device.mkdir("/sessions/to-delete", 0o755)
        self.assertIn("to-delete", self.device.sessions)

        self.device.rmdir("/sessions/to-delete")
        self.assertNotIn("to-delete", self.device.sessions)

    def test_rmdir_default_protected(self):
        """Test cannot delete default session."""
        from cortex.kernel_features.llm_device import FuseOSError
        with self.assertRaises(FuseOSError):
            self.device.rmdir("/sessions/default")

    def test_metrics_updated_on_request(self):
        """Test metrics are updated after request."""
        initial_requests = self.device.metrics.total_requests

        self.device.write("/claude/prompt", b"Test", 0, None)

        self.assertEqual(self.device.metrics.total_requests, initial_requests + 1)
        self.assertIsNotNone(self.device.metrics.last_request_time)

    def test_multiple_models(self):
        """Test different model endpoints."""
        for model in ["claude", "sonnet", "haiku", "opus"]:
            entries = self.device.readdir(f"/{model}", None)
            self.assertIn("prompt", entries)


class TestPathParsing(unittest.TestCase):
    """Additional path parsing tests."""

    def setUp(self):
        self.device = LLMDevice(use_mock=True)

    def test_empty_path(self):
        """Test empty path."""
        ptype, _, _ = self.device._parse_path("")
        self.assertEqual(ptype, "root")

    def test_trailing_slash(self):
        """Test path with trailing slash."""
        ptype, name, _ = self.device._parse_path("/claude/")
        self.assertEqual(ptype, "model")
        self.assertEqual(name, "claude")

    def test_double_slash(self):
        """Test path with double slash."""
        ptype, name, file = self.device._parse_path("//claude//prompt")
        self.assertEqual(ptype, "model_file")
        self.assertEqual(file, "prompt")

    def test_invalid_model_file(self):
        """Test invalid file in model directory."""
        ptype, _, _ = self.device._parse_path("/claude/invalid")
        self.assertEqual(ptype, "unknown")


class TestConcurrency(unittest.TestCase):
    """Test thread safety."""

    def setUp(self):
        self.device = LLMDevice(use_mock=True)

    def test_concurrent_session_creation(self):
        """Test creating sessions concurrently."""
        import threading

        def create_session(name):
            self.device._create_session(name)

        threads = []
        for i in range(10):
            t = threading.Thread(target=create_session, args=(f"session-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All sessions should be created
        for i in range(10):
            self.assertIn(f"session-{i}", self.device.sessions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
