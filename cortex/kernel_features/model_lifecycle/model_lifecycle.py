#!/usr/bin/env python3
"""
Model Lifecycle Manager - Systemd-Based LLM Service Management

Manage LLM models as first-class system services using systemd.
"systemctl for AI models"

Usage:
    cortex model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm --gpus 0,1
    cortex model start llama-70b
    cortex model status
    cortex model enable llama-70b

Author: Yair Siegel
Bounty: cortexlinux/cortex#220
"""

import os
import sys
import json
import sqlite3
import subprocess
import argparse
import tempfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from string import Template


# =============================================================================
# BACKEND CONFIGURATIONS
# =============================================================================

BACKENDS = {
    "vllm": {
        "description": "vLLM - High-throughput LLM serving",
        "command": "python -m vllm.entrypoints.openai.api_server",
        "args": ["--model", "${model_path}", "--port", "${port}"],
        "health_endpoint": "/health",
        "env": {
            "CUDA_VISIBLE_DEVICES": "${gpus}",
        },
    },
    "llamacpp": {
        "description": "llama.cpp - CPU/GPU inference",
        "command": "llama-server",
        "args": ["-m", "${model_path}", "--port", "${port}", "-ngl", "${gpu_layers}"],
        "health_endpoint": "/health",
        "env": {},
    },
    "ollama": {
        "description": "Ollama - Easy model management",
        "command": "ollama",
        "args": ["serve"],
        "health_endpoint": "/api/tags",
        "env": {
            "OLLAMA_HOST": "0.0.0.0:${port}",
        },
    },
    "tgi": {
        "description": "Text Generation Inference",
        "command": "text-generation-launcher",
        "args": ["--model-id", "${model_path}", "--port", "${port}"],
        "health_endpoint": "/health",
        "env": {
            "CUDA_VISIBLE_DEVICES": "${gpus}",
        },
    },
}

# Default resource limits per backend
DEFAULT_RESOURCES = {
    "vllm": {"cpu_cores": 8, "memory_gb": 32, "gpu_memory_fraction": 0.9},
    "llamacpp": {"cpu_cores": 4, "memory_gb": 16, "gpu_memory_fraction": 0.8},
    "ollama": {"cpu_cores": 4, "memory_gb": 16, "gpu_memory_fraction": 0.8},
    "tgi": {"cpu_cores": 8, "memory_gb": 32, "gpu_memory_fraction": 0.9},
}


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for a registered model."""
    name: str
    model_path: str
    backend: str = "vllm"

    # GPU configuration
    gpus: str = "0"
    gpu_layers: int = 99  # For llama.cpp

    # Network
    port: int = 8000
    host: str = "0.0.0.0"

    # Resources
    cpu_cores: int = 8
    memory_gb: int = 32

    # Health check
    health_endpoint: str = "/health"
    health_interval: int = 30
    health_timeout: int = 10
    health_retries: int = 3

    # Auto-start
    enabled: bool = False

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ModelConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# MODEL REGISTRY (SQLite)
# =============================================================================

class ModelRegistry:
    """SQLite-backed model configuration storage."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.config/cortex/models.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def register(self, config: ModelConfig) -> bool:
        """Register a new model."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO models (name, config, created_at) VALUES (?, ?, ?)",
                    (config.name, json.dumps(config.to_dict()), config.created_at)
                )
                conn.commit()
                return True
            except Exception as e:
                print(f"[ERROR] Failed to register model: {e}")
                return False

    def get(self, name: str) -> Optional[ModelConfig]:
        """Get model configuration."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT config FROM models WHERE name = ?", (name,)
            )
            row = cursor.fetchone()
            if row:
                return ModelConfig.from_dict(json.loads(row[0]))
            return None

    def list(self) -> List[ModelConfig]:
        """List all registered models."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT config FROM models")
            return [ModelConfig.from_dict(json.loads(row[0])) for row in cursor.fetchall()]

    def delete(self, name: str) -> bool:
        """Delete a model."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM models WHERE name = ?", (name,))
            conn.commit()
            return True

    def update(self, config: ModelConfig) -> bool:
        """Update model configuration."""
        return self.register(config)


# =============================================================================
# SYSTEMD SERVICE GENERATOR
# =============================================================================

