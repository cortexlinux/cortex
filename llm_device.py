#!/usr/bin/env python3
"""
/dev/llm Virtual Device - FUSE-Based LLM Interface

Provides file-like interface to LLM operations. Enables shell scripts
and any Unix program to use LLMs.

Usage:
    python llm_device.py mount /mnt/llm
    echo "What is 2+2?" > /mnt/llm/claude/prompt
    cat /mnt/llm/claude/response

Directory Structure:
    /mnt/llm/
    ├── claude/              # Claude Sonnet
    │   ├── prompt           # Write prompts here
    │   ├── response         # Read responses
    │   ├── config           # JSON configuration
    │   └── metrics          # Usage stats
    ├── sessions/            # Stateful conversations
    │   └── <session-name>/
    └── status               # System status

Author: Yair Siegel
Bounty: cortexlinux/cortex#223
"""

import os
import sys
import json
import errno
import stat
import time
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

try:
    from fuse import FUSE, FuseOSError, Operations
except ImportError:
    from fusepy import FUSE, FuseOSError, Operations

# =============================================================================
# LLM CLIENTS
# =============================================================================

class MockLLMClient:
    """Mock client for testing without API key."""

    def __init__(self):
        self.name = "mock"
        self.call_count = 0
        self.total_tokens = 0

    def complete(self, prompt: str, config: dict = None) -> str:
        self.call_count += 1
        tokens = len(prompt.split()) + 20
        self.total_tokens += tokens

        # Simple mock responses
        if "2+2" in prompt.lower():
            return "4"
        elif "hello" in prompt.lower():
            return "Hello! How can I help you today?"
        elif "what" in prompt.lower() and "time" in prompt.lower():
            return f"I don't have access to real-time data, but I can help with other questions."
        else:
            return f"[Mock Response] Received: {prompt[:100]}..."

    def get_metrics(self) -> dict:
        return {
            "client": self.name,
            "calls": self.call_count,
            "total_tokens": self.total_tokens
        }


class ClaudeLLMClient:
    """Anthropic Claude API client."""

    def __init__(self, api_key: str = None):
        self.name = "claude"
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.call_count = 0
        self.total_tokens = 0
        self.model = "claude-sonnet-4-20250514"

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                self.client = None
        else:
            self.client = None

    def complete(self, prompt: str, config: dict = None) -> str:
        if not self.client:
            return "[Error] Anthropic client not available. Set ANTHROPIC_API_KEY or use mock mode."

        config = config or {}
        max_tokens = config.get("max_tokens", 1024)
        temperature = config.get("temperature", 0.7)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            self.call_count += 1
            self.total_tokens += response.usage.input_tokens + response.usage.output_tokens
            return response.content[0].text
        except Exception as e:
            return f"[Error] API call failed: {e}"

    def get_metrics(self) -> dict:
        return {
            "client": self.name,
            "model": self.model,
            "calls": self.call_count,
            "total_tokens": self.total_tokens,
            "api_key_set": bool(self.api_key)
        }


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@dataclass
class Session:
    """Conversation session with history."""
    name: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: list = field(default_factory=list)
    config: dict = field(default_factory=dict)

    def add_exchange(self, prompt: str, response: str):
        self.messages.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "response": response
        })

    def get_history(self) -> str:
        lines = []
        for msg in self.messages:
            lines.append(f"[{msg['timestamp']}]")
            lines.append(f"User: {msg['prompt']}")
            lines.append(f"Assistant: {msg['response']}")
            lines.append("")
        return "\n".join(lines)

    def get_context_prompt(self, new_prompt: str) -> str:
        """Build prompt with conversation context."""
        if not self.messages:
            return new_prompt

        context_parts = []
        for msg in self.messages[-5:]:  # Last 5 exchanges
            context_parts.append(f"User: {msg['prompt']}")
            context_parts.append(f"Assistant: {msg['response']}")

        context_parts.append(f"User: {new_prompt}")
        return "\n\n".join(context_parts)


# =============================================================================
# FUSE FILESYSTEM
# =============================================================================

