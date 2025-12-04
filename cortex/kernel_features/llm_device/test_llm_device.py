#!/usr/bin/env python3
"""
Tests for /dev/llm Virtual Device

Run: python test_llm_device.py
"""

import unittest
import json
from llm_device import LLMDevice, MockLLMClient, Session


class TestMockClient(unittest.TestCase):
    """Test mock LLM client."""

    def setUp(self):
        self.client = MockLLMClient()

    def test_basic_response(self):
        response = self.client.complete("What is 2+2?")
        self.assertEqual(response, "4")

    def test_hello_response(self):
        response = self.client.complete("Hello!")
        self.assertIn("Hello", response)

    def test_metrics_tracking(self):
        self.client.complete("Test 1")
        self.client.complete("Test 2")
        metrics = self.client.get_metrics()
        self.assertEqual(metrics["calls"], 2)
        self.assertGreater(metrics["total_tokens"], 0)


class TestSession(unittest.TestCase):
    """Test session management."""

    def setUp(self):
        self.session = Session(name="test-session")

    def test_add_exchange(self):
        self.session.add_exchange("Hello", "Hi there!")
        self.assertEqual(len(self.session.messages), 1)
        self.assertEqual(self.session.messages[0]["prompt"], "Hello")
        self.assertEqual(self.session.messages[0]["response"], "Hi there!")

    def test_get_history(self):
        self.session.add_exchange("Q1", "A1")
        self.session.add_exchange("Q2", "A2")
        history = self.session.get_history()
        self.assertIn("Q1", history)
        self.assertIn("A1", history)
        self.assertIn("Q2", history)
        self.assertIn("A2", history)

    def test_context_prompt(self):
        self.session.add_exchange("What is Python?", "A programming language")
        context = self.session.get_context_prompt("Tell me more")
        self.assertIn("What is Python?", context)
        self.assertIn("A programming language", context)
        self.assertIn("Tell me more", context)


class TestLLMDevice(unittest.TestCase):
    """Test FUSE filesystem operations."""

    def setUp(self):
        self.device = LLMDevice(use_mock=True)

    def test_read_status(self):
        content = self.device.read("/status", 4096, 0, None)
        status = json.loads(content.decode())
        self.assertEqual(status["status"], "running")
        self.assertTrue(status["mock_mode"])

    def test_write_prompt_read_response(self):
        # Write prompt
        prompt = b"What is 2+2?"
        self.device.write("/claude/prompt", prompt, 0, None)

        # Read response
        response = self.device.read("/claude/response", 4096, 0, None)
        self.assertEqual(response.decode(), "4")

    def test_read_config(self):
        content = self.device.read("/claude/config", 4096, 0, None)
        config = json.loads(content.decode())
        self.assertIn("max_tokens", config)
        self.assertIn("temperature", config)

    def test_write_config(self):
        new_config = json.dumps({"max_tokens": 2048}).encode()
        self.device.write("/claude/config", new_config, 0, None)
        self.assertEqual(self.device.config["max_tokens"], 2048)

    def test_read_metrics(self):
        # Generate some activity
        self.device.write("/claude/prompt", b"Test", 0, None)

        content = self.device.read("/claude/metrics", 4096, 0, None)
        metrics = json.loads(content.decode())
        self.assertGreater(metrics["calls"], 0)

    def test_readdir_root(self):
        entries = self.device.readdir("/", None)
        self.assertIn("claude", entries)
        self.assertIn("sessions", entries)
        self.assertIn("status", entries)

    def test_readdir_claude(self):
        entries = self.device.readdir("/claude", None)
        self.assertIn("prompt", entries)
        self.assertIn("response", entries)
        self.assertIn("config", entries)
        self.assertIn("metrics", entries)

    def test_getattr_file(self):
        attrs = self.device.getattr("/claude/prompt")
        self.assertTrue(attrs["st_mode"] & 0o100000)  # Regular file

    def test_getattr_directory(self):
        attrs = self.device.getattr("/claude")
        self.assertTrue(attrs["st_mode"] & 0o40000)  # Directory


class TestSessionFiles(unittest.TestCase):
    """Test session file operations."""

    def setUp(self):
        self.device = LLMDevice(use_mock=True)

    def test_create_session(self):
        self.device.mkdir("/sessions/my-project", 0o755)
        self.assertIn("my-project", self.device.sessions)

    def test_session_prompt_response(self):
        # Create session
        self.device.mkdir("/sessions/test", 0o755)

        # Write prompt
        self.device._write_session_file("/sessions/test/prompt", b"What is 2+2?")

        # Read response
        content = self.device._get_session_file_content("test", "response")
        self.assertEqual(content.decode(), "4")

    def test_session_history(self):
        self.device.mkdir("/sessions/test", 0o755)
        self.device._write_session_file("/sessions/test/prompt", b"Q1")
        self.device._write_session_file("/sessions/test/prompt", b"Q2")

        history = self.device._get_session_file_content("test", "history")
        self.assertIn(b"Q1", history)
        self.assertIn(b"Q2", history)

    def test_readdir_sessions(self):
        self.device.mkdir("/sessions/project-a", 0o755)
        self.device.mkdir("/sessions/project-b", 0o755)

        entries = self.device.readdir("/sessions", None)
        self.assertIn("project-a", entries)
        self.assertIn("project-b", entries)

    def test_readdir_session_files(self):
        self.device.mkdir("/sessions/test", 0o755)

        entries = self.device.readdir("/sessions/test", None)
        self.assertIn("prompt", entries)
        self.assertIn("response", entries)
        self.assertIn("history", entries)
        self.assertIn("config", entries)


if __name__ == "__main__":
    unittest.main(verbosity=2)
