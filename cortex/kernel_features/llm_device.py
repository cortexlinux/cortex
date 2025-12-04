#!/usr/bin/env python3
"""
Cortex /dev/llm Virtual Device

FUSE-based LLM interface - everything is a file.

Features:
- Multiple model endpoints (claude, sonnet, haiku)
- Session management via directories
- Configuration via JSON files
- Conversation history tracking
- Metrics and usage statistics
- Mock client for testing without API key

Usage:
    cortex-llm-device mount /mnt/llm
    echo "What is 2+2?" > /mnt/llm/claude/prompt
    cat /mnt/llm/claude/response
"""

import os
import sys
import json
import time
import stat
import errno
import logging
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('llm_device')

# Try to import FUSE
try:
    from fuse import FUSE, FuseOSError, Operations
    HAS_FUSE = True
except ImportError:
    HAS_FUSE = False
    logger.warning("fusepy not installed - mount will not work")

    class FuseOSError(Exception):
        """Fallback FuseOSError for when fusepy is not installed."""
        def __init__(self, errno_val):
            self.errno = errno_val
            super().__init__(f"FUSE error: {errno_val}")

    class Operations:
        """Fallback Operations base class."""
        pass

# Try to import Anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    logger.warning("anthropic not installed - using mock client")


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SessionConfig:
    """Configuration for an LLM session."""
    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> 'SessionConfig':
        try:
            return cls(**json.loads(data))
        except (json.JSONDecodeError, TypeError):
            return cls()


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    """An LLM conversation session."""
    id: str
    config: SessionConfig = field(default_factory=SessionConfig)
    messages: List[Message] = field(default_factory=list)
    prompt_buffer: str = ""
    response_buffer: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    request_count: int = 0
    total_tokens: int = 0

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.messages.append(Message(role=role, content=content))
        self.last_active = time.time()

    def get_history(self) -> str:
        """Get formatted conversation history."""
        lines = []
        for msg in self.messages:
            ts = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            prefix = "USER" if msg.role == "user" else "ASSISTANT"
            lines.append(f"[{ts}] {prefix}:\n{msg.content}\n")
        return "\n".join(lines)

    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages in API format."""
        return [msg.to_dict() for msg in self.messages]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self.prompt_buffer = ""
        self.response_buffer = ""


@dataclass
class Metrics:
    """Usage metrics for the LLM device."""
    start_time: float = field(default_factory=time.time)
    total_requests: int = 0
    total_tokens: int = 0
    total_errors: int = 0
    sessions_created: int = 0
    last_request_time: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps({
            "status": "running",
            "uptime_seconds": time.time() - self.start_time,
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_errors": self.total_errors,
            "sessions_created": self.sessions_created,
            "last_request": self.last_request_time,
            "requests_per_minute": self._calc_rpm()
        }, indent=2)

    def _calc_rpm(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed < 60:
            return self.total_requests
        return round(self.total_requests / (elapsed / 60), 2)


# ============================================================================
# LLM Clients
# ============================================================================

class MockLLMClient:
    """Mock LLM client for testing without API key."""

    MOCK_RESPONSES = [
        "I understand your question. Let me think about that...",
        "That's an interesting point! Here's my analysis:",
        "Based on the context provided, I would suggest:",
        "Great question! The answer involves several factors:",
    ]

    def __init__(self, latency: float = 0.1):
        self.latency = latency
        self._call_count = 0

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system: Optional[str] = None
    ) -> Tuple[str, int]:
        """Generate a mock response."""
        time.sleep(self.latency)  # Simulate API latency

        self._call_count += 1
        last_msg = messages[-1]["content"] if messages else "empty"

        # Generate contextual mock response
        import random
        prefix = random.choice(self.MOCK_RESPONSES)
        response = f"[Mock Response #{self._call_count}]\n{prefix}\n\nYou asked: \"{last_msg[:100]}...\"\n\nThis is a mock response. Set ANTHROPIC_API_KEY for real responses."

        # Estimate tokens (rough approximation)
        tokens = len(response.split()) + sum(len(m["content"].split()) for m in messages)

        return response, tokens


class AnthropicLLMClient:
    """Real Anthropic API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system: Optional[str] = None
    ) -> Tuple[str, int]:
        """Call Anthropic API and return response with token count."""
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        text = response.content[0].text if response.content else ""
        tokens = response.usage.input_tokens + response.usage.output_tokens

        return text, tokens


# ============================================================================
# FUSE Filesystem Implementation
# ============================================================================

