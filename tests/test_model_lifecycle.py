#!/usr/bin/env python3
"""
Unit tests for Cortex Model Lifecycle Manager

Tests cover:
- Configuration dataclasses (ModelConfig, HealthCheckConfig, ResourceLimits, SecurityConfig)
- Database operations (save, get, list, delete, events)
- Service generation (all backends, security, resources)
- Lifecycle operations (register, start, stop, enable, disable)
- Health checking
- CLI parsing
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.kernel_features.model_lifecycle import (
    ModelConfig,
    HealthCheckConfig,
    ResourceLimits,
    SecurityConfig,
    ModelDatabase,
    ServiceGenerator,
    ModelLifecycleManager,
    HealthChecker,
    ModelState,
    EventType,
)


class TestHealthCheckConfig(unittest.TestCase):
    """Test HealthCheckConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = HealthCheckConfig()
        self.assertTrue(config.enabled)
        self.assertEqual(config.endpoint, "/health")
        self.assertEqual(config.interval_seconds, 30)
        self.assertEqual(config.timeout_seconds, 10)
        self.assertEqual(config.max_failures, 3)
        self.assertEqual(config.startup_delay_seconds, 60)

    def test_custom_values(self):
        """Test custom configuration values."""
        config = HealthCheckConfig(
            enabled=False,
            endpoint="/api/health",
            interval_seconds=60,
            timeout_seconds=5,
            max_failures=5,
            startup_delay_seconds=120
        )
        self.assertFalse(config.enabled)
        self.assertEqual(config.endpoint, "/api/health")
        self.assertEqual(config.interval_seconds, 60)

    def test_to_dict(self):
        """Test dictionary serialization."""
        config = HealthCheckConfig(interval_seconds=45)
        d = config.to_dict()
        self.assertEqual(d["interval_seconds"], 45)
        self.assertIn("enabled", d)

    def test_from_dict(self):
        """Test dictionary deserialization."""
        data = {"enabled": False, "endpoint": "/status", "timeout_seconds": 15}
        config = HealthCheckConfig.from_dict(data)
        self.assertFalse(config.enabled)
        self.assertEqual(config.endpoint, "/status")
        self.assertEqual(config.timeout_seconds, 15)
        # Defaults for missing fields
        self.assertEqual(config.interval_seconds, 30)


class TestResourceLimits(unittest.TestCase):
    """Test ResourceLimits dataclass."""

    def test_default_values(self):
        """Test default resource limits."""
        limits = ResourceLimits()
        self.assertEqual(limits.memory_max, "32G")
        self.assertEqual(limits.memory_high, "28G")
        self.assertEqual(limits.cpu_quota, 4.0)
        self.assertEqual(limits.cpu_weight, 100)
        self.assertEqual(limits.io_weight, 100)
        self.assertEqual(limits.tasks_max, 512)

    def test_custom_values(self):
        """Test custom resource limits."""
        limits = ResourceLimits(
            memory_max="64G",
            memory_high="56G",
            cpu_quota=8.0,
            cpu_weight=200,
            io_weight=500,
            tasks_max=1024
        )
        self.assertEqual(limits.memory_max, "64G")
        self.assertEqual(limits.cpu_quota, 8.0)
        self.assertEqual(limits.tasks_max, 1024)

    def test_to_dict(self):
        """Test dictionary serialization."""
        limits = ResourceLimits(memory_max="16G")
        d = limits.to_dict()
        self.assertEqual(d["memory_max"], "16G")

    def test_from_dict(self):
        """Test dictionary deserialization."""
        data = {"memory_max": "128G", "cpu_quota": 16.0}
        limits = ResourceLimits.from_dict(data)
        self.assertEqual(limits.memory_max, "128G")
        self.assertEqual(limits.cpu_quota, 16.0)


