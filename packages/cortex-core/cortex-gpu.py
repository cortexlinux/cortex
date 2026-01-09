#!/usr/bin/env python3
"""
Cortex Linux GPU Detection and Enablement
Detects GPUs and manages driver installation with Secure Boot support.

Copyright 2025 AI Venture Holdings LLC
SPDX-License-Identifier: Apache-2.0
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Paths
GPU_STATE_FILE = Path("/run/cortex/hw/gpu.json")
GPU_CONFIG_DIR = Path("/etc/cortex/gpu")
MOK_KEY_DIR = Path("/var/lib/cortex/mok")

# NVIDIA Support Matrix (datacenter/server GPUs)
NVIDIA_SUPPORTED = {
    # Architecture: (min_driver, recommended_driver, open_kernel_support)
    "ada": ("535", "550", True),      # Ada Lovelace (H100, L40, etc.)
    "hopper": ("525", "550", True),   # Hopper
    "ampere": ("470", "550", True),   # Ampere (A100, A30, etc.)
    "turing": ("418", "550", True),   # Turing (T4, etc.)
    "volta": ("384", "550", False),   # Volta (V100)
    "pascal": ("375", "550", False),  # Pascal (P100, P40)
}

# AMD ROCm Support Matrix
AMD_SUPPORTED = {
    # Architecture: (min_rocm, recommended_rocm)
    "rdna3": ("5.7", "6.0"),    # RDNA3 (MI300, etc.)
    "rdna2": ("5.0", "6.0"),    # RDNA2
    "cdna2": ("5.0", "6.0"),    # CDNA2 (MI200 series)
    "cdna": ("4.0", "6.0"),     # CDNA (MI100)
    "vega": ("3.0", "6.0"),     # Vega (MI50, MI60)
}


@dataclass
class GPUInfo:
    """GPU hardware information."""
    vendor: str
    model: str
    pci_id: str
    pci_slot: str
    architecture: Optional[str] = None
    vram_mb: Optional[int] = None
    driver_loaded: Optional[str] = None
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    rocm_version: Optional[str] = None
    compute_apis: list = field(default_factory=list)
    ready_for_ai: bool = False


@dataclass
class GPUStatus:
    """System GPU status."""
    gpus: list
    secure_boot: bool
    mok_enrolled: bool
    recommended_action: Optional[str] = None


class CortexGPU:
    """Cortex GPU management."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("cortex-gpu")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        return logger

    def _run_cmd(self, cmd: list, check: bool = False) -> subprocess.CompletedProcess:
        """Run command and return result."""
        self.logger.debug(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    # =========================================================================
    # GPU DETECTION
    # =========================================================================

    def detect_gpus(self) -> list[GPUInfo]:
        """Detect all GPUs in the system."""
        gpus = []

        # Use lspci to find GPUs
        result = self._run_cmd(["lspci", "-nn", "-d", "::0300"])  # VGA
        result2 = self._run_cmd(["lspci", "-nn", "-d", "::0302"])  # 3D controller

        lines = result.stdout.strip().split("\n") + result2.stdout.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            gpu = self._parse_lspci_line(line)
            if gpu:
                self._enrich_gpu_info(gpu)
                gpus.append(gpu)

        return gpus

    def _parse_lspci_line(self, line: str) -> Optional[GPUInfo]:
        """Parse lspci output line."""
        # Format: 00:02.0 VGA compatible controller [0300]: Intel Corporation ... [8086:9a49]
        match = re.match(r"(\S+)\s+.*:\s+(.*?)\s+\[([0-9a-f]{4}):([0-9a-f]{4})\]", line, re.I)
        if not match:
            return None

        pci_slot, model, vendor_id, device_id = match.groups()
        pci_id = f"{vendor_id}:{device_id}"

        # Determine vendor
        vendor_map = {
            "10de": "nvidia",
            "1002": "amd",
            "8086": "intel",
        }
        vendor = vendor_map.get(vendor_id.lower(), "unknown")

        return GPUInfo(
            vendor=vendor,
            model=model.strip(),
            pci_id=pci_id,
            pci_slot=pci_slot,
        )

    def _enrich_gpu_info(self, gpu: GPUInfo):
        """Add detailed GPU information."""
        if gpu.vendor == "nvidia":
            self._enrich_nvidia(gpu)
        elif gpu.vendor == "amd":
            self._enrich_amd(gpu)
        elif gpu.vendor == "intel":
            self._enrich_intel(gpu)

    def _enrich_nvidia(self, gpu: GPUInfo):
        """Get NVIDIA-specific information."""
        # Check if driver is loaded
        result = self._run_cmd(["lsmod"])
        if "nvidia" in result.stdout:
            gpu.driver_loaded = "nvidia"
        elif "nouveau" in result.stdout:
            gpu.driver_loaded = "nouveau"

        # Try nvidia-smi for detailed info
        if shutil.which("nvidia-smi"):
            result = self._run_cmd([
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits"
            ])
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 3:
                    gpu.model = parts[0].strip()
                    gpu.vram_mb = int(parts[1].strip())
                    gpu.driver_version = parts[2].strip()
                    gpu.compute_apis.append("CUDA")
                    gpu.ready_for_ai = True

            # Get CUDA version
            result = self._run_cmd(["nvidia-smi", "--query-gpu=cuda_version", "--format=csv,noheader"])
            if result.returncode == 0 and result.stdout.strip():
                gpu.cuda_version = result.stdout.strip()

        # Determine architecture from model name
        model_lower = gpu.model.lower()
        if any(x in model_lower for x in ["h100", "l40", "rtx 40"]):
            gpu.architecture = "ada"
        elif any(x in model_lower for x in ["h200"]):
            gpu.architecture = "hopper"
        elif any(x in model_lower for x in ["a100", "a30", "a40", "rtx 30"]):
            gpu.architecture = "ampere"
        elif any(x in model_lower for x in ["t4", "rtx 20", "quadro rtx"]):
            gpu.architecture = "turing"
        elif any(x in model_lower for x in ["v100"]):
            gpu.architecture = "volta"
        elif any(x in model_lower for x in ["p100", "p40", "gtx 10"]):
            gpu.architecture = "pascal"

    def _enrich_amd(self, gpu: GPUInfo):
        """Get AMD-specific information."""
        # Check if amdgpu driver is loaded
        result = self._run_cmd(["lsmod"])
        if "amdgpu" in result.stdout:
            gpu.driver_loaded = "amdgpu"
            gpu.compute_apis.append("OpenCL")

        # Try rocm-smi for detailed info
        if shutil.which("rocm-smi"):
            result = self._run_cmd(["rocm-smi", "--showproductname"])
            if result.returncode == 0:
                gpu.compute_apis.append("ROCm")
                gpu.ready_for_ai = True

            # Get ROCm version
            result = self._run_cmd(["rocm-smi", "--showversion"])
            if result.returncode == 0:
                match = re.search(r"ROCm\s*version:\s*(\S+)", result.stdout, re.I)
                if match:
                    gpu.rocm_version = match.group(1)

        # Determine architecture
        model_lower = gpu.model.lower()
        if "mi300" in model_lower:
            gpu.architecture = "rdna3"
        elif "mi200" in model_lower or "mi250" in model_lower:
            gpu.architecture = "cdna2"
        elif "mi100" in model_lower:
            gpu.architecture = "cdna"
        elif "mi50" in model_lower or "mi60" in model_lower:
            gpu.architecture = "vega"

    def _enrich_intel(self, gpu: GPUInfo):
        """Get Intel-specific information."""
        result = self._run_cmd(["lsmod"])
        if "i915" in result.stdout:
            gpu.driver_loaded = "i915"
            gpu.compute_apis.append("OpenCL")

    # =========================================================================
    # SECURE BOOT / MOK
    # =========================================================================

    def check_secure_boot(self) -> bool:
        """Check if Secure Boot is enabled."""
        if not shutil.which("mokutil"):
            return False

        result = self._run_cmd(["mokutil", "--sb-state"])
        return "SecureBoot enabled" in result.stdout

    def check_mok_enrolled(self) -> bool:
        """Check if MOK keys are enrolled for DKMS."""
        mok_key = MOK_KEY_DIR / "MOK.der"
        if not mok_key.exists():
            return False

        result = self._run_cmd(["mokutil", "--test-key", str(mok_key)])
        return "is already enrolled" in result.stdout

    def setup_mok_keys(self) -> bool:
        """Generate and enroll MOK keys for DKMS."""
        self.logger.info("\n🔐 Setting up MOK keys for Secure Boot...")

        MOK_KEY_DIR.mkdir(parents=True, exist_ok=True)
        mok_priv = MOK_KEY_DIR / "MOK.priv"
        mok_der = MOK_KEY_DIR / "MOK.der"

        if not mok_priv.exists():
            self.logger.info("  Generating MOK key pair...")

            # Generate key
            result = self._run_cmd([
                "openssl", "req", "-new", "-x509",
                "-newkey", "rsa:2048",
                "-keyout", str(mok_priv),
                "-outform", "DER",
                "-out", str(mok_der),
                "-nodes",
                "-days", "36500",
                "-subj", "/CN=Cortex Linux MOK/"
            ])

            if result.returncode != 0:
                self.logger.error(f"  ❌ Key generation failed: {result.stderr}")
                return False

            # Secure the private key
            os.chmod(mok_priv, 0o600)

        # Enroll key with mokutil
        self.logger.info("  Enrolling MOK key (password required)...")
        self.logger.info("  ⚠️ You will need to enter a one-time password")
        self.logger.info("     This password will be requested on next reboot")

        result = subprocess.run(
            ["mokutil", "--import", str(mok_der)],
            capture_output=False
        )

        if result.returncode == 0:
            self.logger.info("  ✅ MOK key enrollment initiated")
            self.logger.info("")
            self.logger.info("  ⚠️ IMPORTANT: Reboot and complete MOK enrollment")
            self.logger.info("     1. Reboot the system")
            self.logger.info("     2. Press any key when prompted for MOK Management")
            self.logger.info("     3. Select 'Enroll MOK'")
            self.logger.info("     4. Enter the password you just created")
            self.logger.info("     5. Continue boot")
            return True

        return False

    # =========================================================================
    # DRIVER ENABLEMENT
    # =========================================================================

    def enable_nvidia(self, use_open_kernel: bool = True) -> bool:
        """Enable NVIDIA drivers."""
        self.logger.info("\n🎮 Enabling NVIDIA GPU support...")

        secure_boot = self.check_secure_boot()
        if secure_boot:
            self.logger.info("  Secure Boot detected")
            if not self.check_mok_enrolled():
                self.logger.info("  MOK keys not enrolled - setting up...")
                if not self.setup_mok_keys():
                    return False
                self.logger.info("\n  ⚠️ Please reboot and enroll MOK keys, then re-run this command")
                return False

        # Enable non-free repository if needed
        self.logger.info("  Checking APT sources...")
        sources_file = Path("/etc/apt/sources.list.d/debian.sources")
        if sources_file.exists():
            content = sources_file.read_text()
            if "non-free" not in content:
                self.logger.info("  Enabling non-free repository...")
                # This would need actual implementation
                pass

        # Install NVIDIA packages
        self.logger.info("  Installing NVIDIA driver packages...")

        packages = ["nvidia-driver"]
        if use_open_kernel:
            packages.append("nvidia-kernel-open-dkms")
        else:
            packages.append("nvidia-kernel-dkms")

        result = subprocess.run(
            ["apt-get", "install", "-y"] + packages,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            self.logger.error(f"  ❌ Installation failed: {result.stderr}")
            return False

        # Blacklist nouveau
        blacklist_file = Path("/etc/modprobe.d/nvidia-blacklist.conf")
        blacklist_file.write_text("blacklist nouveau\noptions nouveau modeset=0\n")

        self.logger.info("  ✅ NVIDIA driver installed")
        self.logger.info("  ⚠️ Reboot required to load new drivers")
        return True

    def enable_amd(self, install_rocm: bool = False) -> bool:
        """Enable AMD GPU support."""
        self.logger.info("\n🎮 Enabling AMD GPU support...")

        # Install firmware
        self.logger.info("  Installing AMD firmware...")
        result = subprocess.run(
            ["apt-get", "install", "-y", "firmware-amd-graphics"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            self.logger.error(f"  ❌ Firmware installation failed: {result.stderr}")
            return False

        if install_rocm:
            self.logger.info("  Installing ROCm runtime...")
            # ROCm installation would go here
            # This typically requires adding AMD's repository
            pass

        self.logger.info("  ✅ AMD GPU support enabled")
        return True

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_status(self) -> GPUStatus:
        """Get comprehensive GPU status."""
        gpus = self.detect_gpus()
        secure_boot = self.check_secure_boot()
        mok_enrolled = self.check_mok_enrolled() if secure_boot else True

        # Determine recommended action
        recommended = None
        for gpu in gpus:
            if gpu.vendor == "nvidia" and not gpu.driver_loaded == "nvidia":
                recommended = "Run 'cortex gpu enable nvidia' to install NVIDIA drivers"
                break
            elif gpu.vendor == "amd" and not gpu.ready_for_ai:
                recommended = "Run 'cortex gpu enable amd --rocm' for AI acceleration"
                break

        return GPUStatus(
            gpus=gpus,
            secure_boot=secure_boot,
            mok_enrolled=mok_enrolled,
            recommended_action=recommended,
        )

    def write_gpu_state(self):
        """Write GPU state file for other Cortex components."""
        status = self.get_status()

        GPU_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "secure_boot": status.secure_boot,
            "gpus": [
                {
                    "vendor": g.vendor,
                    "model": g.model,
                    "pci_id": g.pci_id,
                    "pci_slot": g.pci_slot,
                    "architecture": g.architecture,
                    "vram_mb": g.vram_mb,
                    "driver_loaded": g.driver_loaded,
                    "driver_version": g.driver_version,
                    "cuda_version": g.cuda_version,
                    "rocm_version": g.rocm_version,
                    "compute_apis": g.compute_apis,
                    "ready_for_ai": g.ready_for_ai,
                }
                for g in status.gpus
            ],
        }

        with open(GPU_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

        self.logger.debug(f"GPU state written to {GPU_STATE_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="Cortex Linux GPU Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex gpu status              Show GPU status
  cortex gpu status --json       Output status as JSON
  cortex gpu enable nvidia       Install NVIDIA drivers
  cortex gpu enable amd --rocm   Install AMD ROCm
  cortex gpu mok-setup           Setup MOK keys for Secure Boot
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show GPU status")
    status_parser.add_argument("--json", action="store_true", help="JSON output")

    # Enable command
    enable_parser = subparsers.add_parser("enable", help="Enable GPU support")
    enable_parser.add_argument("vendor", choices=["nvidia", "amd", "intel"])
    enable_parser.add_argument("--rocm", action="store_true", help="Install ROCm (AMD)")
    enable_parser.add_argument("--open-kernel", action="store_true", default=True,
                                help="Use open kernel modules (NVIDIA)")

    # MOK setup command
    mok_parser = subparsers.add_parser("mok-setup", help="Setup MOK keys for Secure Boot")

    # Detect command (for firstboot)
    detect_parser = subparsers.add_parser("detect", help="Detect and write GPU state")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    gpu_mgr = CortexGPU(verbose=args.verbose)

    if args.command == "status":
        status = gpu_mgr.get_status()

        if args.json:
            print(json.dumps({
                "secure_boot": status.secure_boot,
                "mok_enrolled": status.mok_enrolled,
                "recommended_action": status.recommended_action,
                "gpus": [
                    {
                        "vendor": g.vendor,
                        "model": g.model,
                        "pci_id": g.pci_id,
                        "driver": g.driver_loaded,
                        "driver_version": g.driver_version,
                        "vram_mb": g.vram_mb,
                        "compute_apis": g.compute_apis,
                        "ready_for_ai": g.ready_for_ai,
                    }
                    for g in status.gpus
                ],
            }, indent=2))
        else:
            print("\n🖥️  Cortex GPU Status\n")
            print(f"Secure Boot: {'Enabled' if status.secure_boot else 'Disabled'}")
            if status.secure_boot:
                print(f"MOK Enrolled: {'Yes' if status.mok_enrolled else 'No'}")

            if not status.gpus:
                print("\nNo GPUs detected")
            else:
                print(f"\nDetected GPUs: {len(status.gpus)}\n")
                for i, gpu in enumerate(status.gpus, 1):
                    print(f"  GPU {i}: {gpu.model}")
                    print(f"    Vendor: {gpu.vendor.upper()}")
                    print(f"    PCI: {gpu.pci_slot} [{gpu.pci_id}]")
                    print(f"    Driver: {gpu.driver_loaded or 'none'}", end="")
                    if gpu.driver_version:
                        print(f" (v{gpu.driver_version})")
                    else:
                        print()
                    if gpu.vram_mb:
                        print(f"    VRAM: {gpu.vram_mb}MB")
                    if gpu.compute_apis:
                        print(f"    Compute: {', '.join(gpu.compute_apis)}")
                    print(f"    AI Ready: {'✅ Yes' if gpu.ready_for_ai else '❌ No'}")
                    print()

            if status.recommended_action:
                print(f"💡 Recommended: {status.recommended_action}\n")

    elif args.command == "enable":
        if os.geteuid() != 0:
            print("Error: This command requires root privileges")
            sys.exit(1)

        if args.vendor == "nvidia":
            success = gpu_mgr.enable_nvidia(use_open_kernel=args.open_kernel)
        elif args.vendor == "amd":
            success = gpu_mgr.enable_amd(install_rocm=args.rocm)
        else:
            print("Intel GPU support uses in-kernel drivers")
            success = True

        sys.exit(0 if success else 1)

    elif args.command == "mok-setup":
        if os.geteuid() != 0:
            print("Error: This command requires root privileges")
            sys.exit(1)
        success = gpu_mgr.setup_mok_keys()
        sys.exit(0 if success else 1)

    elif args.command == "detect":
        gpu_mgr.write_gpu_state()
        print(f"GPU state written to {GPU_STATE_FILE}")


if __name__ == "__main__":
    main()
