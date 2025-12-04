#!/usr/bin/env python3
"""
Tests for Model Lifecycle Manager

Run: python -m pytest test_model_lifecycle.py -v
"""

import unittest
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from model_lifecycle import (
    BACKENDS,
    DEFAULT_RESOURCES,
    ModelConfig,
    ModelRegistry,
    ServiceGenerator,
    ServiceController,
    HealthMonitor,
    ModelLifecycleCLI,
)


class TestBackends(unittest.TestCase):
    """Test backend configurations."""

    def test_backends_exist(self):
        self.assertIn("vllm", BACKENDS)
        self.assertIn("llamacpp", BACKENDS)
        self.assertIn("ollama", BACKENDS)
        self.assertIn("tgi", BACKENDS)

    def test_vllm_config(self):
        backend = BACKENDS["vllm"]
        self.assertIn("command", backend)
        self.assertIn("args", backend)
        self.assertIn("health_endpoint", backend)
        self.assertEqual(backend["health_endpoint"], "/health")

    def test_llamacpp_config(self):
        backend = BACKENDS["llamacpp"]
        self.assertEqual(backend["command"], "llama-server")

    def test_ollama_config(self):
        backend = BACKENDS["ollama"]
        self.assertEqual(backend["command"], "ollama")

    def test_tgi_config(self):
        backend = BACKENDS["tgi"]
        self.assertEqual(backend["command"], "text-generation-launcher")

    def test_default_resources(self):
        self.assertIn("vllm", DEFAULT_RESOURCES)
        self.assertIn("cpu_cores", DEFAULT_RESOURCES["vllm"])
        self.assertIn("memory_gb", DEFAULT_RESOURCES["vllm"])


class TestModelConfig(unittest.TestCase):
    """Test model configuration."""

    def test_create_config(self):
        config = ModelConfig(
            name="test-model",
            model_path="meta-llama/Llama-2-7b-hf",
            backend="vllm",
        )
        self.assertEqual(config.name, "test-model")
        self.assertEqual(config.model_path, "meta-llama/Llama-2-7b-hf")
        self.assertEqual(config.backend, "vllm")

    def test_default_values(self):
        config = ModelConfig(name="test", model_path="path")
        self.assertEqual(config.gpus, "0")
        self.assertEqual(config.port, 8000)
        self.assertEqual(config.cpu_cores, 8)
        self.assertEqual(config.memory_gb, 32)
        self.assertFalse(config.enabled)

    def test_to_dict(self):
        config = ModelConfig(name="test", model_path="path")
        data = config.to_dict()
        self.assertEqual(data["name"], "test")
        self.assertEqual(data["model_path"], "path")
        self.assertIn("created_at", data)

    def test_from_dict(self):
        original = ModelConfig(name="test", model_path="path", port=9000)
        data = original.to_dict()
        restored = ModelConfig.from_dict(data)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.port, 9000)

    def test_custom_gpu_config(self):
        config = ModelConfig(
            name="multi-gpu",
            model_path="path",
            gpus="0,1,2,3",
        )
        self.assertEqual(config.gpus, "0,1,2,3")

    def test_llamacpp_layers(self):
        config = ModelConfig(
            name="cpu-model",
            model_path="path",
            backend="llamacpp",
            gpu_layers=35,
        )
        self.assertEqual(config.gpu_layers, 35)