class TestSecurityConfig(unittest.TestCase):
    """Test SecurityConfig dataclass."""

    def test_default_values(self):
        """Test default security settings."""
        config = SecurityConfig()
        self.assertTrue(config.no_new_privileges)
        self.assertEqual(config.protect_system, "strict")
        self.assertEqual(config.protect_home, "read-only")
        self.assertTrue(config.private_tmp)
        self.assertFalse(config.private_devices)  # False for GPU access
        self.assertTrue(config.restrict_realtime)

    def test_custom_values(self):
        """Test custom security settings."""
        config = SecurityConfig(
            no_new_privileges=False,
            protect_system="full",
            private_devices=True
        )
        self.assertFalse(config.no_new_privileges)
        self.assertEqual(config.protect_system, "full")
        self.assertTrue(config.private_devices)

    def test_to_dict(self):
        """Test dictionary serialization."""
        config = SecurityConfig(protect_system="true")
        d = config.to_dict()
        self.assertEqual(d["protect_system"], "true")

    def test_from_dict(self):
        """Test dictionary deserialization."""
        data = {"no_new_privileges": False, "protect_home": "tmpfs"}
        config = SecurityConfig.from_dict(data)
        self.assertFalse(config.no_new_privileges)
        self.assertEqual(config.protect_home, "tmpfs")


class TestModelConfig(unittest.TestCase):
    """Test ModelConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal configuration."""
        config = ModelConfig(name="test-model", model_path="/path/to/model")
        self.assertEqual(config.name, "test-model")
        self.assertEqual(config.model_path, "/path/to/model")
        self.assertEqual(config.backend, "vllm")
        self.assertEqual(config.port, 8000)

    def test_full_config(self):
        """Test full configuration with all options."""
        config = ModelConfig(
            name="llama-70b",
            model_path="meta-llama/Llama-2-70b-hf",
            backend="tgi",
            port=8080,
            host="0.0.0.0",
            gpu_memory_fraction=0.85,
            max_model_len=8192,
            gpu_ids=[0, 1, 2, 3],
            tensor_parallel_size=4,
            quantization="awq",
            dtype="float16",
            extra_args="--trust-remote-code",
            restart_policy="always",
            restart_max_retries=10,
            preload_on_boot=True,
            health_check=HealthCheckConfig(enabled=True, interval_seconds=60),
            resources=ResourceLimits(memory_max="128G"),
            security=SecurityConfig(protect_system="full"),
            environment={"HF_TOKEN": "xxx"}
        )
        self.assertEqual(config.name, "llama-70b")
        self.assertEqual(config.backend, "tgi")
        self.assertEqual(config.gpu_ids, [0, 1, 2, 3])
        self.assertEqual(config.tensor_parallel_size, 4)
        self.assertTrue(config.preload_on_boot)
        self.assertEqual(config.health_check.interval_seconds, 60)
        self.assertEqual(config.resources.memory_max, "128G")

    def test_to_dict(self):
        """Test dictionary serialization."""
        config = ModelConfig(name="test", model_path="/path")
        d = config.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertIn("health_check", d)
        self.assertIn("resources", d)
        self.assertIn("security", d)

    def test_from_dict(self):
        """Test dictionary deserialization."""
        data = {
            "name": "from-dict",
            "model_path": "/model",
            "backend": "llamacpp",
            "port": 9000,
            "health_check": {"enabled": False, "interval_seconds": 120},
            "resources": {"memory_max": "64G"},
            "security": {"no_new_privileges": False}
        }
        config = ModelConfig.from_dict(data)
        self.assertEqual(config.name, "from-dict")
        self.assertEqual(config.backend, "llamacpp")
        self.assertEqual(config.port, 9000)
        self.assertFalse(config.health_check.enabled)
        self.assertEqual(config.health_check.interval_seconds, 120)
        self.assertEqual(config.resources.memory_max, "64G")
        self.assertFalse(config.security.no_new_privileges)

    def test_get_health_url(self):
        """Test health URL generation."""
        config = ModelConfig(
            name="test",
            model_path="/path",
            host="localhost",
            port=8080,
            health_check=HealthCheckConfig(endpoint="/api/health")
        )
        self.assertEqual(config.get_health_url(), "http://localhost:8080/api/health")

    def test_get_health_url_no_slash(self):
        """Test health URL with endpoint without leading slash."""
        config = ModelConfig(
            name="test",
            model_path="/path",
            health_check=HealthCheckConfig(endpoint="health")
        )
        self.assertEqual(config.get_health_url(), "http://127.0.0.1:8000/health")