class LLMDevice(Operations):
    """FUSE filesystem providing file-based LLM interface."""

    # Model name to API model ID mapping
    MODELS = {
        "claude": "claude-3-5-sonnet-20241022",
        "sonnet": "claude-3-5-sonnet-20241022",
        "haiku": "claude-3-5-haiku-20241022",
        "opus": "claude-3-opus-20240229",
    }

    # Files available in model directories
    MODEL_FILES = ["prompt", "response", "config", "metrics"]

    # Files available in session directories
    SESSION_FILES = ["prompt", "response", "config", "history", "clear"]

    def __init__(self, use_mock: bool = False):
        """Initialize the LLM device filesystem.

        Args:
            use_mock: Force mock client even if API key is available
        """
        self.sessions: Dict[str, Session] = {}
        self.metrics = Metrics()
        self._lock = threading.Lock()

        # Initialize LLM client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if use_mock or not api_key or not HAS_ANTHROPIC:
            self.llm = MockLLMClient()
            self._using_mock = True
            logger.info("Using mock LLM client")
        else:
            self.llm = AnthropicLLMClient(api_key)
            self._using_mock = False
            logger.info("Using Anthropic API client")

        # Create default session
        self._create_session("default")

    def _create_session(self, session_id: str) -> Session:
        """Create a new session."""
        with self._lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = Session(id=session_id)
                self.metrics.sessions_created += 1
                logger.info(f"Created session: {session_id}")
            return self.sessions[session_id]

    def _get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def _delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self.sessions and session_id != "default":
                del self.sessions[session_id]
                logger.info(f"Deleted session: {session_id}")
                return True
            return False

    def _parse_path(self, path: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse a filesystem path into (type, name, file).

        Returns:
            Tuple of (path_type, model_or_session_name, filename)

        Path types:
            - 'root': /
            - 'model': /claude, /sonnet, etc
            - 'model_file': /claude/prompt, /claude/response, etc
            - 'sessions': /sessions
            - 'session': /sessions/my-session
            - 'session_file': /sessions/my-session/prompt
            - 'status': /status
            - 'unknown': anything else
        """
        parts = [p for p in path.strip('/').split('/') if p]

        if not parts:
            return ('root', None, None)

        if parts[0] == 'status':
            return ('status', None, None)

        if parts[0] in self.MODELS:
            if len(parts) == 1:
                return ('model', parts[0], None)
            if parts[1] in self.MODEL_FILES:
                return ('model_file', parts[0], parts[1])
            return ('unknown', None, None)

        if parts[0] == 'sessions':
            if len(parts) == 1:
                return ('sessions', None, None)
            session_id = parts[1]
            if len(parts) == 2:
                return ('session', session_id, None)
            if parts[2] in self.SESSION_FILES:
                return ('session_file', session_id, parts[2])
            return ('unknown', None, None)

        return ('unknown', None, None)

    def _make_stat(self, is_dir: bool = False, size: int = 0) -> Dict[str, Any]:
        """Create stat structure for getattr."""
        now = time.time()
        if is_dir:
            return {
                'st_mode': stat.S_IFDIR | 0o755,
                'st_nlink': 2,
                'st_uid': os.getuid(),
                'st_gid': os.getgid(),
                'st_atime': now,
                'st_mtime': now,
                'st_ctime': now,
            }
        return {
            'st_mode': stat.S_IFREG | 0o644,
            'st_nlink': 1,
            'st_uid': os.getuid(),
            'st_gid': os.getgid(),
            'st_size': size,
            'st_atime': now,
            'st_mtime': now,
            'st_ctime': now,
        }

    # ========================================================================
    # FUSE Operations
    # ========================================================================

    def getattr(self, path: str, fh: Optional[int] = None) -> Dict[str, Any]:
        """Get file attributes."""
        ptype, name, filename = self._parse_path(path)

        # Directories
        if ptype in ('root', 'model', 'sessions'):
            return self._make_stat(is_dir=True)

        if ptype == 'session':
            if name in self.sessions or name == 'default':
                return self._make_stat(is_dir=True)
            raise FuseOSError(errno.ENOENT)

        # Files
        if ptype == 'status':
            return self._make_stat(size=len(self.metrics.to_json()))

        if ptype == 'model_file':
            session = self._get_session("default")
            if filename == 'response' and session:
                return self._make_stat(size=len(session.response_buffer.encode()))
            if filename == 'config' and session:
                return self._make_stat(size=len(session.config.to_json()))
            return self._make_stat(size=0)

        if ptype == 'session_file':
            session = self._get_session(name)
            if not session:
                raise FuseOSError(errno.ENOENT)
            if filename == 'response':
                return self._make_stat(size=len(session.response_buffer.encode()))
            if filename == 'history':
                return self._make_stat(size=len(session.get_history().encode()))
            if filename == 'config':
                return self._make_stat(size=len(session.config.to_json()))
            return self._make_stat(size=0)

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path: str, fh: Optional[int] = None) -> List[str]:
        """List directory contents."""
        ptype, name, _ = self._parse_path(path)
        base = ['.', '..']

        if ptype == 'root':
            return base + list(self.MODELS.keys()) + ['sessions', 'status']

        if ptype == 'model':
            return base + self.MODEL_FILES

        if ptype == 'sessions':
            return base + list(self.sessions.keys())

        if ptype == 'session':
            if name in self.sessions:
                return base + self.SESSION_FILES

        return base

    def read(self, path: str, size: int, offset: int, fh: Optional[int] = None) -> bytes:
        """Read from a file."""
        ptype, name, filename = self._parse_path(path)

        if ptype == 'status':
            data = self.metrics.to_json().encode()
            return data[offset:offset + size]

        if ptype == 'model_file':
            session = self._get_session("default")
            if not session:
                return b""

            if filename == 'response':
                data = session.response_buffer.encode()
            elif filename == 'config':
                data = session.config.to_json().encode()
            elif filename == 'metrics':
                data = json.dumps({
                    "requests": session.request_count,
                    "tokens": session.total_tokens,
                    "messages": len(session.messages)
                }, indent=2).encode()
            else:
                data = b""

            return data[offset:offset + size]

        if ptype == 'session_file':
            session = self._get_session(name)
            if not session:
                return b""

            if filename == 'response':
                data = session.response_buffer.encode()
            elif filename == 'history':
                data = session.get_history().encode()
            elif filename == 'config':
                data = session.config.to_json().encode()
            else:
                data = b""

            return data[offset:offset + size]

        return b""

    def write(self, path: str, data: bytes, offset: int, fh: Optional[int] = None) -> int:
        """Write to a file."""
        ptype, name, filename = self._parse_path(path)
        text = data.decode('utf-8', errors='replace').strip()

        if ptype == 'model_file' and filename == 'prompt':
            return self._handle_prompt("default", name, text, len(data))

        if ptype == 'model_file' and filename == 'config':
            session = self._get_session("default")
            if session:
                session.config = SessionConfig.from_json(text)
                logger.info(f"Updated default session config")
            return len(data)

        if ptype == 'session_file':
            session = self._get_session(name)
            if not session:
                session = self._create_session(name)

            if filename == 'prompt':
                return self._handle_prompt(name, None, text, len(data))

            if filename == 'config':
                session.config = SessionConfig.from_json(text)
                logger.info(f"Updated session {name} config")
                return len(data)

            if filename == 'clear':
                session.clear_history()
                logger.info(f"Cleared session {name} history")
                return len(data)

        raise FuseOSError(errno.EACCES)

    def _handle_prompt(self, session_id: str, model_override: Optional[str], prompt: str, data_len: int) -> int:
        """Process a prompt and generate response."""
        session = self._get_session(session_id) or self._create_session(session_id)

        # Determine model to use
        if model_override and model_override in self.MODELS:
            model = self.MODELS[model_override]
        else:
            model = session.config.model

        # Store prompt
        session.prompt_buffer = prompt
        session.add_message("user", prompt)

        try:
            # Call LLM
            response, tokens = self.llm.complete(
                model=model,
                messages=session.get_messages_for_api(),
                max_tokens=session.config.max_tokens,
                temperature=session.config.temperature,
                system=session.config.system_prompt or None
            )

            # Store response
            session.response_buffer = response
            session.add_message("assistant", response)
            session.request_count += 1
            session.total_tokens += tokens

            # Update metrics
            with self._lock:
                self.metrics.total_requests += 1
                self.metrics.total_tokens += tokens
                self.metrics.last_request_time = time.time()

            logger.info(f"Completed request for session {session_id}: {tokens} tokens")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            session.response_buffer = error_msg

            with self._lock:
                self.metrics.total_errors += 1

            logger.error(f"Request failed for session {session_id}: {e}")

        return data_len

    def mkdir(self, path: str, mode: int) -> int:
        """Create a directory (session)."""
        ptype, name, _ = self._parse_path(path)

        # Only allow creating sessions
        if ptype == 'session' and name:
            self._create_session(name)
            return 0

        raise FuseOSError(errno.EACCES)

    def rmdir(self, path: str) -> int:
        """Remove a directory (session)."""
        ptype, name, _ = self._parse_path(path)

        if ptype == 'session' and name:
            if self._delete_session(name):
                return 0
            raise FuseOSError(errno.ENOTEMPTY if name == "default" else errno.ENOENT)

        raise FuseOSError(errno.EACCES)

    def truncate(self, path: str, length: int, fh: Optional[int] = None) -> int:
        """Truncate a file."""
        return 0

    def open(self, path: str, flags: int) -> int:
        """Open a file."""
        return 0

    def create(self, path: str, mode: int, fi: Optional[Any] = None) -> int:
        """Create a file."""
        return 0

    def unlink(self, path: str) -> int:
        """Delete a file."""
        # Allow "deleting" clear file to clear session
        ptype, name, filename = self._parse_path(path)
        if ptype == 'session_file' and filename == 'clear':
            session = self._get_session(name)
            if session:
                session.clear_history()
                return 0
        raise FuseOSError(errno.EACCES)


# ============================================================================
# Mount/Unmount Functions
# ============================================================================

def mount(mountpoint: str, foreground: bool = False, use_mock: bool = False) -> None:
    """Mount the LLM device filesystem.

    Args:
        mountpoint: Directory to mount at
        foreground: Run in foreground (for debugging)
        use_mock: Use mock client instead of real API
    """
    if not HAS_FUSE:
        print("Error: fusepy not installed")
        print("Install with: pip install fusepy")
        sys.exit(1)

    # Ensure mountpoint exists
    Path(mountpoint).mkdir(parents=True, exist_ok=True)

    print(f"Mounting /dev/llm at {mountpoint}")
    print()
    print("Usage:")
    print(f'  echo "Hello" > {mountpoint}/claude/prompt')
    print(f'  cat {mountpoint}/claude/response')
    print()
    print(f'  mkdir {mountpoint}/sessions/my-project')
    print(f'  echo "Help me code" > {mountpoint}/sessions/my-project/prompt')
    print(f'  cat {mountpoint}/sessions/my-project/history')
    print()

    if use_mock or not os.environ.get("ANTHROPIC_API_KEY"):
        print("Note: Using mock client (set ANTHROPIC_API_KEY for real responses)")

    # Mount filesystem
    FUSE(
        LLMDevice(use_mock=use_mock),
        mountpoint,
        foreground=foreground,
        allow_other=False,
        nothreads=False
    )


def unmount(mountpoint: str) -> None:
    """Unmount the LLM device filesystem."""
    import subprocess
    try:
        subprocess.run(["fusermount", "-u", mountpoint], check=True)
        print(f"Unmounted {mountpoint}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to unmount: {e}")
        sys.exit(1)


# ============================================================================
# CLI Entry Point
# ============================================================================

def main() -> None:
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cortex /dev/llm Virtual Device - File-based LLM Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Mount the device:
    cortex-llm-device mount /mnt/llm

  Use with shell:
    echo "What is 2+2?" > /mnt/llm/claude/prompt
    cat /mnt/llm/claude/response

  Create a session:
    mkdir /mnt/llm/sessions/my-project
    echo "Hello" > /mnt/llm/sessions/my-project/prompt
    cat /mnt/llm/sessions/my-project/history
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Mount command
    mount_parser = subparsers.add_parser("mount", help="Mount the LLM device")
    mount_parser.add_argument("mountpoint", help="Directory to mount at")
    mount_parser.add_argument("-f", "--foreground", action="store_true",
                              help="Run in foreground")
    mount_parser.add_argument("--mock", action="store_true",
                              help="Use mock client (no API calls)")

    # Unmount command
    umount_parser = subparsers.add_parser("umount", help="Unmount the LLM device")
    umount_parser.add_argument("mountpoint", help="Directory to unmount")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check if fusepy is available")

    args = parser.parse_args()

    if args.command == "mount":
        mount(args.mountpoint, args.foreground, args.mock)
    elif args.command == "umount":
        unmount(args.mountpoint)
    elif args.command == "status":
        print(f"fusepy available: {HAS_FUSE}")
        print(f"anthropic available: {HAS_ANTHROPIC}")
        print(f"ANTHROPIC_API_KEY set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
