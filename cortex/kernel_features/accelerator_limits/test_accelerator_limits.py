#!/usr/bin/env python3
"""
Tests for Accelerator-Aware Resource Limits

Run: python -m pytest test_accelerator_limits.py -v
"""

import unittest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from accelerator_limits import (
    PRESETS,
    ResourceProfile,
    CgroupsController,
    GPUManager,
    ProfileStore,
    AcceleratorLimitsCLI,
)


class TestPresets(unittest.TestCase):
    """Test workload presets."""

    def test_presets_exist(self):
        self.assertIn("inference", PRESETS)
        self.assertIn("training", PRESETS)
        self.assertIn("batch", PRESETS)
        self.assertIn("interactive", PRESETS)

    def test_inference_preset(self):
        preset = PRESETS["inference"]
        self.assertEqual(preset["cpu_cores"], 4)
        self.assertEqual(preset["memory_gb"], 32)
        self.assertEqual(preset["gpu_percent"], 100)
        self.assertEqual(preset["oom_score"], -500)

    def test_training_preset(self):
        preset = PRESETS["training"]
        self.assertEqual(preset["cpu_cores"], 16)
        self.assertEqual(preset["memory_gb"], 128)
        self.assertEqual(preset["gpu_percent"], 100)

    def test_batch_preset(self):
        preset = PRESETS["batch"]
        self.assertEqual(preset["gpu_percent"], 80)
        self.assertEqual(preset["oom_score"], 0)

    def test_interactive_preset(self):
        preset = PRESETS["interactive"]
        self.assertEqual(preset["cpu_cores"], 2)
        self.assertEqual(preset["memory_gb"], 16)


class TestResourceProfile(unittest.TestCase):
    """Test resource profile management."""

    def test_create_from_preset(self):
        profile = ResourceProfile.from_preset("my-job", "inference")
        self.assertEqual(profile.name, "my-job")
        self.assertEqual(profile.preset, "inference")
        self.assertEqual(profile.cpu_cores, 4)
        self.assertEqual(profile.memory_gb, 32)

    def test_create_with_overrides(self):
        profile = ResourceProfile.from_preset(
            "custom-job",
            "training",
            cpu_cores=32,
            memory_gb=256,
        )
        self.assertEqual(profile.cpu_cores, 32)
        self.assertEqual(profile.memory_gb, 256)
        self.assertEqual(profile.preset, "training")

    def test_invalid_preset(self):
        with self.assertRaises(ValueError) as ctx:
            ResourceProfile.from_preset("job", "nonexistent")
        self.assertIn("Unknown preset", str(ctx.exception))

    def test_to_dict(self):
        profile = ResourceProfile.from_preset("test", "inference")
        data = profile.to_dict()
        self.assertEqual(data["name"], "test")
        self.assertEqual(data["preset"], "inference")
        self.assertIn("created_at", data)

    def test_from_dict(self):
        original = ResourceProfile.from_preset("test", "batch")
        data = original.to_dict()
        restored = ResourceProfile.from_dict(data)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.preset, original.preset)
        self.assertEqual(restored.cpu_cores, original.cpu_cores)

    def test_gpu_devices(self):
        profile = ResourceProfile.from_preset(
            "multi-gpu",
            "training",
            gpu_devices=[0, 1, 2, 3],
        )
        self.assertEqual(profile.gpu_devices, [0, 1, 2, 3])

    def test_cpu_affinity(self):
        profile = ResourceProfile(
            name="affinity-test",
            cpu_affinity=[0, 1, 2, 3],
        )
        self.assertEqual(profile.cpu_affinity, [0, 1, 2, 3])