class TestModelDatabase(unittest.TestCase):
    """Test ModelDatabase class."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.db = ModelDatabase(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get_model(self):
        """Test saving and retrieving a model."""
        config = ModelConfig(name="test-model", model_path="/path")
        self.db.save_model(config)

        retrieved = self.db.get_model("test-model")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test-model")
        self.assertEqual(retrieved.model_path, "/path")

    def test_get_nonexistent_model(self):
        """Test getting a model that doesn't exist."""
        retrieved = self.db.get_model("nonexistent")
        self.assertIsNone(retrieved)

    def test_list_models(self):
        """Test listing all models."""
        config1 = ModelConfig(name="model-a", model_path="/a")
        config2 = ModelConfig(name="model-b", model_path="/b")
        config3 = ModelConfig(name="model-c", model_path="/c")

        self.db.save_model(config1)
        self.db.save_model(config2)
        self.db.save_model(config3)

        models = self.db.list_models()
        self.assertEqual(len(models), 3)
        names = [m.name for m in models]
        self.assertIn("model-a", names)
        self.assertIn("model-b", names)
        self.assertIn("model-c", names)

    def test_list_models_empty(self):
        """Test listing models when none exist."""
        models = self.db.list_models()
        self.assertEqual(len(models), 0)

    def test_delete_model(self):
        """Test deleting a model."""
        config = ModelConfig(name="to-delete", model_path="/path")
        self.db.save_model(config)

        result = self.db.delete_model("to-delete")
        self.assertTrue(result)

        retrieved = self.db.get_model("to-delete")
        self.assertIsNone(retrieved)

    def test_delete_nonexistent_model(self):
        """Test deleting a model that doesn't exist."""
        result = self.db.delete_model("nonexistent")
        self.assertFalse(result)

    def test_update_model(self):
        """Test updating an existing model."""
        config = ModelConfig(name="test", model_path="/old")
        self.db.save_model(config)

        config.model_path = "/new"
        config.port = 9000
        self.db.save_model(config)

        retrieved = self.db.get_model("test")
        self.assertEqual(retrieved.model_path, "/new")
        self.assertEqual(retrieved.port, 9000)

    def test_log_event(self):
        """Test logging an event."""
        self.db.log_event("test-model", EventType.REGISTERED)
        self.db.log_event("test-model", EventType.STARTED, "details here")

        events = self.db.get_events("test-model")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "started")  # Most recent first
        self.assertEqual(events[0]["details"], "details here")

    def test_get_events_all(self):
        """Test getting all events."""
        self.db.log_event("model-a", EventType.REGISTERED)
        self.db.log_event("model-b", EventType.STARTED)
        self.db.log_event("model-a", EventType.STOPPED)

        events = self.db.get_events()
        self.assertEqual(len(events), 3)

    def test_get_events_limit(self):
        """Test event limit."""
        for i in range(10):
            self.db.log_event("test", EventType.STARTED)

        events = self.db.get_events("test", limit=5)
        self.assertEqual(len(events), 5)