SYSTEMD_TEMPLATE = """[Unit]
Description=Cortex LLM Model: ${name}
Documentation=https://github.com/cortexlinux/cortex
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${user}
Group=${group}
WorkingDirectory=${working_dir}

# Environment
Environment="CUDA_VISIBLE_DEVICES=${gpus}"
${extra_env}

# Command
ExecStart=${exec_start}

# Health check
ExecStartPost=/bin/sh -c 'for i in 1 2 3 4 5 6 7 8 9 10; do sleep 5; curl -sf http://localhost:${port}${health_endpoint} && exit 0; done; exit 1'

# Restart policy
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Resource limits
CPUQuota=${cpu_quota}%
MemoryMax=${memory_max}G
MemoryHigh=${memory_high}G
TasksMax=1024

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cortex-${name}

[Install]
WantedBy=multi-user.target
"""


class ServiceGenerator:
    """Generate systemd service files for models."""

    def __init__(self, service_dir: str = None):
        if service_dir is None:
            # User services if not root, system services if root
            if os.geteuid() == 0:
                service_dir = "/etc/systemd/system"
            else:
                service_dir = os.path.expanduser("~/.config/systemd/user")
        self.service_dir = Path(service_dir)
        self.service_dir.mkdir(parents=True, exist_ok=True)

    def _get_service_name(self, model_name: str) -> str:
        """Get systemd service name for model."""
        return f"cortex-model-{model_name}.service"

    def _get_service_path(self, model_name: str) -> Path:
        """Get path to service file."""
        return self.service_dir / self._get_service_name(model_name)

    def generate(self, config: ModelConfig) -> str:
        """Generate systemd service file content."""
        backend = BACKENDS.get(config.backend, BACKENDS["vllm"])

        # Build command
        cmd_parts = [backend["command"]]
        for arg in backend["args"]:
            cmd_parts.append(Template(arg).safe_substitute(
                model_path=config.model_path,
                port=config.port,
                gpus=config.gpus,
                gpu_layers=config.gpu_layers,
            ))
        exec_start = " ".join(cmd_parts)

        # Build extra environment
        extra_env_lines = []
        for key, val in backend.get("env", {}).items():
            resolved = Template(val).safe_substitute(
                gpus=config.gpus,
                port=config.port,
            )
            extra_env_lines.append(f'Environment="{key}={resolved}"')

        # Generate service content
        content = Template(SYSTEMD_TEMPLATE).safe_substitute(
            name=config.name,
            user=os.environ.get("USER", "root"),
            group=os.environ.get("USER", "root"),
            working_dir=os.path.expanduser("~"),
            gpus=config.gpus,
            extra_env="\n".join(extra_env_lines),
            exec_start=exec_start,
            port=config.port,
            health_endpoint=config.health_endpoint or backend["health_endpoint"],
            cpu_quota=config.cpu_cores * 100,
            memory_max=config.memory_gb,
            memory_high=int(config.memory_gb * 0.9),
        )

        return content

    def install(self, config: ModelConfig) -> bool:
        """Install systemd service for model."""
        service_path = self._get_service_path(config.name)
        content = self.generate(config)

        try:
            service_path.write_text(content)
            self._reload_daemon()
            return True
        except PermissionError:
            print(f"[ERROR] Permission denied writing to {service_path}")
            print(f"[INFO] Generated service content:\n{content}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to install service: {e}")
            return False

    def uninstall(self, model_name: str) -> bool:
        """Remove systemd service for model."""
        service_path = self._get_service_path(model_name)

        try:
            if service_path.exists():
                service_path.unlink()
                self._reload_daemon()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to uninstall service: {e}")
            return False

    def _reload_daemon(self):
        """Reload systemd daemon."""
        try:
            if os.geteuid() == 0:
                subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True)
            else:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        except:
            pass  # Best effort


# =============================================================================
# SERVICE CONTROLLER
# =============================================================================

