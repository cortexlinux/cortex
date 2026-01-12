"""
Permission Auditor & Fixer module.
Fixes security issues with dangerous file permissions (777, world-writable).
"""

import logging
import os
import stat
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


class PermissionAuditor:
    """
    Auditor for detecting and fixing dangerous file permissions.

    Detects:
    - World-writable files (others have write permission)
    - Files with 777 permissions
    - Insecure directory permissions
    """

    def __init__(self, verbose=False, dry_run=True, docker_context=False):
        self.verbose = verbose
        self.dry_run = dry_run
        self.docker_handler = None
        self.logger = logging.getLogger(__name__)

        if docker_context:
            from .docker_handler import DockerPermissionHandler

            self.docker_handler = DockerPermissionHandler()

        if verbose:
            self.logger.setLevel(logging.DEBUG)

    def explain_issue_plain_english(self, filepath: str, issue_type: str) -> str:
        """
        Explain permission issue in plain English.

        Args:
            filepath: Path to the file
            issue_type: Type of issue ('world_writable', 'dangerous_777')

        Returns:
            Plain English explanation
        """
        filename = os.path.basename(filepath)

        explanations = {
            "world_writable": (
                f"⚠️ SECURITY RISK: '{filename}' is WORLD-WRITABLE.\n"
                "   This means ANY user on the system can MODIFY this file.\n"
                "   Attackers could: inject malicious code, delete data, or tamper with configurations.\n"
                "   FIX: Restrict write permissions to owner only."
            ),
            "dangerous_777": (
                f"🚨 CRITICAL RISK: '{filename}' has 777 permissions (rwxrwxrwx).\n"
                "   This means EVERYONE can read, write, and execute this file.\n"
                "   This is like leaving your house with doors unlocked and keys in the lock.\n"
                "   FIX: Set appropriate permissions (644 for files, 755 for scripts)."
            ),
        }
        return explanations.get(issue_type, f"Permission issue detected in '{filename}'")

    def scan_directory(self, directory_path: str | Path) -> dict[str, list[str]]:
        """
        Scan directory for dangerous permissions.

        Args:
            directory_path: Path to directory to scan

        Returns:
            Dictionary with keys:
            - 'world_writable': List of world-writable files
            - 'dangerous': List of files with dangerous permissions (777)
            - 'suggestions': List of suggested fixes
            - 'docker_context': True if Docker files found
        """
        path = Path(directory_path).resolve()
        result = {"world_writable": [], "dangerous": [], "suggestions": [], "docker_context": False}

        if not self._validate_path(path):
            return result

        self._check_docker_context(path, result)
        self._scan_files_for_permissions(path, result)

        return result

    def _validate_path(self, path: Path) -> bool:
        """Validate that path exists and is a directory."""
        if not path.exists():
            logger.warning(f"Directory does not exist: {path}")
            return False

        if not path.is_dir():
            logger.warning(f"Path is not a directory: {path}")
            return False

        return True

    def _check_docker_context(self, path: Path, result: dict) -> None:
        """Check for Docker context in current and parent directories."""
        docker_files = ["docker-compose.yml", "docker-compose.yaml", "Dockerfile", ".dockerignore"]

        # Check current directory
        if self._has_docker_files(path, docker_files, result):
            return

        # Check parent directories
        for parent in path.parents:
            if self._has_docker_files(parent, docker_files, result):
                return

    def _has_docker_files(self, directory: Path, docker_files: list, result: dict) -> bool:
        """Check if directory contains any Docker files."""
        for docker_file in docker_files:
            docker_path = directory / docker_file
            if docker_path.exists():
                result["docker_context"] = True
                if self.verbose:
                    logger.debug(f"Docker context detected: {docker_file}")
                return True
        return False

    def _scan_files_for_permissions(self, path: Path, result: dict) -> None:
        """Scan all files in directory for dangerous permissions."""
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    self._check_file_permissions(item, result)
        except OSError as e:
            logger.error(f"Error scanning directory {path}: {e}")

    def _check_file_permissions(self, file_path: Path, result: dict) -> None:
        """Check permissions for a single file."""
        try:
            mode = file_path.stat().st_mode
            str_path = str(file_path)

            self._check_world_writable(mode, str_path, result)
            self._check_dangerous_777(mode, str_path, result)

        except OSError as e:
            if self.verbose:
                logger.debug(f"Cannot access {file_path}: {e}")

    def _check_world_writable(self, mode: int, file_path: str, result: dict) -> None:
        """Check if file is world-writable."""
        if mode & stat.S_IWOTH:
            result["world_writable"].append(file_path)
            suggestion = self.suggest_fix(file_path, current_perms=oct(mode & 0o777))
            result["suggestions"].append(suggestion)

    def _check_dangerous_777(self, mode: int, file_path: str, result: dict) -> None:
        """Check if file has 777 permissions."""
        if (mode & 0o777) == 0o777 and file_path not in result["dangerous"]:
            result["dangerous"].append(file_path)

            # Check if suggestion already exists
            if not self._has_suggestion_for_file(file_path, result["suggestions"]):
                suggestion = self.suggest_fix(file_path, current_perms="777")
                result["suggestions"].append(suggestion)

    def _has_suggestion_for_file(self, file_path: str, suggestions: list) -> bool:
        """Check if suggestion already exists for the file."""
        for suggestion in suggestions:
            if len(suggestion.split()) > 2:
                suggested_file = suggestion.split()[2].strip("'")
                if suggested_file == file_path:
                    return True
        return False

    def suggest_fix(self, filepath: str | Path, current_perms: str | None = None) -> str:
        """
        Suggest correct permissions for a file.

        Args:
            filepath: Path to the file
            current_perms: Current permissions in octal (e.g., '777')

        Returns:
            Suggested chmod command to fix permissions
        """
        path = Path(filepath)

        if not path.exists():
            return f"# File {filepath} doesn't exist"

        try:
            mode = path.stat().st_mode

            # Get file extension and check if executable
            is_executable = mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            is_script = path.suffix in [".sh", ".py", ".pl", ".rb", ".bash"]

            # Suggested permissions based on file type
            if is_executable or is_script:
                suggested = "755"  # rwxr-xr-x
                reason = "executable/script file"
            else:
                suggested = "644"  # rw-r--r--
                reason = "data file"

            current = oct(mode & 0o777)[-3:] if current_perms is None else current_perms

            return f"chmod {suggested} '{filepath}'  # Fix: {current} → {suggested} ({reason})"

        except OSError as e:
            return f"# Cannot access {filepath}: {e}"

    def fix_permissions(
        self, filepath: str | Path, permissions: str = "644", dry_run: bool = True
    ) -> str:
        """
        Fix permissions for a single file.

        Args:
            filepath: Path to the file
            permissions: Permissions in octal (e.g., '644', '755')
            dry_run: If True, only show what would be changed

        Returns:
            Report of the change made or that would be made
        """
        path = Path(filepath)

        if not path.exists():
            return f"File does not exist: {filepath}"

        try:
            current_mode = path.stat().st_mode
            current_perms = oct(current_mode & 0o777)[-3:]

            if dry_run:
                return f"[DRY RUN] Would change {filepath}: {current_perms} → {permissions}"
            else:
                # Preserve file type bits, only change permission bits
                new_mode = (current_mode & ~0o777) | int(permissions, 8)
                path.chmod(new_mode)

                # Verify the change
                verified = oct(path.stat().st_mode & 0o777)[-3:]
                return f"Changed {filepath}: {current_perms} → {verified}"

        except OSError as e:
            return f"Error changing permissions on {filepath}: {e}"

    def scan_and_fix(self, path=".", apply_fixes=False, dry_run=None):
        """
        Scan directory and optionally fix issues.
        Used by CLI command.

        Args:
            path: Directory to scan
            apply_fixes: If True, apply fixes
            dry_run: If None, use self.dry_run; if True/False, override
        """
        dry_run = self.dry_run if dry_run is None else dry_run
        scan_result = self.scan_directory(path)

        report_lines = self._generate_report_header(path, scan_result)
        self._add_docker_context(report_lines, scan_result)
        self._add_issue_sections(report_lines, scan_result)
        self._add_fix_suggestions(report_lines, scan_result)

        fixed_count = 0
        if apply_fixes:
            fixed_count = self._apply_fixes(report_lines, scan_result, dry_run)

        self._finalize_report(report_lines, fixed_count)

        return {
            "report": "\n".join(report_lines),
            "issues_found": len(scan_result["world_writable"]) + len(scan_result["dangerous"]),
            "scan_result": scan_result,
            "fixed": apply_fixes and not dry_run,
        }

    def _generate_report_header(self, path: str, scan_result: dict) -> list:
        """Generate the header section of the report."""
        issues_found = len(scan_result["world_writable"]) + len(scan_result["dangerous"])

        return [
            "🔒 PERMISSION AUDIT REPORT",
            "=" * 50,
            f"Scanned: {path}",
            f"Total issues found: {issues_found}",
            "",
        ]

    def _add_docker_context(self, report_lines: list, scan_result: dict) -> None:
        """Add Docker context information to report if applicable."""
        if self.docker_handler and scan_result.get("docker_context"):
            report_lines.extend(
                [
                    "🐳 DOCKER/CONTAINER CONTEXT:",
                    f"   Running in: {self.docker_handler.container_info['container_runtime'] or 'Native'}",
                    f"   Host UID/GID: {self.docker_handler.container_info['host_uid']}/{self.docker_handler.container_info['host_gid']}",
                    "",
                ]
            )

    def _add_issue_sections(self, report_lines: list, scan_result: dict) -> None:
        """Add world-writable and dangerous files sections to report."""
        self._add_issue_section(
            report_lines,
            scan_result["world_writable"],
            "🚨 WORLD-WRITABLE FILES (others can write):",
            "world_writable",
        )

        self._add_issue_section(
            report_lines, scan_result["dangerous"], "⚠️ DANGEROUS PERMISSIONS (777):", "dangerous"
        )

    def _add_issue_section(self, report_lines: list, files: list, title: str, key: str) -> None:
        """Add a single issue section to the report."""
        if files:
            report_lines.append(title)
            for file in files[:10]:
                report_lines.append(f"  • {file}")

            if len(files) > 10:
                report_lines.append(f"  ... and {len(files) - 10} more")

            report_lines.append("")

    def _add_fix_suggestions(self, report_lines: list, scan_result: dict) -> None:
        """Add suggestions and fix commands to report."""
        if scan_result["suggestions"]:
            self._add_suggestions_list(report_lines, scan_result["suggestions"])
            self._add_one_command_fix(report_lines, scan_result["world_writable"])

    def _add_suggestions_list(self, report_lines: list, suggestions: list) -> None:
        """Add the list of suggested fixes."""
        report_lines.append("💡 SUGGESTED FIXES:")
        for suggestion in suggestions[:5]:
            report_lines.append(f"  {suggestion}")

        if len(suggestions) > 5:
            report_lines.append(f"  ... and {len(suggestions) - 5} more")

    def _add_one_command_fix(self, report_lines: list, world_writable_files: list) -> None:
        """Add the 'one command to fix all' section."""
        report_lines.append("💡 ONE COMMAND TO FIX ALL ISSUES:")
        fix_commands = []

        for file_path in world_writable_files[:10]:
            suggestion = self.suggest_fix(file_path)
            if "chmod" in suggestion:
                parts = suggestion.split()
                if len(parts) >= 3:
                    fix_commands.append(f"{parts[0]} {parts[1]} '{parts[2]}'")

        if fix_commands:
            report_lines.append("   Run this command:")
            report_lines.append("   " + " && ".join(fix_commands[:3]))

            if len(fix_commands) > 3:
                report_lines.append(f"   ... and {len(fix_commands) - 3} more commands")

        report_lines.append("")

    def _apply_fixes(self, report_lines: list, scan_result: dict, dry_run: bool) -> int:
        """Apply fixes to files and update report."""
        report_lines.extend(["", "🛠️ APPLYING FIXES:"])
        fixed_count = 0

        for file_path in scan_result["world_writable"]:
            try:
                fixed = self._apply_single_fix(report_lines, file_path, dry_run)
                if fixed:
                    fixed_count += 1
            except Exception as e:
                report_lines.append(f"  ✗ Error fixing {file_path}: {e}")

        report_lines.append(f"Fixed {fixed_count} files")
        return fixed_count

    def _apply_single_fix(self, report_lines: list, file_path: str, dry_run: bool) -> bool:
        """Apply fix to a single file."""
        suggestion = self.suggest_fix(file_path)

        if "chmod" not in suggestion:
            return False

        parts = suggestion.split()
        if len(parts) < 2:
            return False

        cmd, perms = parts[0], parts[1]
        if cmd != "chmod" or not perms.isdigit():
            return False

        if not dry_run:
            self.fix_permissions(file_path, permissions=perms, dry_run=False)
            report_lines.append(f"  ✓ Fixed: {file_path}")
        else:
            report_lines.append(f"  [DRY RUN] Would fix: {file_path}")

        return True

    def _finalize_report(self, report_lines: list, fixed_count: int) -> None:
        """Add final lines to the report."""
        report_lines.extend(["", "✅ Scan complete"])