class TestServiceGenerator(unittest.TestCase):
    """Test ServiceGenerator class."""

    def setUp(self):
        """Create generator."""
        self.generator = ServiceGenerator()

    def test_generate_vllm_service(self):
        """Test generating vLLM service file."""
        config = ModelConfig(
            name="llama",
            model_path="meta-llama/Llama-2-7b-hf",
            backend="vllm",
            port=8000,
            gpu_ids=[0],
            max_model_len=4096
        )
        service = self.generator.generate(config)

        self.assertIn("Description=Cortex Model: llama", service)
        self.assertIn("vllm.entrypoints.openai.api_server", service)
        self.assertIn("--model meta-llama/Llama-2-7b-hf", service)
        self.assertIn("--port 8000", service)
        self.assertIn("CUDA_VISIBLE_DEVICES=0", service)
        self.assertIn("NoNewPrivileges=true", service)

    def test_generate_llamacpp_service(self):
        """Test generating llama.cpp service file."""
        config = ModelConfig(
            name="gguf-model",
            model_path="/models/model.gguf",
            backend="llamacpp",
            port=8080
        )
        service = self.generator.generate(config)

        self.assertIn("llama-server", service)
        self.assertIn("-m /models/model.gguf", service)
        self.assertIn("--port 8080", service)

    def test_generate_tgi_service(self):
        """Test generating TGI service file."""
        config = ModelConfig(
            name="tgi-model",
            model_path="bigscience/bloom-560m",
            backend="tgi",
            port=8000,
            gpu_ids=[0, 1],
            tensor_parallel_size=2
        )
        service = self.generator.generate(config)

        self.assertIn("text-generation-launcher", service)
        self.assertIn("--model-id bigscience/bloom-560m", service)
        self.assertIn("--num-shard 2", service)
        self.assertIn("CUDA_VISIBLE_DEVICES=0,1", service)

    def test_generate_ollama_service(self):
        """Test generating Ollama service file."""
        config = ModelConfig(
            name="ollama",
            model_path="llama2",
            backend="ollama"
        )
        service = self.generator.generate(config)

        self.assertIn("ollama serve", service)

    def test_generate_with_quantization(self):
        """Test service with quantization."""
        config = ModelConfig(
            name="quant-model",
            model_path="/model",
            backend="vllm",
            quantization="awq"
        )
        service = self.generator.generate(config)

        self.assertIn("--quantization awq", service)

    def test_generate_with_resources(self):
        """Test service with custom resources."""
        config = ModelConfig(
            name="resource-model",
            model_path="/model",
            resources=ResourceLimits(
                memory_max="64G",
                cpu_quota=8.0,
                tasks_max=1024
            )
        )
        service = self.generator.generate(config)

        self.assertIn("MemoryMax=64G", service)
        self.assertIn("CPUQuota=800%", service)
        self.assertIn("TasksMax=1024", service)

    def test_generate_with_security(self):
        """Test service with security settings."""
        config = ModelConfig(
            name="secure-model",
            model_path="/model",
            security=SecurityConfig(
                protect_system="strict",
                protect_home="read-only",
                restrict_realtime=True
            )
        )
        service = self.generator.generate(config)

        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ProtectHome=read-only", service)
        self.assertIn("RestrictRealtime=true", service)

    def test_generate_restart_policy(self):
        """Test restart policy in service."""
        config = ModelConfig(
            name="restart-model",
            model_path="/model",
            restart_policy="always",
            restart_max_retries=10
        )
        service = self.generator.generate(config)

        self.assertIn("Restart=always", service)
        self.assertIn("StartLimitBurst=10", service)

    def test_get_default_health_endpoint(self):
        """Test default health endpoints."""
        self.assertEqual(self.generator.get_default_health_endpoint("vllm"), "/health")
        self.assertEqual(self.generator.get_default_health_endpoint("tgi"), "/health")
        self.assertEqual(self.generator.get_default_health_endpoint("ollama"), "/api/tags")
        self.assertEqual(self.generator.get_default_health_endpoint("unknown"), "/health")


class TestModelLifecycleManager(unittest.TestCase):
    """Test ModelLifecycleManager class."""

    def setUp(self):
        """Create manager with temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.manager = ModelLifecycleManager(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_service_name(self):
        """Test service name generation."""
        self.assertEqual(self.manager._service_name("my-model"), "cortex-my-model.service")

    @patch('subprocess.run')
    def test_register(self, mock_run):
        """Test model registration."""
        mock_run.return_value = MagicMock(returncode=0)

        config = ModelConfig(name="test-model", model_path="/path")
        result = self.manager.register(config)

        self.assertTrue(result)
        self.assertIsNotNone(self.manager.db.get_model("test-model"))
        mock_run.assert_called()  # daemon-reload

    @patch('subprocess.run')
    def test_start(self, mock_run):
        """Test starting a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path")
        self.manager.db.save_model(config)

        result = self.manager.start("test-model")
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_start_nonexistent(self, mock_run):
        """Test starting a model that doesn't exist."""
        result = self.manager.start("nonexistent")
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_stop(self, mock_run):
        """Test stopping a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path")
        self.manager.db.save_model(config)

        result = self.manager.stop("test-model")
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_restart(self, mock_run):
        """Test restarting a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path")
        self.manager.db.save_model(config)

        result = self.manager.restart("test-model")
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_enable(self, mock_run):
        """Test enabling a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path", preload_on_boot=False)
        self.manager.db.save_model(config)

        result = self.manager.enable("test-model")
        self.assertTrue(result)

        # Check config updated
        updated = self.manager.db.get_model("test-model")
        self.assertTrue(updated.preload_on_boot)

    @patch('subprocess.run')
    def test_disable(self, mock_run):
        """Test disabling a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path", preload_on_boot=True)
        self.manager.db.save_model(config)

        result = self.manager.disable("test-model")
        self.assertTrue(result)

        updated = self.manager.db.get_model("test-model")
        self.assertFalse(updated.preload_on_boot)

    @patch('subprocess.run')
    def test_unregister(self, mock_run):
        """Test unregistering a model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = ModelConfig(name="test-model", model_path="/path")
        self.manager.register(config)

        result = self.manager.unregister("test-model")
        self.assertTrue(result)
        self.assertIsNone(self.manager.db.get_model("test-model"))

    @patch('subprocess.run')
    def test_get_state(self, mock_run):
        """Test getting model state."""
        mock_run.return_value = MagicMock(returncode=0, stdout="active\n", stderr="")

        state = self.manager.get_state("test-model")
        self.assertEqual(state, ModelState.ACTIVE)

    @patch('subprocess.run')
    def test_get_state_inactive(self, mock_run):
        """Test getting inactive state."""
        mock_run.return_value = MagicMock(returncode=3, stdout="inactive\n", stderr="")

        state = self.manager.get_state("test-model")
        self.assertEqual(state, ModelState.INACTIVE)

    @patch('subprocess.run')
    def test_get_state_failed(self, mock_run):
        """Test getting failed state."""
        mock_run.return_value = MagicMock(returncode=3, stdout="failed\n", stderr="")

        state = self.manager.get_state("test-model")
        self.assertEqual(state, ModelState.FAILED)

    @patch('subprocess.run')
    def test_get_status(self, mock_run):
        """Test getting detailed status."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="active\n", stderr=""),
            MagicMock(returncode=0, stdout="MainPID=12345\nMemoryCurrent=1000000\n", stderr=""),
            MagicMock(returncode=0, stdout="enabled\n", stderr=""),
        ]

        config = ModelConfig(name="test-model", model_path="/path")
        self.manager.db.save_model(config)

        status = self.manager.get_status("test-model")
        self.assertEqual(status["name"], "test-model")
        self.assertEqual(status["state"], "active")
        self.assertTrue(status["enabled"])

    def test_get_status_nonexistent(self):
        """Test getting status of nonexistent model."""
        status = self.manager.get_status("nonexistent")
        self.assertIn("error", status)


