#!/usr/bin/env python3
"""
System Requirements Pre-flight Checker for Cortex Linux
Validates system meets requirements before installation begins.
"""

import os
import sys
import platform
import shutil
import subprocess
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class CheckStatus(Enum):
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class RequirementCheck:
    name: str
    status: CheckStatus
    message: str
    can_continue: bool = True
    
    def __str__(self) -> str:
        status_symbol = {
            CheckStatus.PASS: "[PASS]",
            CheckStatus.WARNING: "[WARN]",
            CheckStatus.ERROR: "[FAIL]"
        }.get(self.status, "[?]")
        return f"{status_symbol} {self.name}: {self.message}"


@dataclass
class PackageRequirements:
    package_name: str
    min_disk_space_gb: float = 1.0
    min_ram_gb: float = 2.0
    supported_os: List[str] = None
    supported_architectures: List[str] = None
    required_packages: List[str] = None
    
    def __post_init__(self):
        if self.supported_os is None:
            self.supported_os = ["ubuntu", "debian", "fedora", "centos", "rhel"]
        if self.supported_architectures is None:
            self.supported_architectures = ["x86_64", "amd64"]
        if self.required_packages is None:
            self.required_packages = []


class SystemRequirementsChecker:
    PACKAGE_REQUIREMENTS = {
        'oracle-23-ai': PackageRequirements(
            package_name='oracle-23-ai',
            min_disk_space_gb=30.0,
            min_ram_gb=8.0,
            required_packages=['gcc', 'make', 'libaio1'],
        ),
    }
    
    def __init__(self, force_mode: bool = False, json_output: bool = False):
        self.force_mode = force_mode
        self.json_output = json_output
        self.checks: List[RequirementCheck] = []
        self.has_errors = False
    
    def check_disk_space(self, required_gb: float) -> RequirementCheck:
        try:
            if PSUTIL_AVAILABLE:
                disk = psutil.disk_usage('/')
                available_gb = disk.free / (1024 ** 3)
            else:
                if os.name == 'nt':
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p('C:\\'), None, None, ctypes.pointer(free_bytes)
                    )
                    available_gb = free_bytes.value / (1024 ** 3)
                else:
                    result = subprocess.run(['df', '-BG', '/'], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        parts = result.stdout.strip().split('\n')[1].split()
                        available_gb = float(parts[3].replace('G', ''))
                    else:
                        available_gb = 0
            
            if available_gb >= required_gb:
                return RequirementCheck("Disk Space", CheckStatus.PASS, 
                    f"{available_gb:.1f}GB available ({required_gb:.1f}GB required)")
            else:
                return RequirementCheck("Disk Space", CheckStatus.ERROR,
                    f"Insufficient disk space: {available_gb:.1f}GB available, {required_gb:.1f}GB required",
                    can_continue=False)
        except Exception as e:
            return RequirementCheck("Disk Space", CheckStatus.WARNING,
                f"Could not check disk space: {str(e)}")
    
    def check_ram(self, required_gb: float) -> RequirementCheck:
        try:
            if PSUTIL_AVAILABLE:
                mem = psutil.virtual_memory()
                total_gb = mem.total / (1024 ** 3)
            else:
                if os.name == 'nt':
                    import ctypes
                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                                   ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                                   ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                                   ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                                   ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
                    stat = MEMORYSTATUSEX()
                    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                    total_gb = stat.ullTotalPhys / (1024 ** 3)
                else:
                    with open('/proc/meminfo', 'r') as f:
                        meminfo = f.read()
                    total_match = re.search(r'MemTotal:\s+(\d+)', meminfo)
                    total_gb = int(total_match.group(1)) / (1024 ** 2) if total_match else 0
            
            if total_gb >= required_gb:
                return RequirementCheck("RAM", CheckStatus.PASS,
                    f"{total_gb:.1f}GB total ({required_gb:.1f}GB required)")
            else:
                return RequirementCheck("RAM", CheckStatus.ERROR,
                    f"Insufficient RAM: {total_gb:.1f}GB total ({required_gb:.1f}GB required)",
                    can_continue=False)
        except Exception as e:
            return RequirementCheck("RAM", CheckStatus.WARNING, f"Could not check RAM: {str(e)}")
    
    def check_os(self, supported_os: List[str]) -> RequirementCheck:
        try:
            system = platform.system().lower()
            if system == 'linux':
                os_name, os_version = self._detect_linux_distribution()
                if os_name.lower() in [s.lower() for s in supported_os]:
                    return RequirementCheck("OS", CheckStatus.PASS, f"{os_name} {os_version}")
                else:
                    return RequirementCheck("OS", CheckStatus.WARNING,
                        f"{os_name} {os_version} (not officially supported)")
            else:
                return RequirementCheck("OS", CheckStatus.INFO, f"{system}")
        except Exception as e:
            return RequirementCheck("OS", CheckStatus.WARNING, f"Could not detect OS: {str(e)}")
    
    def check_architecture(self, supported_architectures: List[str]) -> RequirementCheck:
        arch = platform.machine().lower()
        if arch in [a.lower() for a in supported_architectures]:
            return RequirementCheck("Architecture", CheckStatus.PASS, arch)
        else:
            return RequirementCheck("Architecture", CheckStatus.WARNING,
                f"{arch} (not officially supported)")
    
    def check_packages(self, required_packages: List[str]) -> RequirementCheck:
        missing = []
        for pkg in required_packages:
            if not shutil.which(pkg):
                missing.append(pkg)
        
        if not missing:
            return RequirementCheck("Packages", CheckStatus.PASS,
                f"All required packages found: {', '.join(required_packages)}")
        else:
            return RequirementCheck("Packages", CheckStatus.WARNING,
                f"Missing packages: {', '.join(missing)}")
    
    def check_gpu(self) -> RequirementCheck:
        try:
            if os.name == 'nt':
                result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                    capture_output=True, text=True, timeout=5)
                if 'NVIDIA' in result.stdout or 'AMD' in result.stdout:
                    return RequirementCheck("GPU", CheckStatus.PASS, "GPU detected")
            else:
                result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=5)
                if 'NVIDIA' in result.stdout or 'AMD' in result.stdout:
                    return RequirementCheck("GPU", CheckStatus.PASS, "GPU detected")
            return RequirementCheck("GPU", CheckStatus.INFO, "No GPU detected")
        except Exception:
            return RequirementCheck("GPU", CheckStatus.INFO, "Could not check GPU")
    
    def _detect_linux_distribution(self) -> Tuple[str, str]:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                content = f.read()
            name_match = re.search(r'^ID=(.+)$', content, re.MULTILINE)
            version_match = re.search(r'^VERSION_ID=(.+)$', content, re.MULTILINE)
            name = name_match.group(1).strip('"') if name_match else 'unknown'
            version = version_match.group(1).strip('"') if version_match else 'unknown'
            return name, version
        return 'linux', 'unknown'
    
    def check_all(self, package_name: str) -> bool:
        if package_name not in self.PACKAGE_REQUIREMENTS:
            reqs = PackageRequirements(package_name=package_name)
        else:
            reqs = self.PACKAGE_REQUIREMENTS[package_name]
        
        self.checks = [
            self.check_disk_space(reqs.min_disk_space_gb),
            self.check_ram(reqs.min_ram_gb),
            self.check_os(reqs.supported_os),
            self.check_architecture(reqs.supported_architectures),
            self.check_packages(reqs.required_packages),
            self.check_gpu(),
        ]
        
        self.has_errors = any(c.status == CheckStatus.ERROR for c in self.checks)
        return not self.has_errors or self.force_mode
    
    def print_results(self):
        if self.json_output:
            print(json.dumps([{
                'name': c.name,
                'status': c.status.value,
                'message': c.message
            } for c in self.checks], indent=2))
        else:
            for check in self.checks:
                print(check)
            if self.has_errors and not self.force_mode:
                print("\nCannot proceed: System does not meet minimum requirements")
                return False
        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Check system requirements')
    parser.add_argument('package', help='Package name')
    parser.add_argument('--force', action='store_true', help='Force installation despite warnings')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()
    
    checker = SystemRequirementsChecker(force_mode=args.force, json_output=args.json)
    success = checker.check_all(args.package)
    checker.print_results()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