class TestProfileStore(unittest.TestCase):
    """Test profile persistence."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ProfileStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_and_load(self):
        profile = ResourceProfile.from_preset("test-profile", "inference")
        self.store.save(profile)

        loaded = self.store.load("test-profile")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "test-profile")
        self.assertEqual(loaded.preset, "inference")

    def test_load_nonexistent(self):
        loaded = self.store.load("nonexistent")
        self.assertIsNone(loaded)

    def test_delete(self):
        profile = ResourceProfile.from_preset("to-delete", "batch")
        self.store.save(profile)

        self.assertTrue(self.store.delete("to-delete"))
        self.assertIsNone(self.store.load("to-delete"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("nonexistent"))

    def test_list_profiles(self):
        self.store.save(ResourceProfile.from_preset("p1", "inference"))
        self.store.save(ResourceProfile.from_preset("p2", "training"))
        self.store.save(ResourceProfile.from_preset("p3", "batch"))

        profiles = self.store.list_profiles()
        self.assertIn("p1", profiles)
        self.assertIn("p2", profiles)
        self.assertIn("p3", profiles)
        self.assertEqual(len(profiles), 3)

    def test_empty_list(self):
        profiles = self.store.list_profiles()
        self.assertEqual(profiles, [])


class TestGPUManager(unittest.TestCase):
    """Test GPU environment variable management."""

    def test_cuda_visible_devices(self):
        profile = ResourceProfile(
            name="gpu-test",
            gpu_devices=[0, 2],
        )
        env = GPUManager.get_env_vars(profile)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,2")

    def test_no_gpu_devices(self):
        profile = ResourceProfile(name="no-gpu")
        env = GPUManager.get_env_vars(profile)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", env)

    def test_tensorflow_memory_fraction(self):
        profile = ResourceProfile(
            name="tf-test",
            gpu_percent=50,
        )
        env = GPUManager.get_env_vars(profile)
        self.assertEqual(env["TF_FORCE_GPU_ALLOW_GROWTH"], "true")
        self.assertEqual(env["TF_GPU_MEMORY_FRACTION"], "0.5")

    def test_pytorch_alloc_conf(self):
        profile = ResourceProfile(
            name="pt-test",
            gpu_percent=80,
            memory_gb=64,
        )
        env = GPUManager.get_env_vars(profile)
        self.assertIn("PYTORCH_CUDA_ALLOC_CONF", env)

    def test_full_gpu_no_fraction(self):
        profile = ResourceProfile(
            name="full-gpu",
            gpu_percent=100,
        )
        env = GPUManager.get_env_vars(profile)
        self.assertNotIn("TF_GPU_MEMORY_FRACTION", env)


class TestCgroupsController(unittest.TestCase):
    """Test cgroups v2 controller (mock mode)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.controller = CgroupsController(base_path=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_get_cgroup_path(self):
        path = self.controller._get_cgroup_path("test-profile")
        self.assertIn("cortex.slice", str(path))
        self.assertIn("test-profile", str(path))

    def test_create_cgroup_permission_denied(self):
        # Without proper cgroup setup, should handle gracefully
        profile = ResourceProfile.from_preset("test", "inference")
        # Should not raise, just warn
        result = self.controller.create_cgroup(profile)
        # May be True or False depending on permissions, but shouldn't crash
        self.assertIsInstance(result, bool)

    def test_get_status_nonexistent(self):
        status = self.controller.get_status("nonexistent")
        self.assertEqual(status["name"], "nonexistent")
        self.assertFalse(status["exists"])
        self.assertEqual(status["pids"], [])


class TestCLI(unittest.TestCase):
    """Test CLI commands."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ProfileStore(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_initialization(self):
        cli = AcceleratorLimitsCLI()
        self.assertIsNotNone(cli.store)
        self.assertIsNotNone(cli.cgroups)
        self.assertIsNotNone(cli.gpu)

    @patch('accelerator_limits.ProfileStore')
    @patch('accelerator_limits.CgroupsController')
    def test_create_command(self, mock_cgroups, mock_store):
        cli = AcceleratorLimitsCLI()
        cli.store = self.store
        cli.cgroups = MagicMock()
        cli.cgroups.create_cgroup.return_value = True

        args = MagicMock()
        args.name = "test-job"
        args.preset = "inference"
        args.gpus = None
        args.memory = None
        args.cpus = None

        cli.create(args)

        loaded = self.store.load("test-job")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.preset, "inference")

    def test_presets_command(self):
        cli = AcceleratorLimitsCLI()
        cli.store = self.store
        args = MagicMock()

        # Should not raise
        cli.presets(args)


class TestEndToEnd(unittest.TestCase):
    """End-to-end tests simulating actual usage."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = ProfileStore(self.temp_dir)
        self.gpu = GPUManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_create_inference_job(self):
        # Create profile
        profile = ResourceProfile.from_preset(
            "llm-inference",
            "inference",
            gpu_devices=[0, 1],
        )
        self.store.save(profile)

        # Load and verify
        loaded = self.store.load("llm-inference")
        self.assertEqual(loaded.cpu_cores, 4)
        self.assertEqual(loaded.memory_gb, 32)
        self.assertEqual(loaded.gpu_devices, [0, 1])

        # Get env vars
        env = GPUManager.get_env_vars(loaded)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")

    def test_create_training_job(self):
        profile = ResourceProfile.from_preset(
            "train-bert",
            "training",
            cpu_cores=32,
            memory_gb=256,
            gpu_devices=[0, 1, 2, 3, 4, 5, 6, 7],
        )
        self.store.save(profile)

        loaded = self.store.load("train-bert")
        self.assertEqual(loaded.cpu_cores, 32)
        self.assertEqual(loaded.memory_gb, 256)
        self.assertEqual(len(loaded.gpu_devices), 8)

    def test_batch_job_workflow(self):
        # Create batch profile with limited GPU
        profile = ResourceProfile.from_preset(
            "batch-embeddings",
            "batch",
            gpu_devices=[2],
            gpu_percent=50,
        )
        self.store.save(profile)

        loaded = self.store.load("batch-embeddings")
        env = GPUManager.get_env_vars(loaded)

        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "2")
        self.assertIn("TF_GPU_MEMORY_FRACTION", env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