class TestHealthChecker(unittest.TestCase):
    """Test HealthChecker class."""

    def setUp(self):
        """Create health checker with mock manager."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.manager = ModelLifecycleManager(self.db_path)
        self.checker = self.manager.health_checker

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('urllib.request.urlopen')
    def test_check_health_success(self, mock_urlopen):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = ModelConfig(name="test", model_path="/path")
        healthy, msg = self.checker.check_health(config)

        self.assertTrue(healthy)
        self.assertEqual(msg, "OK")

    @patch('urllib.request.urlopen')
    def test_check_health_failure_status(self, mock_urlopen):
        """Test health check with bad status code."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = ModelConfig(name="test", model_path="/path")
        healthy, msg = self.checker.check_health(config)

        self.assertFalse(healthy)
        self.assertIn("500", msg)

    @patch('urllib.request.urlopen')
    def test_check_health_connection_error(self, mock_urlopen):
        """Test health check with connection error."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        config = ModelConfig(name="test", model_path="/path")
        healthy, msg = self.checker.check_health(config)

        self.assertFalse(healthy)
        self.assertIn("Connection failed", msg)


class TestModelState(unittest.TestCase):
    """Test ModelState enum."""

    def test_state_values(self):
        """Test all state values."""
        self.assertEqual(ModelState.UNKNOWN.value, "unknown")
        self.assertEqual(ModelState.INACTIVE.value, "inactive")
        self.assertEqual(ModelState.ACTIVATING.value, "activating")
        self.assertEqual(ModelState.ACTIVE.value, "active")
        self.assertEqual(ModelState.DEACTIVATING.value, "deactivating")
        self.assertEqual(ModelState.FAILED.value, "failed")
        self.assertEqual(ModelState.RELOADING.value, "reloading")


class TestEventType(unittest.TestCase):
    """Test EventType enum."""

    def test_event_values(self):
        """Test all event type values."""
        self.assertEqual(EventType.REGISTERED.value, "registered")
        self.assertEqual(EventType.STARTED.value, "started")
        self.assertEqual(EventType.STOPPED.value, "stopped")
        self.assertEqual(EventType.ENABLED.value, "enabled")
        self.assertEqual(EventType.DISABLED.value, "disabled")
        self.assertEqual(EventType.UNREGISTERED.value, "unregistered")
        self.assertEqual(EventType.HEALTH_CHECK_FAILED.value, "health_check_failed")
        self.assertEqual(EventType.HEALTH_CHECK_PASSED.value, "health_check_passed")
        self.assertEqual(EventType.AUTO_RESTARTED.value, "auto_restarted")
        self.assertEqual(EventType.CONFIG_UPDATED.value, "config_updated")
        self.assertEqual(EventType.ERROR.value, "error")


class TestConfigSerialization(unittest.TestCase):
    """Test full configuration serialization round-trip."""

    def test_full_roundtrip(self):
        """Test serializing and deserializing full config."""
        original = ModelConfig(
            name="roundtrip-test",
            model_path="/models/test",
            backend="tgi",
            port=9000,
            host="0.0.0.0",
            gpu_memory_fraction=0.8,
            max_model_len=8192,
            gpu_ids=[0, 1],
            tensor_parallel_size=2,
            quantization="gptq",
            dtype="float16",
            extra_args="--trust-remote-code",
            restart_policy="always",
            restart_max_retries=10,
            preload_on_boot=True,
            health_check=HealthCheckConfig(
                enabled=True,
                endpoint="/api/health",
                interval_seconds=60,
                timeout_seconds=15,
                max_failures=5,
                startup_delay_seconds=120
            ),
            resources=ResourceLimits(
                memory_max="128G",
                memory_high="120G",
                cpu_quota=16.0,
                cpu_weight=200,
                io_weight=500,
                tasks_max=2048
            ),
            security=SecurityConfig(
                no_new_privileges=True,
                protect_system="full",
                protect_home="read-only",
                private_tmp=True,
                private_devices=False,
                restrict_realtime=True
            ),
            environment={"HF_TOKEN": "test", "CUSTOM_VAR": "value"}
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize from dict
        restored = ModelConfig.from_dict(data)

        # Verify all fields match
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.model_path, original.model_path)
        self.assertEqual(restored.backend, original.backend)
        self.assertEqual(restored.port, original.port)
        self.assertEqual(restored.gpu_ids, original.gpu_ids)
        self.assertEqual(restored.tensor_parallel_size, original.tensor_parallel_size)
        self.assertEqual(restored.quantization, original.quantization)
        self.assertEqual(restored.preload_on_boot, original.preload_on_boot)

        # Nested configs
        self.assertEqual(restored.health_check.interval_seconds, original.health_check.interval_seconds)
        self.assertEqual(restored.resources.memory_max, original.resources.memory_max)
        self.assertEqual(restored.security.protect_system, original.security.protect_system)
        self.assertEqual(restored.environment, original.environment)

    def test_json_roundtrip(self):
        """Test JSON serialization round-trip."""
        original = ModelConfig(
            name="json-test",
            model_path="/path",
            health_check=HealthCheckConfig(interval_seconds=45)
        )

        # To JSON and back
        json_str = json.dumps(original.to_dict())
        data = json.loads(json_str)
        restored = ModelConfig.from_dict(data)

        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.health_check.interval_seconds, 45)


class TestDatabasePersistence(unittest.TestCase):
    """Test database persistence across instances."""

    def test_persistence(self):
        """Test that data persists across database instances."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "persist.db"

        try:
            # First instance
            db1 = ModelDatabase(db_path)
            config = ModelConfig(name="persist-test", model_path="/path")
            db1.save_model(config)
            db1.log_event("persist-test", EventType.REGISTERED)

            # Second instance (simulates restart)
            db2 = ModelDatabase(db_path)
            retrieved = db2.get_model("persist-test")
            events = db2.get_events("persist-test")

            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.name, "persist-test")
            self.assertEqual(len(events), 1)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_special_characters_in_name(self):
        """Test model names with special characters."""
        db = ModelDatabase(self.db_path)
        config = ModelConfig(name="model-with_special.chars", model_path="/path")
        db.save_model(config)
        retrieved = db.get_model("model-with_special.chars")
        self.assertIsNotNone(retrieved)

    def test_empty_gpu_ids(self):
        """Test config with empty GPU IDs."""
        config = ModelConfig(name="cpu-only", model_path="/path", gpu_ids=[])
        self.assertEqual(config.gpu_ids, [])

    def test_large_max_model_len(self):
        """Test config with large max_model_len."""
        config = ModelConfig(name="large", model_path="/path", max_model_len=131072)
        self.assertEqual(config.max_model_len, 131072)

    def test_many_gpus(self):
        """Test config with many GPUs."""
        config = ModelConfig(
            name="multi-gpu",
            model_path="/path",
            gpu_ids=[0, 1, 2, 3, 4, 5, 6, 7]
        )
        self.assertEqual(len(config.gpu_ids), 8)

        generator = ServiceGenerator()
        service = generator.generate(config)
        self.assertIn("CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7", service)


if __name__ == "__main__":
    unittest.main(verbosity=2)
