"""
Permission Auditor & Fixer module.
"""

from .auditor_fixer import PermissionAuditor
from .docker_handler import DockerPermissionHandler

PermissionManager = PermissionAuditor
PermissionFixer = PermissionAuditor


def scan_path(path: str):
    """Compatibility function: Scan a path for permission issues."""
    auditor = PermissionAuditor()
    return auditor.scan_directory(path)


def analyze_permissions(path: str):
    """Compatibility function: Analyze permissions with suggestions."""
    auditor = PermissionAuditor()
    return {"scan": auditor.scan_directory(path), "auditor": auditor}


__all__ = [
    "PermissionAuditor",
    "DockerPermissionHandler",
    "PermissionManager",
    "PermissionFixer",
    "scan_path",
    "analyze_permissions",
]