class TestModelRegistry(unittest.TestCase):
    """Test model registry storage."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "models.db")
        self.registry = ModelRegistry(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_register_model(self):
        config = ModelConfig(name="test-model", model_path="path")
        result = self.registry.register(config)
        self.assertTrue(result)

    def test_get_model(self):
        config = ModelConfig(name="test-model", model_path="path", port=9000)
        self.registry.register(config)

        loaded = self.registry.get("test-model")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test-model")
        self.assertEqual(loaded.port, 9000)

    def test_get_nonexistent(self):
        loaded = self.registry.get("nonexistent")
        self.assertIsNone(loaded)

    def test_list_models(self):
        self.registry.register(ModelConfig(name="m1", model_path="p1"))
        self.registry.register(ModelConfig(name="m2", model_path="p2"))
        self.registry.register(ModelConfig(name="m3", model_path="p3"))

        models = self.registry.list()
        self.assertEqual(len(models), 3)
        names = [m.name for m in models]
        self.assertIn("m1", names)
        self.assertIn("m2", names)
        self.assertIn("m3", names)

    def test_delete_model(self):
        self.registry.register(ModelConfig(name="to-delete", model_path="path"))
        self.assertTrue(self.registry.delete("to-delete"))
        self.assertIsNone(self.registry.get("to-delete"))

    def test_update_model(self):
        config = ModelConfig(name="test", model_path="path", port=8000)
        self.registry.register(config)

        config.port = 9000
        self.registry.update(config)

        loaded = self.registry.get("test")
        self.assertEqual(loaded.port, 9000)

    def test_empty_list(self):
        models = self.registry.list()
        self.assertEqual(models, [])


class TestServiceGenerator(unittest.TestCase):
    """Test systemd service generation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.generator = ServiceGenerator(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_generate_vllm_service(self):
        config = ModelConfig(
            name="llama-7b",
            model_path="meta-llama/Llama-2-7b-hf",
            backend="vllm",
            gpus="0,1",
            port=8000,
        )
        content = self.generator.generate(config)

        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("[Install]", content)
        self.assertIn("CUDA_VISIBLE_DEVICES=0,1", content)
        self.assertIn("vllm.entrypoints.openai.api_server", content)
        self.assertIn("meta-llama/Llama-2-7b-hf", content)

    def test_generate_llamacpp_service(self):
        config = ModelConfig(
            name="llama-cpp",
            model_path="/models/llama.gguf",
            backend="llamacpp",
            gpu_layers=35,
        )
        content = self.generator.generate(config)

        self.assertIn("llama-server", content)
        self.assertIn("/models/llama.gguf", content)
        self.assertIn("-ngl", content)

    def test_generate_ollama_service(self):
        config = ModelConfig(
            name="ollama-server",
            model_path="",
            backend="ollama",
            port=11434,
        )
        content = self.generator.generate(config)

        self.assertIn("ollama serve", content)
        self.assertIn("OLLAMA_HOST", content)

    def test_resource_limits(self):
        config = ModelConfig(
            name="resource-test",
            model_path="path",
            cpu_cores=16,
            memory_gb=64,
        )
        content = self.generator.generate(config)

        self.assertIn("CPUQuota=1600%", content)
        self.assertIn("MemoryMax=64G", content)

    def test_security_hardening(self):
        config = ModelConfig(name="secure", model_path="path")
        content = self.generator.generate(config)

        self.assertIn("NoNewPrivileges=true", content)
        self.assertIn("ProtectSystem=strict", content)
        self.assertIn("PrivateTmp=true", content)

    def test_install_service(self):
        config = ModelConfig(name="install-test", model_path="path")
        result = self.generator.install(config)

        self.assertTrue(result)
        service_path = Path(self.temp_dir) / "cortex-model-install-test.service"
        self.assertTrue(service_path.exists())

    def test_uninstall_service(self):
        config = ModelConfig(name="uninstall-test", model_path="path")
        self.generator.install(config)

        result = self.generator.uninstall("uninstall-test")
        self.assertTrue(result)

        service_path = Path(self.temp_dir) / "cortex-model-uninstall-test.service"
        self.assertFalse(service_path.exists())


class TestServiceController(unittest.TestCase):
    """Test systemd service control."""

    def setUp(self):
        self.controller = ServiceController()

    def test_get_service_name(self):
        name = self.controller._get_service_name("my-model")
        self.assertEqual(name, "cortex-model-my-model.service")

    @patch('subprocess.run')
    def test_start_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = self.controller.start("test-model")
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_start_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Failed")
        result = self.controller.start("test-model")
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_stop(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = self.controller.stop("test-model")
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_status(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="active", stderr=""),
            MagicMock(returncode=0, stdout="enabled", stderr=""),
            MagicMock(returncode=0, stdout="ActiveState=active\nMainPID=1234\nMemoryCurrent=1073741824\nCPUUsageNSec=1000000000", stderr=""),
        ]
        status = self.controller.status("test-model")
        self.assertEqual(status["active"], "active")
        self.assertTrue(status["enabled"])


class TestHealthMonitor(unittest.TestCase):
    """Test health monitoring."""

    @patch('urllib.request.urlopen')
    def test_healthy_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = HealthMonitor.check("localhost", 8000, "/health")
        self.assertTrue(result["healthy"])
        self.assertEqual(result["status_code"], 200)

    def test_unhealthy_connection_error(self):
        # This should fail to connect since nothing is listening
        result = HealthMonitor.check("localhost", 59999, "/health", timeout=1)
        self.assertFalse(result["healthy"])
        self.assertIn("error", result)


class TestCLI(unittest.TestCase):
    """Test CLI commands."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "models.db")
        self.service_dir = os.path.join(self.temp_dir, "services")
        os.makedirs(self.service_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_initialization(self):
        cli = ModelLifecycleCLI()
        self.assertIsNotNone(cli.registry)
        self.assertIsNotNone(cli.generator)
        self.assertIsNotNone(cli.controller)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "models.db")
        self.service_dir = os.path.join(self.temp_dir, "services")
        os.makedirs(self.service_dir)

        self.registry = ModelRegistry(self.db_path)
        self.generator = ServiceGenerator(self.service_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_register_and_generate(self):
        # Register model
        config = ModelConfig(
            name="llama-70b",
            model_path="meta-llama/Llama-2-70b-hf",
            backend="vllm",
            gpus="0,1,2,3",
            port=8000,
            cpu_cores=16,
            memory_gb=128,
        )
        self.registry.register(config)

        # Generate service
        self.generator.install(config)

        # Verify registration
        loaded = self.registry.get("llama-70b")
        self.assertEqual(loaded.gpus, "0,1,2,3")

        # Verify service file
        service_path = Path(self.service_dir) / "cortex-model-llama-70b.service"
        self.assertTrue(service_path.exists())
        content = service_path.read_text()
        self.assertIn("CUDA_VISIBLE_DEVICES=0,1,2,3", content)
        self.assertIn("MemoryMax=128G", content)

    def test_multi_model_workflow(self):
        # Register multiple models
        models = [
            ModelConfig(name="llama-7b", model_path="meta-llama/Llama-2-7b-hf", port=8000),
            ModelConfig(name="mistral", model_path="mistralai/Mistral-7B-v0.1", port=8001),
            ModelConfig(name="phi", model_path="microsoft/phi-2", port=8002),
        ]

        for m in models:
            self.registry.register(m)
            self.generator.install(m)

        # List all
        all_models = self.registry.list()
        self.assertEqual(len(all_models), 3)

        # Verify each service file
        for m in models:
            service_path = Path(self.service_dir) / f"cortex-model-{m.name}.service"
            self.assertTrue(service_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