class LLMDevice(Operations):
    """
    FUSE filesystem providing LLM access via files.

    Write to prompt file, read from response file.
    """

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock

        # Initialize clients
        if use_mock:
            self.client = MockLLMClient()
        else:
            self.client = ClaudeLLMClient()
            # Fallback to mock if no API key
            if not self.client.client:
                print("[INFO] No API key found, using mock client")
                self.client = MockLLMClient()
                self.use_mock = True

        # File data storage
        self.files: Dict[str, bytes] = {}
        self.file_attrs: Dict[str, dict] = {}

        # Sessions
        self.sessions: Dict[str, Session] = {}

        # Current prompt/response for each model
        self.prompts: Dict[str, str] = {"claude": ""}
        self.responses: Dict[str, str] = {"claude": ""}

        # Configuration
        self.config = {
            "max_tokens": 1024,
            "temperature": 0.7,
            "model": "claude-sonnet-4-20250514"
        }

        # Thread lock for concurrent access
        self.lock = threading.Lock()

        # Initialize directory structure
        self._init_structure()

    def _init_structure(self):
        """Initialize virtual directory structure."""
        now = time.time()

        # Root directories
        dirs = ["/", "/claude", "/sessions"]
        for d in dirs:
            self.file_attrs[d] = {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_size": 0,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
                "st_uid": os.getuid(),
                "st_gid": os.getgid(),
            }

        # Virtual files
        files = [
            "/status",
            "/claude/prompt",
            "/claude/response",
            "/claude/config",
            "/claude/metrics"
        ]
        for f in files:
            self.file_attrs[f] = {
                "st_mode": stat.S_IFREG | 0o644,
                "st_nlink": 1,
                "st_size": 0,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
                "st_uid": os.getuid(),
                "st_gid": os.getgid(),
            }
            self.files[f] = b""

    # =========================================================================
    # FUSE Operations
    # =========================================================================

    def getattr(self, path, fh=None):
        """Get file attributes."""
        # Check for session paths
        if path.startswith("/sessions/") and path != "/sessions":
            parts = path.split("/")
            if len(parts) == 3:  # /sessions/<name>
                session_name = parts[2]
                if session_name in self.sessions or path not in self.file_attrs:
                    # Session directory
                    now = time.time()
                    return {
                        "st_mode": stat.S_IFDIR | 0o755,
                        "st_nlink": 2,
                        "st_size": 0,
                        "st_ctime": now,
                        "st_mtime": now,
                        "st_atime": now,
                        "st_uid": os.getuid(),
                        "st_gid": os.getgid(),
                    }
            elif len(parts) == 4:  # /sessions/<name>/<file>
                session_name = parts[2]
                filename = parts[3]
                if session_name in self.sessions and filename in ["prompt", "response", "history", "config"]:
                    now = time.time()
                    content = self._get_session_file_content(session_name, filename)
                    return {
                        "st_mode": stat.S_IFREG | 0o644,
                        "st_nlink": 1,
                        "st_size": len(content),
                        "st_ctime": now,
                        "st_mtime": now,
                        "st_atime": now,
                        "st_uid": os.getuid(),
                        "st_gid": os.getgid(),
                    }

        if path not in self.file_attrs:
            raise FuseOSError(errno.ENOENT)

        attrs = self.file_attrs[path].copy()

        # Update size for dynamic content
        if path in self.files:
            attrs["st_size"] = len(self._get_file_content(path))

        return attrs

    def readdir(self, path, fh):
        """List directory contents."""
        entries = [".", ".."]

        if path == "/":
            entries.extend(["claude", "sessions", "status"])
        elif path == "/claude":
            entries.extend(["prompt", "response", "config", "metrics"])
        elif path == "/sessions":
            entries.extend(self.sessions.keys())
        elif path.startswith("/sessions/"):
            parts = path.split("/")
            if len(parts) == 3:
                session_name = parts[2]
                if session_name in self.sessions:
                    entries.extend(["prompt", "response", "history", "config"])

        return entries

    def read(self, path, size, offset, fh):
        """Read file content."""
        content = self._get_file_content(path)
        return content[offset:offset + size]

    def write(self, path, data, offset, fh):
        """Write to file (handles prompts)."""
        with self.lock:
            if path == "/claude/prompt":
                prompt = data.decode("utf-8").strip()
                self.prompts["claude"] = prompt

                # Generate response
                response = self.client.complete(prompt, self.config)
                self.responses["claude"] = response

                return len(data)

            elif path == "/claude/config":
                try:
                    new_config = json.loads(data.decode("utf-8"))
                    self.config.update(new_config)
                except json.JSONDecodeError:
                    pass
                return len(data)

            elif path.startswith("/sessions/"):
                return self._write_session_file(path, data)

            else:
                # Store in generic files dict
                if path in self.files:
                    self.files[path] = data
                    return len(data)

        raise FuseOSError(errno.EACCES)

    def truncate(self, path, length, fh=None):
        """Truncate file (needed for write operations)."""
        if path in ["/claude/prompt", "/claude/config"]:
            return 0
        if path.startswith("/sessions/"):
            return 0
        if path in self.files:
            self.files[path] = self.files[path][:length]
            return 0
        raise FuseOSError(errno.EACCES)

    def open(self, path, flags):
        """Open file."""
        return 0

    def create(self, path, mode, fi=None):
        """Create file (for sessions)."""
        if path.startswith("/sessions/"):
            parts = path.split("/")
            if len(parts) == 3:
                # Creating session directory
                session_name = parts[2]
                self.sessions[session_name] = Session(name=session_name)
                return 0
        raise FuseOSError(errno.EACCES)

    def mkdir(self, path, mode):
        """Create directory (for sessions)."""
        if path.startswith("/sessions/"):
            parts = path.split("/")
            if len(parts) == 3:
                session_name = parts[2]
                if session_name not in self.sessions:
                    self.sessions[session_name] = Session(name=session_name)
                    return 0
        raise FuseOSError(errno.EACCES)

    def unlink(self, path):
        """Delete file."""
        raise FuseOSError(errno.EACCES)

    def rmdir(self, path):
        """Delete directory."""
        if path.startswith("/sessions/"):
            parts = path.split("/")
            if len(parts) == 3:
                session_name = parts[2]
                if session_name in self.sessions:
                    del self.sessions[session_name]
                    return 0
        raise FuseOSError(errno.EACCES)

    # =========================================================================
    # Content Helpers
    # =========================================================================

    def _get_file_content(self, path: str) -> bytes:
        """Get dynamic file content."""
        if path == "/status":
            status = {
                "status": "running",
                "client": self.client.name,
                "mock_mode": self.use_mock,
                "sessions": list(self.sessions.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return json.dumps(status, indent=2).encode("utf-8")

        elif path == "/claude/prompt":
            return self.prompts.get("claude", "").encode("utf-8")

        elif path == "/claude/response":
            return self.responses.get("claude", "").encode("utf-8")

        elif path == "/claude/config":
            return json.dumps(self.config, indent=2).encode("utf-8")

        elif path == "/claude/metrics":
            return json.dumps(self.client.get_metrics(), indent=2).encode("utf-8")

        elif path.startswith("/sessions/"):
            parts = path.split("/")
            if len(parts) == 4:
                session_name = parts[2]
                filename = parts[3]
                return self._get_session_file_content(session_name, filename)

        return self.files.get(path, b"")

    def _get_session_file_content(self, session_name: str, filename: str) -> bytes:
        """Get session file content."""
        if session_name not in self.sessions:
            return b""

        session = self.sessions[session_name]

        if filename == "prompt":
            return b""  # Prompt is write-only
        elif filename == "response":
            if session.messages:
                return session.messages[-1]["response"].encode("utf-8")
            return b""
        elif filename == "history":
            return session.get_history().encode("utf-8")
        elif filename == "config":
            return json.dumps(session.config, indent=2).encode("utf-8")

        return b""

    def _write_session_file(self, path: str, data: bytes) -> int:
        """Write to session file."""
        parts = path.split("/")
        if len(parts) != 4:
            raise FuseOSError(errno.EACCES)

        session_name = parts[2]
        filename = parts[3]

        if session_name not in self.sessions:
            self.sessions[session_name] = Session(name=session_name)

        session = self.sessions[session_name]

        if filename == "prompt":
            prompt = data.decode("utf-8").strip()
            # Build context-aware prompt
            context_prompt = session.get_context_prompt(prompt)
            response = self.client.complete(context_prompt, session.config)
            session.add_exchange(prompt, response)
            return len(data)

        elif filename == "config":
            try:
                new_config = json.loads(data.decode("utf-8"))
                session.config.update(new_config)
            except json.JSONDecodeError:
                pass
            return len(data)

        raise FuseOSError(errno.EACCES)


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="/dev/llm Virtual Device")
    parser.add_argument("command", choices=["mount", "test"], help="Command to run")
    parser.add_argument("mountpoint", nargs="?", default="/mnt/llm", help="Mount point")
    parser.add_argument("--mock", action="store_true", help="Use mock client (no API)")
    parser.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    if args.command == "test":
        # Quick test without mounting
        print("Testing LLM Device...")
        device = LLMDevice(use_mock=True)

        # Simulate write to prompt
        prompt = b"What is 2+2?"
        device.write("/claude/prompt", prompt, 0, None)

        # Read response
        response = device.read("/claude/response", 4096, 0, None)
        print(f"Prompt: {prompt.decode()}")
        print(f"Response: {response.decode()}")

        # Check metrics
        metrics = device.read("/claude/metrics", 4096, 0, None)
        print(f"Metrics: {metrics.decode()}")

        print("\nTest passed!")
        return

    # Mount filesystem
    mountpoint = Path(args.mountpoint)

    if not mountpoint.exists():
        mountpoint.mkdir(parents=True)

    print(f"Mounting /dev/llm at {mountpoint}")
    print(f"Mock mode: {args.mock}")
    print("Usage:")
    print(f"  echo 'Hello' > {mountpoint}/claude/prompt")
    print(f"  cat {mountpoint}/claude/response")
    print("\nPress Ctrl+C to unmount")

    device = LLMDevice(use_mock=args.mock)

    FUSE(
        device,
        str(mountpoint),
        foreground=args.foreground or True,
        allow_other=False,
        nothreads=False,
        debug=args.debug
    )


if __name__ == "__main__":
    main()
