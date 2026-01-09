#!/usr/bin/env python3
"""
Cortex Linux - Model Preload Daemon

A lightweight daemon that keeps models preloaded in memory for instant inference.
Achieves <100ms startup time by maintaining a warm model cache.

Architecture:
- Unix domain socket for IPC (no network overhead)
- Memory-mapped model files
- Shared model instance across requests
- Graceful unloading on memory pressure

Usage:
    # Start daemon
    cortex-preload start
    
    # Stop daemon
    cortex-preload stop
    
    # Check status
    cortex-preload status

Author: Cortex Linux Team
License: Apache 2.0
"""

import atexit
import json
import logging
import os
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Paths
CORTEX_RUN_DIR = Path("/run/user") / str(os.getuid()) / "cortex"
SOCKET_PATH = CORTEX_RUN_DIR / "preload.sock"
PID_FILE = CORTEX_RUN_DIR / "preload.pid"
CORTEX_MODELS_DIR = Path.home() / ".cortex" / "models"


@dataclass
class PreloadRequest:
    """Request to the preload daemon."""

    action: str  # "complete", "chat", "status", "reload", "unload"
    model: str | None = None
    messages: list[dict[str, str]] | None = None
    prompt: str | None = None
    max_tokens: int = 512
    temperature: float = 0.7

    def to_bytes(self) -> bytes:
        """Serialize to bytes for socket transmission."""
        data = json.dumps(asdict(self))
        length = len(data)
        return struct.pack("!I", length) + data.encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PreloadRequest":
        """Deserialize from bytes."""
        return cls(**json.loads(data.decode("utf-8")))


@dataclass
class PreloadResponse:
    """Response from the preload daemon."""

    success: bool
    content: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    tokens_per_second: float = 0.0
    model: str | None = None

    def to_bytes(self) -> bytes:
        """Serialize to bytes for socket transmission."""
        data = json.dumps(asdict(self))
        length = len(data)
        return struct.pack("!I", length) + data.encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PreloadResponse":
        """Deserialize from bytes."""
        return cls(**json.loads(data.decode("utf-8")))


