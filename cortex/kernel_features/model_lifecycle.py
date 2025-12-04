#!/usr/bin/env python3
"""
Cortex Model Lifecycle Manager

Manages LLM models as first-class system services using systemd.
Provides health monitoring, auto-restart, resource limits, and security hardening.

Usage:
    cortex model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm --gpus 0,1
    cortex model start llama-70b
    cortex model status
    cortex model enable llama-70b  # auto-start on boot
    cortex model logs llama-70b
"""

import os
import sys
import json
import subprocess
import sqlite3
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from enum import Enum


# Configuration paths
CORTEX_DB_PATH = Path.home() / ".cortex/models.db"
CORTEX_SERVICE_DIR = Path.home() / ".config/systemd/user"
CORTEX_LOG_DIR = Path.home() / ".cortex/logs"


class ModelState(Enum):
    """Model service states."""
    UNKNOWN = "unknown"
    INACTIVE = "inactive"
    ACTIVATING = "activating"
    ACTIVE = "active"
    DEACTIVATING = "deactivating"
    FAILED = "failed"
    RELOADING = "reloading"


class EventType(Enum):
    """Event types for logging."""
    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNREGISTERED = "unregistered"
    HEALTH_CHECK_FAILED = "health_check_failed"
    HEALTH_CHECK_PASSED = "health_check_passed"
    AUTO_RESTARTED = "auto_restarted"
    CONFIG_UPDATED = "config_updated"
    ERROR = "error"


@dataclass
class HealthCheckConfig:
    """Health check configuration for model services."""
    enabled: bool = True
    endpoint: str = "/health"
    interval_seconds: int = 30
    timeout_seconds: int = 10
    max_failures: int = 3
    startup_delay_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HealthCheckConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ResourceLimits:
    """Resource limits for model services."""
    memory_max: str = "32G"
    memory_high: str = "28G"
    cpu_quota: float = 4.0  # Number of CPU cores
    cpu_weight: int = 100  # 1-10000, default 100
    io_weight: int = 100  # 1-10000, default 100
    tasks_max: int = 512  # Max number of processes/threads

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceLimits':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SecurityConfig:
    """Security hardening configuration."""
    no_new_privileges: bool = True
    protect_system: str = "strict"  # "true", "full", "strict"
    protect_home: str = "read-only"  # "true", "read-only", "tmpfs"
    private_tmp: bool = True
    private_devices: bool = False  # False to allow GPU access
    restrict_realtime: bool = True
    restrict_suid_sgid: bool = True
    protect_kernel_tunables: bool = True
    protect_kernel_modules: bool = True
    protect_control_groups: bool = True
    memory_deny_write_execute: bool = False  # False for JIT compilation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ModelConfig:
    """Complete model configuration."""
    name: str
    model_path: str
    backend: str = "vllm"
    port: int = 8000
    host: str = "127.0.0.1"
    gpu_memory_fraction: float = 0.9
    max_model_len: int = 4096
    gpu_ids: List[int] = field(default_factory=lambda: [0])
    tensor_parallel_size: int = 1
    quantization: Optional[str] = None  # awq, gptq, squeezellm
    dtype: str = "auto"  # auto, float16, bfloat16
    extra_args: str = ""
    restart_policy: str = "on-failure"
    restart_max_retries: int = 5
    preload_on_boot: bool = False
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    environment: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelConfig':
        # Handle nested dataclasses
        if 'health_check' in data and isinstance(data['health_check'], dict):
            data['health_check'] = HealthCheckConfig.from_dict(data['health_check'])
        if 'resources' in data and isinstance(data['resources'], dict):
            data['resources'] = ResourceLimits.from_dict(data['resources'])
        if 'security' in data and isinstance(data['security'], dict):
            data['security'] = SecurityConfig.from_dict(data['security'])

        # Filter to valid fields
        valid_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def get_health_url(self) -> str:
        """Get the health check URL."""
        endpoint = self.health_check.endpoint
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return f"http://{self.host}:{self.port}{endpoint}"


