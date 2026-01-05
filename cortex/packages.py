#!/usr/bin/env python3
"""
Intelligent Package Manager Wrapper for Cortex Linux

Translates natural language requests into apt/yum package manager commands.
Supports common software installations, development tools, and libraries.
Enhanced with fuzzy matching for better user experience.
"""

import re
import subprocess
import difflib
from enum import Enum


class PackageManagerType(Enum):
    """Supported package manager types."""

    APT = "apt"  # Ubuntu/Debian
    YUM = "yum"  # RHEL/CentOS/Fedora (older)
    DNF = "dnf"  # RHEL/CentOS/Fedora (newer)


class PackageManager:
    """
    Intelligent wrapper that translates natural language into package manager commands.
    """

    def __init__(self, pm_type: PackageManagerType | None = None):
        self.pm_type = pm_type or self._detect_package_manager()
        self.package_mappings = self._build_package_mappings()
        self.action_patterns = self._build_action_patterns()

    def _detect_package_manager(self) -> PackageManagerType:
        try:
            result = subprocess.run(["which", "apt"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.APT
            result = subprocess.run(["which", "dnf"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.DNF
            result = subprocess.run(["which", "yum"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return PackageManagerType.YUM
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return PackageManagerType.APT

    def _build_action_patterns(self) -> dict[str, list[str]]:
        return {
            "install": [r"\binstall\b", r"\bsetup\b", r"\bget\b", r"\badd\b", r"\bfetch\b", r"\bdownload\b"],
            "remove": [r"\bremove\b", r"\buninstall\b", r"\bdelete\b", r"\bpurge\b"],
            "update": [r"\bupdate\b", r"\bupgrade\b", r"\brefresh\b"],
            "search": [r"\bsearch\b", r"\bfind\b", r"\blookup\b"],
        }

    def _build_package_mappings(self) -> dict[str, dict[str, list[str]]]:
        return {
            "python": {"apt": ["python3", "python3-pip", "python3-venv"], "yum": ["python3", "python3-pip"]},
            "python development": {"apt": ["python3-dev", "python3-pip", "build-essential"], "yum": ["python3-devel", "python3-pip", "gcc", "gcc-c++", "make"]},
            "python data science": {"apt": ["python3", "python3-pip", "python3-numpy", "python3-pandas", "python3-scipy", "python3-matplotlib", "python3-jupyter"], "yum": ["python3", "python3-pip", "python3-numpy", "python3-pandas", "python3-scipy", "python3-matplotlib"]},
            "web development": {"apt": ["nodejs", "npm", "git", "curl", "wget"], "yum": ["nodejs", "npm", "git", "curl", "wget"]},
            "nodejs": {"apt": ["nodejs", "npm"], "yum": ["nodejs", "npm"]},
            "docker": {"apt": ["docker.io", "docker-compose"], "yum": ["docker", "docker-compose"]},
            "nginx": {"apt": ["nginx"], "yum": ["nginx"]},
            "apache": {"apt": ["apache2"], "yum": ["httpd"]},
            "mysql": {"apt": ["mysql-server", "mysql-client"], "yum": ["mysql-server", "mysql"]},
            "postgresql": {"apt": ["postgresql", "postgresql-contrib"], "yum": ["postgresql-server", "postgresql"]},
            "redis": {"apt": ["redis-server"], "yum": ["redis"]},
            "git": {"apt": ["git"], "yum": ["git"]},
            "vim": {"apt": ["vim"], "yum": ["vim"]},
            "curl": {"apt": ["curl"], "yum": ["curl"]},
            "wget": {"apt": ["wget"], "yum": ["wget"]},
            "system monitoring": {"apt": ["htop", "iotop", "nethogs", "sysstat"], "yum": ["htop", "iotop", "nethogs", "sysstat"]},
            "network tools": {"apt": ["net-tools", "iputils-ping", "tcpdump", "wireshark"], "yum": ["net-tools", "iputils", "tcpdump", "wireshark"]},
            "security tools": {"apt": ["ufw", "fail2ban", "openssh-server", "ssl-cert"], "yum": ["firewalld", "fail2ban", "openssh-server"]},
        }

    def _normalize_text(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_action(self, text: str) -> str:
        normalized = self._normalize_text(text)
        for action, patterns in self.action_patterns.items():
            for pattern in patterns:
                if re.search(pattern, normalized):
                    return action
        return "install"

    def _find_matching_packages(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        matched_packages = set()
        pm_key = "apt" if self.pm_type == PackageManagerType.APT else "yum"

        found_exact = False
        # (此处保持原有的精确匹配逻辑，缩减展示)
        for key, packages in self.package_mappings.items():
            if key in normalized:
                matched_packages.update(packages.get(pm_key, []))
                found_exact = True

        # 核心增强：物理注入模糊匹配逻辑
        if not found_exact:
            choices = list(self.package_mappings.keys())
            # 寻找最接近的 3 个词
            matches = difflib.get_close_matches(normalized, choices, n=3, cutoff=0.5)
            if matches:
                print(f"Fuzzy matching found: {matches}")
                for match in matches:
                    matched_packages.update(self.package_mappings[match].get(pm_key, []))

        return sorted(matched_packages)

    def parse(self, request: str) -> list[str]:
        if not request or not request.strip():
            raise ValueError("Empty request provided")
        action = self._extract_action(request)
        packages = self._find_matching_packages(request)
        if not packages:
            raise ValueError(f"No matching packages found for: {request}")
        if self.pm_type == PackageManagerType.APT:
            if action == "install": return [f"apt install -y {' '.join(packages)}"]
            elif action == "remove": return [f"apt remove -y {' '.join(packages)}"]
            elif action == "update": return ["apt update", f"apt upgrade -y {' '.join(packages)}"]
            elif action == "search": return [f"apt search {' '.join(packages)}"]
        return []
