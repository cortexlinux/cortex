#!/usr/bin/env python3
"""
Dependency Resolution System
Detects and resolves package dependencies for conflict detection
"""

import subprocess
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Dependency:
    """Represents a package dependency"""
    name: str
    version: Optional[str] = None
    reason: str = ""
    is_satisfied: bool = False
    installed_version: Optional[str] = None


@dataclass
class DependencyGraph:
    """Complete dependency graph for a package"""
    package_name: str
    direct_dependencies: List[Dependency]
    all_dependencies: List[Dependency]
    conflicts: List[Tuple[str, str]]
    installation_order: List[str]


class DependencyResolver:
    """Resolves package dependencies intelligently"""
    
    DEPENDENCY_PATTERNS = {
        'docker': {
            'direct': ['containerd', 'docker-ce-cli', 'docker-buildx-plugin'],
            'system': ['iptables', 'ca-certificates', 'curl', 'gnupg']
        },
        'postgresql': {
            'direct': ['postgresql-common', 'postgresql-client'],
            'optional': ['postgresql-contrib']
        },
        'nginx': {
            'direct': [],
            'runtime': ['libc6', 'libpcre3', 'zlib1g']
        },
        'mysql-server': {
            'direct': ['mysql-client', 'mysql-common'],
            'system': ['libaio1', 'libmecab2']
        },
    }
    
    def __init__(self):
        self.dependency_cache: Dict[str, DependencyGraph] = {}
        self.installed_packages: Set[str] = set()
        self._refresh_installed_packages()
    
    def _run_command(self, cmd: List[str]) -> Tuple[bool, str, str]:
        """Execute command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return (result.returncode == 0, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (False, "", "Command timed out")
        except Exception as e:
            return (False, "", str(e))
    
    def _refresh_installed_packages(self) -> None:
        """Refresh cache of installed packages"""
        logger.info("Refreshing installed packages cache...")
        success, stdout, _ = self._run_command(['dpkg', '-l'])
        
        if success:
            for line in stdout.split('\n'):
                if line.startswith('ii'):
                    parts = line.split()
                    if len(parts) >= 2:
                        self.installed_packages.add(parts[1])
        
        logger.info(f"Found {len(self.installed_packages)} installed packages")
    
    def is_package_installed(self, package_name: str) -> bool:
        """Check if package is installed"""
        return package_name in self.installed_packages
    
    def get_installed_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package"""
        if not self.is_package_installed(package_name):
            return None
        
        success, stdout, _ = self._run_command([
            'dpkg-query', '-W', '-f=${Version}', package_name
        ])
        
        return stdout.strip() if success else None
    
    def get_apt_dependencies(self, package_name: str) -> List[Dependency]:
        """Get dependencies from apt-cache"""
        dependencies = []
        
        success, stdout, stderr = self._run_command([
            'apt-cache', 'depends', package_name
        ])
        
        if not success:
            logger.warning(f"Could not get dependencies for {package_name}: {stderr}")
            return dependencies
        
        for line in stdout.split('\n'):
            line = line.strip()
            
            if line.startswith('Depends:'):
                dep_name = line.split(':', 1)[1].strip()
                if '|' in dep_name:
                    dep_name = dep_name.split('|')[0].strip()
                
                dep_name = re.sub(r'\s*\([^)]*\)', '', dep_name)
                
                is_installed = self.is_package_installed(dep_name)
                installed_ver = self.get_installed_version(dep_name) if is_installed else None
                
                dependencies.append(Dependency(
                    name=dep_name,
                    reason="Required dependency",
                    is_satisfied=is_installed,
                    installed_version=installed_ver
                ))
        
        return dependencies
    
    def get_predefined_dependencies(self, package_name: str) -> List[Dependency]:
        """Get dependencies from predefined patterns"""
        dependencies = []
        
        if package_name not in self.DEPENDENCY_PATTERNS:
            return dependencies
        
        pattern = self.DEPENDENCY_PATTERNS[package_name]
        
        for dep in pattern.get('direct', []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(Dependency(
                name=dep,
                reason="Required dependency",
                is_satisfied=is_installed,
                installed_version=self.get_installed_version(dep) if is_installed else None
            ))
        
        for dep in pattern.get('system', []):
            is_installed = self.is_package_installed(dep)
            dependencies.append(Dependency(
                name=dep,
                reason="System dependency",
                is_satisfied=is_installed,
                installed_version=self.get_installed_version(dep) if is_installed else None
            ))
        
        return dependencies
    
    def resolve_dependencies(self, package_name: str, recursive: bool = True) -> DependencyGraph:
        """
        Resolve all dependencies for a package
        
        Args:
            package_name: Package to resolve dependencies for
            recursive: Whether to resolve transitive dependencies
        """
        logger.info(f"Resolving dependencies for {package_name}...")
        
        if package_name in self.dependency_cache:
            logger.info(f"Using cached dependencies for {package_name}")
            return self.dependency_cache[package_name]
        
        apt_deps = self.get_apt_dependencies(package_name)
        predefined_deps = self.get_predefined_dependencies(package_name)
        
        all_deps: Dict[str, Dependency] = {}
        
        for dep in predefined_deps + apt_deps:
            if dep.name not in all_deps:
                all_deps[dep.name] = dep
        
        direct_dependencies = list(all_deps.values())
        
        transitive_deps: Dict[str, Dependency] = {}
        if recursive:
            for dep in direct_dependencies:
                if not dep.is_satisfied:
                    sub_deps = self.get_apt_dependencies(dep.name)
                    for sub_dep in sub_deps:
                        if sub_dep.name not in all_deps and sub_dep.name not in transitive_deps:
                            transitive_deps[sub_dep.name] = sub_dep
        
        all_dependencies = list(all_deps.values()) + list(transitive_deps.values())
        
        conflicts = self._detect_conflicts(all_dependencies, package_name)
        
        installation_order = self._calculate_installation_order(
            package_name,
            all_dependencies
        )
        
        graph = DependencyGraph(
            package_name=package_name,
            direct_dependencies=direct_dependencies,
            all_dependencies=all_dependencies,
            conflicts=conflicts,
            installation_order=installation_order
        )
        
        self.dependency_cache[package_name] = graph
        
        return graph
    
    def _detect_conflicts(self, dependencies: List[Dependency], package_name: str) -> List[Tuple[str, str]]:
        """Detect conflicting packages"""
        conflicts = []
        
        conflict_patterns = {
            'mysql-server': ['mariadb-server'],
            'mariadb-server': ['mysql-server'],
            'apache2': ['nginx'],
            'nginx': ['apache2']
        }
        
        dep_names = {dep.name for dep in dependencies}
        dep_names.add(package_name)
        
        for dep_name in dep_names:
            if dep_name in conflict_patterns:
                for conflicting in conflict_patterns[dep_name]:
                    if conflicting in dep_names or self.is_package_installed(conflicting):
                        conflicts.append((dep_name, conflicting))
        
        return conflicts
    
    def _calculate_installation_order(
        self,
        package_name: str,
        dependencies: List[Dependency]
    ) -> List[str]:
        """Calculate optimal installation order"""
        no_deps = []
        has_deps = []
        
        for dep in dependencies:
            if not dep.is_satisfied:
                if 'lib' in dep.name or dep.name in ['ca-certificates', 'curl', 'gnupg']:
                    no_deps.append(dep.name)
                else:
                    has_deps.append(dep.name)
        
        order = no_deps + has_deps
        
        if package_name not in order:
            order.append(package_name)
        
        return order
    
    def get_missing_dependencies(self, package_name: str) -> List[Dependency]:
        """Get list of dependencies that need to be installed"""
        graph = self.resolve_dependencies(package_name)
        return [dep for dep in graph.all_dependencies if not dep.is_satisfied]
