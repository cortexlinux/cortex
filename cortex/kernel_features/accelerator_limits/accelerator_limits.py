#!/usr/bin/env python3
"""
Accelerator-Aware Resource Limits - cgroups v2 Wrapper for AI Workloads

Wraps Linux cgroups v2 with an AI-friendly CLI for managing GPU, CPU,
and memory resources with workload presets.

Usage:
    cortex limits create inference-job --preset inference --gpus 2
    cortex limits apply inference-job --pid 12345
    eval $(cortex limits env inference-job)
    cortex limits status inference-job

Author: Yair Siegel
Bounty: cortexlinux/cortex#222
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# =============================================================================
# WORKLOAD PRESETS
# =============================================================================

PRESETS = {
    "inference": {
        "description": "Low-latency serving",
        "cpu_cores": 4,
        "memory_gb": 32,
        "gpu_percent": 100,
        "oom_score": -500,
    },
    "training": {
        "description": "Long training jobs",
        "cpu_cores": 16,
        "memory_gb": 128,
        "gpu_percent": 100,
        "oom_score": -800,
    },
    "batch": {
        "description": "Background processing",
        "cpu_cores": 8,
        "memory_gb": 64,
        "gpu_percent": 80,
        "oom_score": 0,
    },
    "interactive": {
        "description": "Development",
        "cpu_cores": 2,
        "memory_gb": 16,
        "gpu_percent": 50,
        "oom_score": -200,
    },
}

# =============================================================================
# PROFILE MANAGEMENT
# =============================================================================

@dataclass
class ResourceProfile:
    """Resource limit profile for AI workloads."""
    name: str
    preset: str = "inference"

    # CPU limits
    cpu_cores: int = 4
    cpu_weight: int = 100  # 1-10000, default 100
    cpu_affinity: Optional[List[int]] = None

    # Memory limits
    memory_gb: int = 32
    memory_soft_gb: Optional[int] = None  # Soft limit
    swap_gb: int = 0

    # GPU limits
    gpu_percent: int = 100
    gpu_devices: Optional[List[int]] = None  # CUDA_VISIBLE_DEVICES

    # OOM and priority
    oom_score: int = -500  # -1000 to 1000
    nice: int = 0  # -20 to 19

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_preset(cls, name: str, preset: str, **overrides) -> 'ResourceProfile':
        """Create profile from preset with optional overrides."""
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESETS.keys())}")

        preset_values = PRESETS[preset].copy()
        preset_values.pop("description", None)
        preset_values.update(overrides)

        return cls(name=name, preset=preset, **preset_values)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResourceProfile':
        return cls(**data)


# =============================================================================
# CGROUPS V2 CONTROLLER
# =============================================================================

class CgroupsController:
    """
    Manages cgroups v2 for AI workloads.

    Supports user-mode delegation (no root required if configured).
    """

    def __init__(self, base_path: str = "/sys/fs/cgroup"):
        self.base_path = Path(base_path)
        self.user_slice = f"user.slice/user-{os.getuid()}.slice"
        self.cortex_group = "cortex.slice"

    def _get_cgroup_path(self, profile_name: str) -> Path:
        """Get cgroup path for profile."""
        # Try user delegation first, fall back to system
        user_path = self.base_path / self.user_slice / self.cortex_group / profile_name
        system_path = self.base_path / self.cortex_group / profile_name

        if user_path.parent.exists():
            return user_path
        return system_path

    def create_cgroup(self, profile: ResourceProfile) -> bool:
        """Create cgroup for profile."""
        cgroup_path = self._get_cgroup_path(profile.name)

        try:
            # Create directory
            cgroup_path.mkdir(parents=True, exist_ok=True)

            # Enable controllers
            self._enable_controllers(cgroup_path.parent, ["cpu", "memory", "io"])

            # Apply limits
            self._apply_cpu_limits(cgroup_path, profile)
            self._apply_memory_limits(cgroup_path, profile)

            return True
        except PermissionError:
            print(f"[WARN] Permission denied creating cgroup. Running in simulation mode.")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to create cgroup: {e}")
            return False

    def _enable_controllers(self, parent_path: Path, controllers: List[str]):
        """Enable controllers in parent cgroup."""
        subtree_control = parent_path / "cgroup.subtree_control"
        if subtree_control.exists():
            try:
                current = subtree_control.read_text().split()
                for controller in controllers:
                    if controller not in current:
                        subtree_control.write_text(f"+{controller}")
            except:
                pass  # Best effort

    def _apply_cpu_limits(self, cgroup_path: Path, profile: ResourceProfile):
        """Apply CPU limits to cgroup."""
        # CPU weight (shares)
        cpu_weight = cgroup_path / "cpu.weight"
        if cpu_weight.exists():
            cpu_weight.write_text(str(profile.cpu_weight))

        # CPU quota (cores * 100000 / period)
        cpu_max = cgroup_path / "cpu.max"
        if cpu_max.exists():
            period = 100000  # Default period
            quota = profile.cpu_cores * period
            cpu_max.write_text(f"{quota} {period}")

    def _apply_memory_limits(self, cgroup_path: Path, profile: ResourceProfile):
        """Apply memory limits to cgroup."""
        # Hard limit
        memory_max = cgroup_path / "memory.max"
        if memory_max.exists():
            memory_bytes = profile.memory_gb * 1024 * 1024 * 1024
            memory_max.write_text(str(memory_bytes))

        # Soft limit
        if profile.memory_soft_gb:
            memory_high = cgroup_path / "memory.high"
            if memory_high.exists():
                soft_bytes = profile.memory_soft_gb * 1024 * 1024 * 1024
                memory_high.write_text(str(soft_bytes))

        # Swap limit
        memory_swap = cgroup_path / "memory.swap.max"
        if memory_swap.exists():
            swap_bytes = profile.swap_gb * 1024 * 1024 * 1024
            memory_swap.write_text(str(swap_bytes))

    def apply_to_pid(self, profile_name: str, pid: int) -> bool:
        """Move process to cgroup."""
        cgroup_path = self._get_cgroup_path(profile_name)
        procs_file = cgroup_path / "cgroup.procs"

        try:
            if procs_file.exists():
                procs_file.write_text(str(pid))
                return True
            else:
                print(f"[WARN] Cgroup not found. Setting OOM score only.")
                self._set_oom_score(pid, -500)
                return True
        except Exception as e:
            print(f"[ERROR] Failed to apply cgroup: {e}")
            return False

    def _set_oom_score(self, pid: int, score: int):
        """Set OOM score adjustment for process."""
        oom_adj = Path(f"/proc/{pid}/oom_score_adj")
        try:
            if oom_adj.exists():
                oom_adj.write_text(str(score))
        except:
            pass

    def get_status(self, profile_name: str) -> Dict:
        """Get cgroup status."""
        cgroup_path = self._get_cgroup_path(profile_name)
        status = {
            "name": profile_name,
            "path": str(cgroup_path),
            "exists": cgroup_path.exists(),
            "pids": [],
            "memory_current": 0,
            "cpu_usage": 0,
        }

        if cgroup_path.exists():
            # Get PIDs
            procs_file = cgroup_path / "cgroup.procs"
            if procs_file.exists():
                status["pids"] = [int(p) for p in procs_file.read_text().split() if p]

            # Get memory usage
            memory_current = cgroup_path / "memory.current"
            if memory_current.exists():
                status["memory_current"] = int(memory_current.read_text().strip())

            # Get CPU stats
            cpu_stat = cgroup_path / "cpu.stat"
            if cpu_stat.exists():
                for line in cpu_stat.read_text().split('\n'):
                    if line.startswith("usage_usec"):
                        status["cpu_usage"] = int(line.split()[1])

        return status

    def delete_cgroup(self, profile_name: str) -> bool:
        """Delete cgroup."""
        cgroup_path = self._get_cgroup_path(profile_name)

        try:
            if cgroup_path.exists():
                # Move processes to parent first
                procs = (cgroup_path / "cgroup.procs").read_text().split()
                if procs:
                    parent_procs = cgroup_path.parent / "cgroup.procs"
                    for pid in procs:
                        if pid:
                            parent_procs.write_text(pid)

                cgroup_path.rmdir()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to delete cgroup: {e}")
            return False


# =============================================================================
# GPU ENVIRONMENT MANAGEMENT
# =============================================================================

class GPUManager:
    """Manages GPU allocation via environment variables."""

    @staticmethod
    def get_env_vars(profile: ResourceProfile) -> Dict[str, str]:
        """Generate GPU environment variables for profile."""
        env = {}

        # CUDA_VISIBLE_DEVICES
        if profile.gpu_devices is not None:
            env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, profile.gpu_devices))

        # Memory fraction (for TensorFlow)
        if profile.gpu_percent < 100:
            fraction = profile.gpu_percent / 100
            env["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"
            env["TF_GPU_MEMORY_FRACTION"] = str(fraction)

        # PyTorch memory fraction
        if profile.gpu_percent < 100:
            env["PYTORCH_CUDA_ALLOC_CONF"] = f"max_split_size_mb:{profile.memory_gb * 1024 // 4}"

        return env

    @staticmethod
    def print_env_export(profile: ResourceProfile):
        """Print shell export commands for GPU environment."""
        env = GPUManager.get_env_vars(profile)
        for key, value in env.items():
            print(f"export {key}={value}")


# =============================================================================
# PROFILE STORAGE
# =============================================================================

class ProfileStore:
    """Persistent storage for resource profiles."""

    def __init__(self, store_path: str = None):
        if store_path is None:
            store_path = os.path.expanduser("~/.config/cortex/limits")
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)

    def save(self, profile: ResourceProfile):
        """Save profile to disk."""
        profile_path = self.store_path / f"{profile.name}.json"
        with open(profile_path, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)

    def load(self, name: str) -> Optional[ResourceProfile]:
        """Load profile from disk."""
        profile_path = self.store_path / f"{name}.json"
        if profile_path.exists():
            with open(profile_path) as f:
                return ResourceProfile.from_dict(json.load(f))
        return None

    def delete(self, name: str) -> bool:
        """Delete profile from disk."""
        profile_path = self.store_path / f"{name}.json"
        if profile_path.exists():
            profile_path.unlink()
            return True
        return False

    def list_profiles(self) -> List[str]:
        """List all saved profiles."""
        return [p.stem for p in self.store_path.glob("*.json")]


# =============================================================================
# CLI
# =============================================================================

class AcceleratorLimitsCLI:
    """CLI for cortex limits command."""

    def __init__(self):
        self.store = ProfileStore()
        self.cgroups = CgroupsController()
        self.gpu = GPUManager()

    def create(self, args):
        """Create a new resource profile."""
        overrides = {}
        if args.gpus is not None:
            overrides["gpu_devices"] = list(range(args.gpus))
        if args.memory:
            overrides["memory_gb"] = args.memory
        if args.cpus:
            overrides["cpu_cores"] = args.cpus

        profile = ResourceProfile.from_preset(args.name, args.preset, **overrides)

        # Create cgroup
        self.cgroups.create_cgroup(profile)

        # Save profile
        self.store.save(profile)

        print(f"Created profile '{args.name}' with preset '{args.preset}'")
        print(f"  CPU: {profile.cpu_cores} cores")
        print(f"  Memory: {profile.memory_gb} GB")
        print(f"  GPU: {profile.gpu_percent}%")
        print(f"  OOM Score: {profile.oom_score}")

    def apply(self, args):
        """Apply profile to a process."""
        profile = self.store.load(args.name)
        if not profile:
            print(f"Profile '{args.name}' not found")
            return 1

        if self.cgroups.apply_to_pid(args.name, args.pid):
            print(f"Applied profile '{args.name}' to PID {args.pid}")
            return 0
        return 1

    def env(self, args):
        """Print environment variables for profile."""
        profile = self.store.load(args.name)
        if not profile:
            print(f"# Profile '{args.name}' not found", file=sys.stderr)
            return 1

        self.gpu.print_env_export(profile)
        return 0

    def status(self, args):
        """Show status of a profile."""
        profile = self.store.load(args.name)
        if not profile:
            print(f"Profile '{args.name}' not found")
            return 1

        status = self.cgroups.get_status(args.name)

        print(f"Profile: {args.name}")
        print(f"  Preset: {profile.preset}")
        print(f"  Cgroup exists: {status['exists']}")
        print(f"  Active PIDs: {len(status['pids'])}")
        if status['pids']:
            print(f"    PIDs: {status['pids'][:10]}{'...' if len(status['pids']) > 10 else ''}")
        print(f"  Memory usage: {status['memory_current'] / (1024**3):.2f} GB")
        print(f"  CPU usage: {status['cpu_usage'] / 1_000_000:.2f}s")

    def list_cmd(self, args):
        """List all profiles."""
        profiles = self.store.list_profiles()
        if not profiles:
            print("No profiles found")
            return

        print("Available profiles:")
        for name in profiles:
            profile = self.store.load(name)
            if profile:
                print(f"  {name} ({profile.preset}): {profile.cpu_cores} CPU, {profile.memory_gb}GB RAM")

    def delete(self, args):
        """Delete a profile."""
        if self.cgroups.delete_cgroup(args.name):
            self.store.delete(args.name)
            print(f"Deleted profile '{args.name}'")
        else:
            print(f"Failed to delete profile '{args.name}'")

    def presets(self, args):
        """List available presets."""
        print("Available presets:")
        for name, config in PRESETS.items():
            print(f"\n  {name}:")
            print(f"    Description: {config['description']}")
            print(f"    CPU: {config['cpu_cores']} cores")
            print(f"    Memory: {config['memory_gb']} GB")
            print(f"    GPU: {config['gpu_percent']}%")
            print(f"    OOM Score: {config['oom_score']}")


def main():
    parser = argparse.ArgumentParser(
        description="Accelerator-Aware Resource Limits",
        prog="cortex limits"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Create resource profile")
    create_parser.add_argument("name", help="Profile name")
    create_parser.add_argument("--preset", "-p", default="inference",
                               choices=list(PRESETS.keys()), help="Preset to use")
    create_parser.add_argument("--gpus", type=int, help="Number of GPUs")
    create_parser.add_argument("--memory", type=int, help="Memory in GB")
    create_parser.add_argument("--cpus", type=int, help="Number of CPU cores")

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply profile to process")
    apply_parser.add_argument("name", help="Profile name")
    apply_parser.add_argument("--pid", type=int, required=True, help="Process ID")

    # env
    env_parser = subparsers.add_parser("env", help="Print environment variables")
    env_parser.add_argument("name", help="Profile name")

    # status
    status_parser = subparsers.add_parser("status", help="Show profile status")
    status_parser.add_argument("name", help="Profile name")

    # list
    subparsers.add_parser("list", help="List all profiles")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete profile")
    delete_parser.add_argument("name", help="Profile name")

    # presets
    subparsers.add_parser("presets", help="List available presets")

    args = parser.parse_args()
    cli = AcceleratorLimitsCLI()

    commands = {
        "create": cli.create,
        "apply": cli.apply,
        "env": cli.env,
        "status": cli.status,
        "list": cli.list_cmd,
        "delete": cli.delete,
        "presets": cli.presets,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