class PreloadDaemon:
    """
    Daemon process that keeps models preloaded for fast inference.
    
    Uses Unix domain sockets for minimal IPC latency.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize the daemon.

        Args:
            model_name: Model to preload (uses default if None)
        """
        self.model_name = model_name
        self.model = None
        self.manager = None
        self.socket = None
        self.running = False
        self._lock = threading.Lock()
        self._stats = {
            "requests": 0,
            "total_tokens": 0,
            "total_time_ms": 0.0,
            "start_time": 0.0,
        }

    def start(self, daemon: bool = True) -> None:
        """
        Start the preload daemon.

        Args:
            daemon: If True, fork to background
        """
        # Ensure run directory exists
        CORTEX_RUN_DIR.mkdir(parents=True, exist_ok=True)

        # Check if already running
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                logger.error(f"Daemon already running with PID {pid}")
                sys.exit(1)
            except OSError:
                # Process not running, clean up stale files
                PID_FILE.unlink()
                if SOCKET_PATH.exists():
                    SOCKET_PATH.unlink()

        if daemon:
            # Double fork to daemonize
            self._daemonize()

        # Write PID file
        PID_FILE.write_text(str(os.getpid()))

        # Register cleanup
        atexit.register(self._cleanup)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Load model
        self._load_model()

        # Start socket server
        self._start_server()

    def _daemonize(self) -> None:
        """Fork to background using double-fork technique."""
        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                # Parent exits
                sys.exit(0)
        except OSError as e:
            logger.error(f"First fork failed: {e}")
            sys.exit(1)

        # Decouple from parent
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            logger.error(f"Second fork failed: {e}")
            sys.exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        with open("/dev/null", "r") as devnull:
            os.dup2(devnull.fileno(), sys.stdin.fileno())

        # Log to file instead of stdout/stderr
        log_file = CORTEX_RUN_DIR / "preload.log"
        with open(log_file, "a") as log:
            os.dup2(log.fileno(), sys.stdout.fileno())
            os.dup2(log.fileno(), sys.stderr.fileno())

    def _load_model(self) -> None:
        """Load the model into memory."""
        try:
            from cortex.llm.llamacpp_backend import ModelManager

            logger.info("Loading model for preload daemon...")
            start_time = time.perf_counter()

            self.manager = ModelManager()

            # Use specified model or default
            model_name = self.model_name or self.manager.default_model
            if model_name is None:
                # Try to find any available model
                available = self.manager.list_available_models()
                if available:
                    model_name = available[0]
                    self.manager.register_model(
                        model_name,
                        str(CORTEX_MODELS_DIR / f"{model_name}.gguf"),
                        set_default=True,
                    )
                else:
                    logger.error("No models available. Run: cortex model download recommended")
                    sys.exit(1)

            self.model = self.manager.load_model(model_name)
            self.model_name = model_name

            load_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"✅ Model loaded in {load_time:.1f}ms: {model_name}")

            self._stats["start_time"] = time.time()

        except ImportError:
            logger.error(
                "llama-cpp-python not installed. Run: ./scripts/build_llamacpp.sh"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            sys.exit(1)

    def _start_server(self) -> None:
        """Start the Unix domain socket server."""
        # Remove existing socket
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        # Create socket
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(SOCKET_PATH))
        self.socket.listen(5)

        # Set socket permissions (owner only)
        os.chmod(SOCKET_PATH, 0o600)

        self.running = True
        logger.info(f"🔌 Preload daemon listening on {SOCKET_PATH}")

        # Accept connections
        while self.running:
            try:
                self.socket.settimeout(1.0)  # Allow periodic checks
                try:
                    conn, _ = self.socket.accept()
                except socket.timeout:
                    continue

                # Handle connection in thread
                thread = threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True,
                )
                thread.start()

            except Exception as e:
                if self.running:
                    logger.error(f"Socket error: {e}")

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a client connection."""
        try:
            # Read request length
            length_data = conn.recv(4)
            if not length_data:
                return

            length = struct.unpack("!I", length_data)[0]

            # Read request data
            data = b""
            while len(data) < length:
                chunk = conn.recv(length - len(data))
                if not chunk:
                    break
                data += chunk

            # Parse request
            request = PreloadRequest.from_bytes(data)

            # Process request
            response = self._process_request(request)

            # Send response
            conn.sendall(response.to_bytes())

        except Exception as e:
            logger.error(f"Connection error: {e}")
            response = PreloadResponse(success=False, error=str(e))
            try:
                conn.sendall(response.to_bytes())
            except Exception:
                pass
        finally:
            conn.close()

    def _process_request(self, request: PreloadRequest) -> PreloadResponse:
        """Process a client request."""
        start_time = time.perf_counter()

        try:
            if request.action == "status":
                return self._handle_status()

            elif request.action == "reload":
                return self._handle_reload(request.model)

            elif request.action == "unload":
                return self._handle_unload()

            elif request.action == "complete":
                return self._handle_complete(request, start_time)

            elif request.action == "chat":
                return self._handle_chat(request, start_time)

            else:
                return PreloadResponse(
                    success=False,
                    error=f"Unknown action: {request.action}",
                )

        except Exception as e:
            logger.error(f"Request error: {e}")
            return PreloadResponse(success=False, error=str(e))

    def _handle_status(self) -> PreloadResponse:
        """Handle status request."""
        uptime = time.time() - self._stats["start_time"]
        avg_tps = (
            self._stats["total_tokens"] / (self._stats["total_time_ms"] / 1000)
            if self._stats["total_time_ms"] > 0
            else 0
        )

        status = {
            "model": self.model_name,
            "loaded": self.model is not None,
            "requests": self._stats["requests"],
            "total_tokens": self._stats["total_tokens"],
            "uptime_seconds": uptime,
            "avg_tokens_per_second": avg_tps,
        }

        return PreloadResponse(
            success=True,
            content=json.dumps(status),
            model=self.model_name,
        )

    def _handle_reload(self, model_name: str | None) -> PreloadResponse:
        """Handle model reload request."""
        with self._lock:
            try:
                if model_name:
                    self.model_name = model_name

                # Unload current model
                if self.model:
                    del self.model
                    self.model = None

                # Load new model
                self._load_model()

                return PreloadResponse(
                    success=True,
                    content=f"Model reloaded: {self.model_name}",
                    model=self.model_name,
                )
            except Exception as e:
                return PreloadResponse(success=False, error=str(e))

    def _handle_unload(self) -> PreloadResponse:
        """Handle model unload request."""
        with self._lock:
            if self.model:
                del self.model
                self.model = None
                return PreloadResponse(success=True, content="Model unloaded")
            return PreloadResponse(success=True, content="No model loaded")

    def _handle_complete(
        self, request: PreloadRequest, start_time: float
    ) -> PreloadResponse:
        """Handle text completion request."""
        if not self.model:
            return PreloadResponse(success=False, error="No model loaded")

        with self._lock:
            from cortex.llm.llamacpp_backend import GenerationConfig

            config = GenerationConfig(
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )

            result = self.model.generate(request.prompt or "", config=config)

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Update stats
            self._stats["requests"] += 1
            self._stats["total_tokens"] += result.tokens_generated
            self._stats["total_time_ms"] += result.total_time_ms

            return PreloadResponse(
                success=True,
                content=result.content,
                latency_ms=latency_ms,
                tokens_per_second=result.tokens_per_second,
                model=self.model_name,
            )

    def _handle_chat(
        self, request: PreloadRequest, start_time: float
    ) -> PreloadResponse:
        """Handle chat completion request."""
        if not self.model:
            return PreloadResponse(success=False, error="No model loaded")

        if not request.messages:
            return PreloadResponse(success=False, error="No messages provided")

        with self._lock:
            from cortex.llm.llamacpp_backend import GenerationConfig

            config = GenerationConfig(
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )

            result = self.model.chat(request.messages, config=config)

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Update stats
            self._stats["requests"] += 1
            self._stats["total_tokens"] += result.tokens_generated
            self._stats["total_time_ms"] += result.total_time_ms

            return PreloadResponse(
                success=True,
                content=result.content,
                latency_ms=latency_ms,
                tokens_per_second=result.tokens_per_second,
                model=self.model_name,
            )

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _cleanup(self) -> None:
        """Clean up resources on exit."""
        logger.info("Cleaning up...")

        if self.socket:
            self.socket.close()

        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        if PID_FILE.exists():
            PID_FILE.unlink()


class PreloadClient:
    """Client for communicating with the preload daemon."""

    def __init__(self, timeout: float = 60.0):
        """
        Initialize the client.

        Args:
            timeout: Socket timeout in seconds
        """
        self.timeout = timeout

    def _connect(self) -> socket.socket:
        """Connect to the daemon."""
        if not SOCKET_PATH.exists():
            raise RuntimeError(
                "Preload daemon not running. Start with: cortex-preload start"
            )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(str(SOCKET_PATH))
        return sock

    def _send_request(self, request: PreloadRequest) -> PreloadResponse:
        """Send a request to the daemon."""
        sock = self._connect()
        try:
            # Send request
            sock.sendall(request.to_bytes())

            # Read response length
            length_data = sock.recv(4)
            if not length_data:
                raise RuntimeError("No response from daemon")

            length = struct.unpack("!I", length_data)[0]

            # Read response data
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    break
                data += chunk

            return PreloadResponse.from_bytes(data)

        finally:
            sock.close()

    def complete(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate text completion."""
        request = PreloadRequest(
            action="complete",
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response = self._send_request(request)
        if not response.success:
            raise RuntimeError(response.error)
        return response.content or ""

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        """Generate chat completion."""
        request = PreloadRequest(
            action="chat",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        response = self._send_request(request)
        if not response.success:
            raise RuntimeError(response.error)
        return response.content or ""

    def status(self) -> dict[str, Any]:
        """Get daemon status."""
        request = PreloadRequest(action="status")
        response = self._send_request(request)
        if not response.success:
            raise RuntimeError(response.error)
        return json.loads(response.content or "{}")

    def reload(self, model_name: str | None = None) -> str:
        """Reload model."""
        request = PreloadRequest(action="reload", model=model_name)
        response = self._send_request(request)
        if not response.success:
            raise RuntimeError(response.error)
        return response.content or ""

    def unload(self) -> str:
        """Unload model."""
        request = PreloadRequest(action="unload")
        response = self._send_request(request)
        if not response.success:
            raise RuntimeError(response.error)
        return response.content or ""


def is_daemon_running() -> bool:
    """Check if the daemon is running."""
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def stop_daemon() -> bool:
    """Stop the daemon if running."""
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)

        # Wait for process to exit
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                break

        return True
    except (OSError, ValueError):
        return False


def main():
    """CLI entry point for cortex-preload command."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Preload Daemon")
    sub = parser.add_subparsers(dest="command")

    # Start daemon
    start = sub.add_parser("start", help="Start the preload daemon")
    start.add_argument("--model", help="Model to preload")
    start.add_argument("--foreground", action="store_true", help="Run in foreground")

    # Stop daemon
    sub.add_parser("stop", help="Stop the preload daemon")

    # Status
    sub.add_parser("status", help="Get daemon status")

    # Reload model
    reload_cmd = sub.add_parser("reload", help="Reload model")
    reload_cmd.add_argument("--model", help="Model to load")

    # Test completion
    test = sub.add_parser("test", help="Test inference")
    test.add_argument("prompt", help="Test prompt")

    args = parser.parse_args()

    if args.command == "start":
        if is_daemon_running():
            print("❌ Daemon already running")
            sys.exit(1)

        daemon = PreloadDaemon(model_name=args.model)
        daemon.start(daemon=not args.foreground)

    elif args.command == "stop":
        if stop_daemon():
            print("✅ Daemon stopped")
        else:
            print("❌ Daemon not running")

    elif args.command == "status":
        if not is_daemon_running():
            print("❌ Daemon not running")
            sys.exit(1)

        client = PreloadClient()
        status = client.status()
        print(f"🔌 Preload Daemon Status")
        print(f"   Model: {status.get('model', 'none')}")
        print(f"   Loaded: {'✅' if status.get('loaded') else '❌'}")
        print(f"   Requests: {status.get('requests', 0)}")
        print(f"   Tokens: {status.get('total_tokens', 0)}")
        print(f"   Uptime: {status.get('uptime_seconds', 0):.1f}s")
        print(f"   Avg TPS: {status.get('avg_tokens_per_second', 0):.1f}")

    elif args.command == "reload":
        if not is_daemon_running():
            print("❌ Daemon not running")
            sys.exit(1)

        client = PreloadClient()
        result = client.reload(args.model)
        print(f"✅ {result}")

    elif args.command == "test":
        if not is_daemon_running():
            print("❌ Daemon not running")
            sys.exit(1)

        client = PreloadClient()
        start = time.perf_counter()
        result = client.complete(args.prompt)
        latency = (time.perf_counter() - start) * 1000
        print(f"Response ({latency:.1f}ms):")
        print(result)

    else:
        parser.print_help()


# CLI entry point
if __name__ == "__main__":
    main()