class ServiceController:
    """Control systemd services for models."""

    def __init__(self):
        self.user_mode = os.geteuid() != 0

    def _systemctl(self, *args) -> subprocess.CompletedProcess:
        """Run systemctl command."""
        cmd = ["systemctl"]
        if self.user_mode:
            cmd.append("--user")
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def _get_service_name(self, model_name: str) -> str:
        return f"cortex-model-{model_name}.service"

    def start(self, model_name: str) -> bool:
        """Start model service."""
        result = self._systemctl("start", self._get_service_name(model_name))
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def stop(self, model_name: str) -> bool:
        """Stop model service."""
        result = self._systemctl("stop", self._get_service_name(model_name))
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def restart(self, model_name: str) -> bool:
        """Restart model service."""
        result = self._systemctl("restart", self._get_service_name(model_name))
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def enable(self, model_name: str) -> bool:
        """Enable model service for auto-start."""
        result = self._systemctl("enable", self._get_service_name(model_name))
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def disable(self, model_name: str) -> bool:
        """Disable model service auto-start."""
        result = self._systemctl("disable", self._get_service_name(model_name))
        if result.returncode != 0:
            print(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def status(self, model_name: str) -> Dict:
        """Get model service status."""
        service = self._get_service_name(model_name)

        # Get active state
        active_result = self._systemctl("is-active", service)
        active = active_result.stdout.strip()

        # Get enabled state
        enabled_result = self._systemctl("is-enabled", service)
        enabled = enabled_result.stdout.strip()

        # Get detailed status
        status_result = self._systemctl("show", service,
            "--property=ActiveState,SubState,MainPID,MemoryCurrent,CPUUsageNSec")

        props = {}
        for line in status_result.stdout.split('\n'):
            if '=' in line:
                key, val = line.split('=', 1)
                props[key] = val

        return {
            "service": service,
            "active": active,
            "enabled": enabled == "enabled",
            "pid": int(props.get("MainPID", 0)),
            "memory_bytes": int(props.get("MemoryCurrent", 0)),
            "cpu_nsec": int(props.get("CPUUsageNSec", 0)),
        }

    def logs(self, model_name: str, lines: int = 50) -> str:
        """Get model service logs."""
        result = subprocess.run(
            ["journalctl", "-u", self._get_service_name(model_name),
             "-n", str(lines), "--no-pager"],
            capture_output=True, text=True
        )
        return result.stdout


# =============================================================================
# HEALTH MONITOR
# =============================================================================

class HealthMonitor:
    """Monitor model health via HTTP endpoints."""

    @staticmethod
    def check(host: str, port: int, endpoint: str, timeout: int = 5) -> Dict:
        """Check model health."""
        import urllib.request
        import urllib.error

        url = f"http://{host}:{port}{endpoint}"

        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {
                    "healthy": True,
                    "status_code": resp.status,
                    "url": url,
                }
        except urllib.error.HTTPError as e:
            return {
                "healthy": False,
                "status_code": e.code,
                "error": str(e),
                "url": url,
            }
        except Exception as e:
            return {
                "healthy": False,
                "status_code": None,
                "error": str(e),
                "url": url,
            }


# =============================================================================
# CLI
# =============================================================================

class ModelLifecycleCLI:
    """CLI for cortex model command."""

    def __init__(self):
        self.registry = ModelRegistry()
        self.generator = ServiceGenerator()
        self.controller = ServiceController()
        self.health = HealthMonitor()

    def register(self, args):
        """Register a new model."""
        # Get default resources for backend
        defaults = DEFAULT_RESOURCES.get(args.backend, DEFAULT_RESOURCES["vllm"])

        config = ModelConfig(
            name=args.name,
            model_path=args.path,
            backend=args.backend,
            gpus=args.gpus or "0",
            port=args.port or 8000,
            cpu_cores=args.cpus or defaults["cpu_cores"],
            memory_gb=args.memory or defaults["memory_gb"],
        )

        # Register in database
        if not self.registry.register(config):
            return 1

        # Generate and install systemd service
        if self.generator.install(config):
            print(f"Registered model '{args.name}'")
            print(f"  Backend: {args.backend}")
            print(f"  Path: {args.path}")
            print(f"  Port: {config.port}")
            print(f"  GPUs: {config.gpus}")
            print(f"\nStart with: cortex model start {args.name}")
        else:
            print(f"Registered model '{args.name}' (service file generation failed)")

        return 0

    def start(self, args):
        """Start a model."""
        config = self.registry.get(args.name)
        if not config:
            print(f"Model '{args.name}' not found")
            return 1

        if self.controller.start(args.name):
            print(f"Started model '{args.name}'")
            print(f"  Endpoint: http://localhost:{config.port}")
            return 0
        return 1

    def stop(self, args):
        """Stop a model."""
        if self.controller.stop(args.name):
            print(f"Stopped model '{args.name}'")
            return 0
        return 1

    def restart(self, args):
        """Restart a model."""
        if self.controller.restart(args.name):
            print(f"Restarted model '{args.name}'")
            return 0
        return 1

    def enable(self, args):
        """Enable model auto-start."""
        config = self.registry.get(args.name)
        if not config:
            print(f"Model '{args.name}' not found")
            return 1

        if self.controller.enable(args.name):
            config.enabled = True
            self.registry.update(config)
            print(f"Enabled auto-start for '{args.name}'")
            return 0
        return 1

    def disable(self, args):
        """Disable model auto-start."""
        config = self.registry.get(args.name)
        if not config:
            print(f"Model '{args.name}' not found")
            return 1

        if self.controller.disable(args.name):
            config.enabled = False
            self.registry.update(config)
            print(f"Disabled auto-start for '{args.name}'")
            return 0
        return 1

    def status(self, args):
        """Show model status."""
        if args.name:
            # Single model status
            config = self.registry.get(args.name)
            if not config:
                print(f"Model '{args.name}' not found")
                return 1

            svc_status = self.controller.status(args.name)
            health = self.health.check("localhost", config.port, config.health_endpoint)

            print(f"Model: {args.name}")
            print(f"  Backend: {config.backend}")
            print(f"  Path: {config.model_path}")
            print(f"  Status: {svc_status['active']}")
            print(f"  Enabled: {svc_status['enabled']}")
            print(f"  PID: {svc_status['pid'] or 'N/A'}")
            print(f"  Memory: {svc_status['memory_bytes'] / (1024**3):.2f} GB")
            print(f"  Health: {'healthy' if health['healthy'] else 'unhealthy'}")
            print(f"  Endpoint: http://localhost:{config.port}")
        else:
            # All models status
            models = self.registry.list()
            if not models:
                print("No models registered")
                return 0

            print("Registered models:")
            for config in models:
                svc_status = self.controller.status(config.name)
                status_icon = "●" if svc_status['active'] == 'active' else "○"
                enabled_mark = " [enabled]" if svc_status['enabled'] else ""
                print(f"  {status_icon} {config.name} ({config.backend}) - :{config.port}{enabled_mark}")

        return 0

    def logs(self, args):
        """Show model logs."""
        output = self.controller.logs(args.name, args.lines)
        print(output)
        return 0

    def unregister(self, args):
        """Unregister a model."""
        config = self.registry.get(args.name)
        if not config:
            print(f"Model '{args.name}' not found")
            return 1

        # Stop if running
        self.controller.stop(args.name)

        # Remove service file
        self.generator.uninstall(args.name)

        # Remove from registry
        self.registry.delete(args.name)

        print(f"Unregistered model '{args.name}'")
        return 0

    def backends(self, args):
        """List available backends."""
        print("Available backends:")
        for name, info in BACKENDS.items():
            defaults = DEFAULT_RESOURCES.get(name, {})
            print(f"\n  {name}:")
            print(f"    Description: {info['description']}")
            print(f"    Command: {info['command']}")
            print(f"    Default CPU: {defaults.get('cpu_cores', 'N/A')} cores")
            print(f"    Default Memory: {defaults.get('memory_gb', 'N/A')} GB")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Model Lifecycle Manager",
        prog="cortex model"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # register
    reg_parser = subparsers.add_parser("register", help="Register a new model")
    reg_parser.add_argument("name", help="Model name")
    reg_parser.add_argument("--path", "-p", required=True, help="Model path or HuggingFace ID")
    reg_parser.add_argument("--backend", "-b", default="vllm",
                           choices=list(BACKENDS.keys()), help="Backend to use")
    reg_parser.add_argument("--gpus", "-g", help="GPU devices (e.g., '0,1')")
    reg_parser.add_argument("--port", type=int, help="Port to serve on")
    reg_parser.add_argument("--cpus", type=int, help="CPU cores")
    reg_parser.add_argument("--memory", type=int, help="Memory in GB")

    # start
    start_parser = subparsers.add_parser("start", help="Start a model")
    start_parser.add_argument("name", help="Model name")

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop a model")
    stop_parser.add_argument("name", help="Model name")

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart a model")
    restart_parser.add_argument("name", help="Model name")

    # enable
    enable_parser = subparsers.add_parser("enable", help="Enable auto-start")
    enable_parser.add_argument("name", help="Model name")

    # disable
    disable_parser = subparsers.add_parser("disable", help="Disable auto-start")
    disable_parser.add_argument("name", help="Model name")

    # status
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("name", nargs="?", help="Model name (optional)")

    # logs
    logs_parser = subparsers.add_parser("logs", help="Show logs")
    logs_parser.add_argument("name", help="Model name")
    logs_parser.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")

    # unregister
    unreg_parser = subparsers.add_parser("unregister", help="Unregister a model")
    unreg_parser.add_argument("name", help="Model name")

    # backends
    subparsers.add_parser("backends", help="List available backends")

    args = parser.parse_args()
    cli = ModelLifecycleCLI()

    commands = {
        "register": cli.register,
        "start": cli.start,
        "stop": cli.stop,
        "restart": cli.restart,
        "enable": cli.enable,
        "disable": cli.disable,
        "status": cli.status,
        "logs": cli.logs,
        "unregister": cli.unregister,
        "backends": cli.backends,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