class ModelDatabase:
    """SQLite database for model configuration and event persistence."""

    def __init__(self, db_path: Path = CORTEX_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS models (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (model_name) REFERENCES models(name)
                );

                CREATE INDEX IF NOT EXISTS idx_events_model ON events(model_name);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            """)

    def save_model(self, config: ModelConfig) -> None:
        """Save or update model configuration."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO models (name, config, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    config = excluded.config,
                    updated_at = excluded.updated_at
            """, (config.name, json.dumps(config.to_dict()), now, now))

    def get_model(self, name: str) -> Optional[ModelConfig]:
        """Get model configuration by name."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config FROM models WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return ModelConfig.from_dict(json.loads(row[0]))
        return None

    def list_models(self) -> List[ModelConfig]:
        """List all registered models."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT config FROM models ORDER BY name").fetchall()
            return [ModelConfig.from_dict(json.loads(r[0])) for r in rows]

    def delete_model(self, name: str) -> bool:
        """Delete model configuration."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM models WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def log_event(self, model_name: str, event_type: EventType, details: str = None) -> None:
        """Log an event for a model."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO events (model_name, event_type, details, timestamp) VALUES (?, ?, ?, ?)",
                (model_name, event_type.value, details, now)
            )

    def get_events(self, model_name: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events, optionally filtered by model name."""
        with sqlite3.connect(self.db_path) as conn:
            if model_name:
                rows = conn.execute(
                    "SELECT model_name, event_type, details, timestamp FROM events "
                    "WHERE model_name = ? ORDER BY timestamp DESC LIMIT ?",
                    (model_name, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT model_name, event_type, details, timestamp FROM events "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()

            return [
                {"model": r[0], "event": r[1], "details": r[2], "timestamp": r[3]}
                for r in rows
            ]


class ServiceGenerator:
    """Generate systemd service files for LLM backends."""

    # Backend command templates
    BACKENDS = {
        "vllm": (
            "python -m vllm.entrypoints.openai.api_server "
            "--model {model_path} "
            "--host {host} "
            "--port {port} "
            "--gpu-memory-utilization {gpu_memory_fraction} "
            "--max-model-len {max_model_len} "
            "--tensor-parallel-size {tensor_parallel_size} "
            "{quantization_arg} "
            "{dtype_arg} "
            "{extra_args}"
        ),
        "llamacpp": (
            "llama-server "
            "-m {model_path} "
            "--host {host} "
            "--port {port} "
            "-ngl 99 "
            "-c {max_model_len} "
            "{extra_args}"
        ),
        "ollama": "ollama serve",
        "tgi": (
            "text-generation-launcher "
            "--model-id {model_path} "
            "--hostname {host} "
            "--port {port} "
            "--max-input-length {max_model_len} "
            "--max-total-tokens {max_total_tokens} "
            "--num-shard {tensor_parallel_size} "
            "{quantization_arg} "
            "{dtype_arg} "
            "{extra_args}"
        ),
    }

    # Health check endpoints by backend
    HEALTH_ENDPOINTS = {
        "vllm": "/health",
        "llamacpp": "/health",
        "ollama": "/api/tags",
        "tgi": "/health",
    }

    def _get_command(self, config: ModelConfig) -> str:
        """Build the execution command for the backend."""
        template = self.BACKENDS.get(config.backend, self.BACKENDS["vllm"])

        # Build optional arguments
        quantization_arg = ""
        if config.quantization:
            if config.backend == "vllm":
                quantization_arg = f"--quantization {config.quantization}"
            elif config.backend == "tgi":
                quantization_arg = f"--quantize {config.quantization}"

        dtype_arg = ""
        if config.dtype != "auto":
            if config.backend == "vllm":
                dtype_arg = f"--dtype {config.dtype}"
            elif config.backend == "tgi":
                dtype_arg = f"--dtype {config.dtype}"

        # Calculate max total tokens for TGI
        max_total_tokens = config.max_model_len * 2

        cmd = template.format(
            model_path=config.model_path,
            host=config.host,
            port=config.port,
            gpu_memory_fraction=config.gpu_memory_fraction,
            max_model_len=config.max_model_len,
            max_total_tokens=max_total_tokens,
            tensor_parallel_size=config.tensor_parallel_size,
            quantization_arg=quantization_arg,
            dtype_arg=dtype_arg,
            extra_args=config.extra_args,
        )

        # Clean up multiple spaces
        return ' '.join(cmd.split())

    def _get_environment(self, config: ModelConfig) -> str:
        """Generate environment variable lines."""
        env_lines = []

        # GPU configuration
        gpu_list = ','.join(map(str, config.gpu_ids))
        env_lines.append(f"Environment=CUDA_VISIBLE_DEVICES={gpu_list}")
        env_lines.append(f"Environment=HIP_VISIBLE_DEVICES={gpu_list}")

        # Common ML environment variables
        env_lines.append("Environment=TOKENIZERS_PARALLELISM=false")
        env_lines.append("Environment=TRANSFORMERS_OFFLINE=0")

        # Custom environment variables
        for key, value in config.environment.items():
            env_lines.append(f"Environment={key}={value}")

        return '\n'.join(env_lines)

    def _get_resource_limits(self, config: ModelConfig) -> str:
        """Generate resource limit lines."""
        res = config.resources
        lines = [
            f"CPUQuota={int(res.cpu_quota * 100)}%",
            f"CPUWeight={res.cpu_weight}",
            f"MemoryMax={res.memory_max}",
            f"MemoryHigh={res.memory_high}",
            f"IOWeight={res.io_weight}",
            f"TasksMax={res.tasks_max}",
        ]
        return '\n'.join(lines)

    def _get_security_settings(self, config: ModelConfig) -> str:
        """Generate security hardening lines."""
        sec = config.security
        lines = []

        if sec.no_new_privileges:
            lines.append("NoNewPrivileges=true")
        if sec.protect_system:
            lines.append(f"ProtectSystem={sec.protect_system}")
        if sec.protect_home:
            lines.append(f"ProtectHome={sec.protect_home}")
        if sec.private_tmp:
            lines.append("PrivateTmp=true")
        if sec.private_devices:
            lines.append("PrivateDevices=true")
        if sec.restrict_realtime:
            lines.append("RestrictRealtime=true")
        if sec.restrict_suid_sgid:
            lines.append("RestrictSUIDSGID=true")
        if sec.protect_kernel_tunables:
            lines.append("ProtectKernelTunables=true")
        if sec.protect_kernel_modules:
            lines.append("ProtectKernelModules=true")
        if sec.protect_control_groups:
            lines.append("ProtectControlGroups=true")
        if sec.memory_deny_write_execute:
            lines.append("MemoryDenyWriteExecute=true")

        return '\n'.join(lines)

    def _get_health_check(self, config: ModelConfig) -> str:
        """Generate health check watchdog configuration."""
        if not config.health_check.enabled:
            return ""

        hc = config.health_check
        # Use systemd watchdog for health monitoring
        return f"""
# Health check via systemd watchdog
WatchdogSec={hc.interval_seconds}
"""

    def generate(self, config: ModelConfig) -> str:
        """Generate complete systemd service file."""
        cmd = self._get_command(config)
        env = self._get_environment(config)
        resources = self._get_resource_limits(config)
        security = self._get_security_settings(config)
        health = self._get_health_check(config)

        service = f"""[Unit]
Description=Cortex Model: {config.name}
Documentation=https://github.com/cortexlinux/cortex
After=network.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={cmd}
{env}

# Resource Limits
{resources}

# Security Hardening
{security}

# Restart Policy
Restart={config.restart_policy}
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst={config.restart_max_retries}
{health}
# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cortex-{config.name}

[Install]
WantedBy=default.target
"""
        return service

    def get_default_health_endpoint(self, backend: str) -> str:
        """Get default health check endpoint for backend."""
        return self.HEALTH_ENDPOINTS.get(backend, "/health")


class HealthChecker:
    """Health check monitor for model services."""

    def __init__(self, manager: 'ModelLifecycleManager'):
        self.manager = manager
        self._monitors: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._failure_counts: Dict[str, int] = {}

    def check_health(self, config: ModelConfig) -> Tuple[bool, str]:
        """Perform a single health check."""
        url = config.get_health_url()
        timeout = config.health_check.timeout_seconds

        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return True, "OK"
                return False, f"HTTP {response.status}"
        except urllib.error.URLError as e:
            return False, f"Connection failed: {e.reason}"
        except Exception as e:
            return False, str(e)

    def start_monitor(self, name: str) -> None:
        """Start health monitoring for a model."""
        if name in self._monitors:
            return

        config = self.manager.db.get_model(name)
        if not config or not config.health_check.enabled:
            return

        stop_event = threading.Event()
        self._stop_events[name] = stop_event
        self._failure_counts[name] = 0

        def monitor_loop():
            hc = config.health_check
            # Wait for startup
            time.sleep(hc.startup_delay_seconds)

            while not stop_event.is_set():
                healthy, msg = self.check_health(config)

                if healthy:
                    if self._failure_counts.get(name, 0) > 0:
                        self.manager.db.log_event(name, EventType.HEALTH_CHECK_PASSED, msg)
                    self._failure_counts[name] = 0
                else:
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
                    self.manager.db.log_event(
                        name, EventType.HEALTH_CHECK_FAILED,
                        f"Failure {self._failure_counts[name]}/{hc.max_failures}: {msg}"
                    )

                    if self._failure_counts[name] >= hc.max_failures:
                        self.manager.db.log_event(name, EventType.AUTO_RESTARTED)
                        self.manager.restart(name, log_event=False)
                        self._failure_counts[name] = 0
                        time.sleep(hc.startup_delay_seconds)

                stop_event.wait(hc.interval_seconds)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self._monitors[name] = thread

    def stop_monitor(self, name: str) -> None:
        """Stop health monitoring for a model."""
        if name in self._stop_events:
            self._stop_events[name].set()
        if name in self._monitors:
            self._monitors[name].join(timeout=5)
            del self._monitors[name]
        self._stop_events.pop(name, None)
        self._failure_counts.pop(name, None)


class ModelLifecycleManager:
    """Main manager for model lifecycle operations."""

    def __init__(self, db_path: Path = None):
        self.db = ModelDatabase(db_path) if db_path else ModelDatabase()
        self.generator = ServiceGenerator()
        self.health_checker = HealthChecker(self)
        CORTEX_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        CORTEX_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _systemctl(self, *args) -> subprocess.CompletedProcess:
        """Run systemctl command."""
        return subprocess.run(
            ["systemctl", "--user"] + list(args),
            capture_output=True,
            text=True
        )

    def _service_name(self, name: str) -> str:
        """Get systemd service name for model."""
        return f"cortex-{name}.service"

    def _service_path(self, name: str) -> Path:
        """Get service file path."""
        return CORTEX_SERVICE_DIR / self._service_name(name)

    def register(self, config: ModelConfig) -> bool:
        """Register a new model service."""
        try:
            # Generate and write service file
            service_content = self.generator.generate(config)
            service_path = self._service_path(config.name)
            service_path.write_text(service_content)

            # Save to database
            self.db.save_model(config)

            # Reload systemd
            self._systemctl("daemon-reload")

            # Log event
            self.db.log_event(config.name, EventType.REGISTERED)

            print(f"Registered model '{config.name}'")
            return True
        except Exception as e:
            self.db.log_event(config.name, EventType.ERROR, str(e))
            print(f"Failed to register '{config.name}': {e}")
            return False

    def unregister(self, name: str) -> bool:
        """Unregister a model service."""
        try:
            # Stop if running
            self.stop(name, log_event=False)

            # Disable if enabled
            self.disable(name, log_event=False)

            # Stop health monitoring
            self.health_checker.stop_monitor(name)

            # Remove service file
            service_path = self._service_path(name)
            if service_path.exists():
                service_path.unlink()

            # Reload systemd
            self._systemctl("daemon-reload")

            # Remove from database
            self.db.delete_model(name)

            # Log event
            self.db.log_event(name, EventType.UNREGISTERED)

            print(f"Unregistered model '{name}'")
            return True
        except Exception as e:
            self.db.log_event(name, EventType.ERROR, str(e))
            print(f"Failed to unregister '{name}': {e}")
            return False

    def start(self, name: str, log_event: bool = True) -> bool:
        """Start a model service."""
        config = self.db.get_model(name)
        if not config:
            print(f"Model '{name}' not found")
            return False

        result = self._systemctl("start", self._service_name(name))
        success = result.returncode == 0

        if success:
            if log_event:
                self.db.log_event(name, EventType.STARTED)
            self.health_checker.start_monitor(name)
            print(f"Started model '{name}'")
        else:
            if log_event:
                self.db.log_event(name, EventType.ERROR, result.stderr)
            print(f"Failed to start '{name}': {result.stderr}")

        return success

    def stop(self, name: str, log_event: bool = True) -> bool:
        """Stop a model service."""
        self.health_checker.stop_monitor(name)

        result = self._systemctl("stop", self._service_name(name))
        success = result.returncode == 0

        if success:
            if log_event:
                self.db.log_event(name, EventType.STOPPED)
            print(f"Stopped model '{name}'")
        else:
            if log_event:
                self.db.log_event(name, EventType.ERROR, result.stderr)
            print(f"Failed to stop '{name}': {result.stderr}")

        return success

    def restart(self, name: str, log_event: bool = True) -> bool:
        """Restart a model service."""
        self.health_checker.stop_monitor(name)

        result = self._systemctl("restart", self._service_name(name))
        success = result.returncode == 0

        if success:
            if log_event:
                self.db.log_event(name, EventType.STARTED, "restart")
            self.health_checker.start_monitor(name)
            print(f"Restarted model '{name}'")
        else:
            if log_event:
                self.db.log_event(name, EventType.ERROR, result.stderr)
            print(f"Failed to restart '{name}': {result.stderr}")

        return success

    def enable(self, name: str, log_event: bool = True) -> bool:
        """Enable a model for auto-start on boot."""
        result = self._systemctl("enable", self._service_name(name))
        success = result.returncode == 0

        if success:
            if log_event:
                self.db.log_event(name, EventType.ENABLED)
            # Update config
            config = self.db.get_model(name)
            if config:
                config.preload_on_boot = True
                self.db.save_model(config)
            print(f"Enabled model '{name}' for auto-start")
        else:
            print(f"Failed to enable '{name}': {result.stderr}")

        return success

    def disable(self, name: str, log_event: bool = True) -> bool:
        """Disable auto-start for a model."""
        result = self._systemctl("disable", self._service_name(name))
        success = result.returncode == 0

        if success:
            if log_event:
                self.db.log_event(name, EventType.DISABLED)
            # Update config
            config = self.db.get_model(name)
            if config:
                config.preload_on_boot = False
                self.db.save_model(config)
            print(f"Disabled auto-start for model '{name}'")
        else:
            print(f"Failed to disable '{name}': {result.stderr}")

        return success

    def get_state(self, name: str) -> ModelState:
        """Get current state of a model service."""
        result = self._systemctl("is-active", self._service_name(name))
        state_str = result.stdout.strip()

        try:
            return ModelState(state_str)
        except ValueError:
            return ModelState.UNKNOWN

    def get_status(self, name: str) -> Dict[str, Any]:
        """Get detailed status of a model service."""
        config = self.db.get_model(name)
        if not config:
            return {"error": f"Model '{name}' not found"}

        state = self.get_state(name)

        # Get additional info from systemctl
        result = self._systemctl("show", self._service_name(name),
                                "--property=MainPID,MemoryCurrent,CPUUsageNSec,ActiveEnterTimestamp")
        props = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                props[key] = value

        # Check if enabled
        enabled_result = self._systemctl("is-enabled", self._service_name(name))
        enabled = enabled_result.stdout.strip() == "enabled"

        return {
            "name": name,
            "state": state.value,
            "enabled": enabled,
            "backend": config.backend,
            "model_path": config.model_path,
            "port": config.port,
            "gpu_ids": config.gpu_ids,
            "pid": props.get("MainPID", "0"),
            "memory": props.get("MemoryCurrent", "0"),
            "cpu_time": props.get("CPUUsageNSec", "0"),
            "started_at": props.get("ActiveEnterTimestamp", ""),
        }

    def status(self, name: str = None) -> None:
        """Print status of one or all models."""
        if name:
            models = [self.db.get_model(name)]
            if not models[0]:
                print(f"Model '{name}' not found")
                return
        else:
            models = self.db.list_models()

        if not models:
            print("No models registered")
            return

        print(f"\n{'NAME':<20} {'STATE':<12} {'ENABLED':<8} {'BACKEND':<10} {'PORT':<6}")
        print("-" * 60)

        for m in models:
            if m:
                state = self.get_state(m.name)
                enabled_result = self._systemctl("is-enabled", self._service_name(m.name))
                enabled = "yes" if enabled_result.stdout.strip() == "enabled" else "no"

                # Color-code state
                state_str = state.value
                if state == ModelState.ACTIVE:
                    state_str = f"\033[32m{state_str}\033[0m"  # Green
                elif state == ModelState.FAILED:
                    state_str = f"\033[31m{state_str}\033[0m"  # Red

                print(f"{m.name:<20} {state_str:<21} {enabled:<8} {m.backend:<10} {m.port:<6}")

    def logs(self, name: str, lines: int = 50, follow: bool = False) -> None:
        """Show logs for a model service."""
        args = ["journalctl", "--user", "-u", self._service_name(name), "-n", str(lines)]
        if follow:
            args.append("-f")

        subprocess.run(args)

    def events(self, name: str = None, limit: int = 20) -> None:
        """Show events for models."""
        events = self.db.get_events(name, limit)

        if not events:
            print("No events found")
            return

        print(f"\n{'TIMESTAMP':<25} {'MODEL':<15} {'EVENT':<20} {'DETAILS'}")
        print("-" * 80)

        for e in events:
            ts = e['timestamp'][:19].replace('T', ' ')
            details = (e['details'] or '')[:30]
            print(f"{ts:<25} {e['model']:<15} {e['event']:<20} {details}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cortex Model Lifecycle Manager - Systemd-based LLM service management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex-model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm --gpus 0,1
  cortex-model start llama-70b
  cortex-model status
  cortex-model enable llama-70b
  cortex-model logs llama-70b -f
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Register command
    reg = subparsers.add_parser("register", help="Register a new model")
    reg.add_argument("name", help="Model name")
    reg.add_argument("--path", required=True, help="Model path or HuggingFace ID")
    reg.add_argument("--backend", default="vllm",
                     choices=["vllm", "llamacpp", "ollama", "tgi"],
                     help="Inference backend")
    reg.add_argument("--port", type=int, default=8000, help="Service port")
    reg.add_argument("--host", default="127.0.0.1", help="Service host")
    reg.add_argument("--gpus", default="0", help="Comma-separated GPU IDs")
    reg.add_argument("--memory", default="32G", help="Memory limit")
    reg.add_argument("--cpu", type=float, default=4.0, help="CPU cores limit")
    reg.add_argument("--max-model-len", type=int, default=4096, help="Max sequence length")
    reg.add_argument("--tensor-parallel", type=int, default=1, help="Tensor parallel size")
    reg.add_argument("--quantization", help="Quantization method (awq, gptq)")
    reg.add_argument("--extra-args", default="", help="Extra backend arguments")
    reg.add_argument("--no-health-check", action="store_true", help="Disable health checks")

    # Start command
    start = subparsers.add_parser("start", help="Start a model")
    start.add_argument("name", help="Model name")

    # Stop command
    stop = subparsers.add_parser("stop", help="Stop a model")
    stop.add_argument("name", help="Model name")

    # Restart command
    restart = subparsers.add_parser("restart", help="Restart a model")
    restart.add_argument("name", help="Model name")

    # Enable command
    enable = subparsers.add_parser("enable", help="Enable auto-start on boot")
    enable.add_argument("name", help="Model name")

    # Disable command
    disable = subparsers.add_parser("disable", help="Disable auto-start")
    disable.add_argument("name", help="Model name")

    # Unregister command
    unreg = subparsers.add_parser("unregister", help="Unregister a model")
    unreg.add_argument("name", help="Model name")

    # Status command
    status = subparsers.add_parser("status", help="Show model status")
    status.add_argument("name", nargs="?", help="Model name (optional)")

    # List command
    subparsers.add_parser("list", help="List all models")

    # Logs command
    logs = subparsers.add_parser("logs", help="Show model logs")
    logs.add_argument("name", help="Model name")
    logs.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")
    logs.add_argument("-f", "--follow", action="store_true", help="Follow log output")

    # Events command
    events = subparsers.add_parser("events", help="Show model events")
    events.add_argument("name", nargs="?", help="Model name (optional)")
    events.add_argument("-n", "--limit", type=int, default=20, help="Number of events")

    # Health command
    health = subparsers.add_parser("health", help="Check model health")
    health.add_argument("name", help="Model name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = ModelLifecycleManager()

    if args.command == "register":
        config = ModelConfig(
            name=args.name,
            model_path=args.path,
            backend=args.backend,
            port=args.port,
            host=args.host,
            gpu_ids=[int(x) for x in args.gpus.split(",")],
            max_model_len=args.max_model_len,
            tensor_parallel_size=args.tensor_parallel,
            quantization=args.quantization,
            extra_args=args.extra_args,
            health_check=HealthCheckConfig(
                enabled=not args.no_health_check,
                endpoint=ServiceGenerator().get_default_health_endpoint(args.backend)
            ),
            resources=ResourceLimits(
                memory_max=args.memory,
                cpu_quota=args.cpu
            )
        )
        manager.register(config)

    elif args.command == "start":
        manager.start(args.name)

    elif args.command == "stop":
        manager.stop(args.name)

    elif args.command == "restart":
        manager.restart(args.name)

    elif args.command == "enable":
        manager.enable(args.name)

    elif args.command == "disable":
        manager.disable(args.name)

    elif args.command == "unregister":
        manager.unregister(args.name)

    elif args.command in ("status", "list"):
        manager.status(getattr(args, 'name', None))

    elif args.command == "logs":
        manager.logs(args.name, args.lines, args.follow)

    elif args.command == "events":
        manager.events(getattr(args, 'name', None), args.limit)

    elif args.command == "health":
        config = manager.db.get_model(args.name)
        if config:
            healthy, msg = manager.health_checker.check_health(config)
            status = "healthy" if healthy else "unhealthy"
            print(f"Model '{args.name}' is {status}: {msg}")
            sys.exit(0 if healthy else 1)
        else:
            print(f"Model '{args.name}' not found")
            sys.exit(1)


if __name__ == "__main__":
    main()
