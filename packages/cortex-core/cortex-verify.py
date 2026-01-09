#!/usr/bin/env python3
"""
Cortex Linux Offline Verification Tool
Validates installation integrity, signatures, and provenance without network access.

Copyright 2025 AI Venture Holdings LLC
SPDX-License-Identifier: Apache-2.0
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Trust bundle paths
TRUST_BUNDLE_DIR = Path("/usr/share/cortex/trust")
KEYRING_PATH = Path("/usr/share/keyrings/cortex-archive-keyring.gpg")
SBOM_DIR = Path("/usr/share/cortex/sbom")

# Verification targets
APT_SOURCES_DIR = Path("/etc/apt/sources.list.d")
ISO_CHECKSUMS_URL = "https://cortexlinux.com/releases"


@dataclass
class VerificationResult:
    """Result of a verification check."""
    name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)
    severity: str = "error"  # error, warning, info


@dataclass
class VerificationReport:
    """Complete verification report."""
    timestamp: str
    hostname: str
    cortex_version: str
    checks: list
    passed: int
    failed: int
    warnings: int
    overall_status: str


class CortexVerify:
    """Cortex verification tool."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[VerificationResult] = []

    def _log(self, message: str):
        """Log message if verbose."""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    def _run_cmd(self, cmd: list, check: bool = False) -> subprocess.CompletedProcess:
        """Run command and return result."""
        self._log(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _add_result(self, result: VerificationResult):
        """Add a verification result."""
        self.results.append(result)

    # =========================================================================
    # KEYRING VERIFICATION
    # =========================================================================

    def verify_keyring(self) -> VerificationResult:
        """Verify Cortex archive keyring is installed and valid."""
        if not KEYRING_PATH.exists():
            return VerificationResult(
                name="keyring_installed",
                passed=False,
                message=f"Cortex keyring not found at {KEYRING_PATH}",
                severity="error"
            )

        # Check keyring permissions
        stat = KEYRING_PATH.stat()
        if stat.st_mode & 0o777 != 0o644:
            return VerificationResult(
                name="keyring_permissions",
                passed=False,
                message=f"Keyring has incorrect permissions: {oct(stat.st_mode & 0o777)}",
                severity="warning"
            )

        # Verify keyring content
        result = self._run_cmd(["gpg", "--show-keys", str(KEYRING_PATH)])
        if result.returncode != 0:
            return VerificationResult(
                name="keyring_valid",
                passed=False,
                message="Keyring is not valid GPG keyring",
                details={"error": result.stderr},
                severity="error"
            )

        # Extract key info
        key_info = result.stdout

        return VerificationResult(
            name="keyring",
            passed=True,
            message="Cortex archive keyring is valid",
            details={"path": str(KEYRING_PATH), "key_info": key_info[:500]}
        )

    # =========================================================================
    # APT REPOSITORY VERIFICATION
    # =========================================================================

    def verify_apt_sources(self) -> VerificationResult:
        """Verify APT sources are properly configured with Signed-By."""
        cortex_sources = list(APT_SOURCES_DIR.glob("*cortex*"))

        if not cortex_sources:
            return VerificationResult(
                name="apt_sources",
                passed=False,
                message="No Cortex APT sources found",
                severity="error"
            )

        issues = []
        for source_file in cortex_sources:
            content = source_file.read_text()

            # Check for Signed-By
            if "Signed-By" not in content and "signed-by" not in content.lower():
                issues.append(f"{source_file.name}: Missing Signed-By directive")

            # Check for deb822 format
            if source_file.suffix == ".sources":
                if "Types:" not in content:
                    issues.append(f"{source_file.name}: Not valid deb822 format")

        if issues:
            return VerificationResult(
                name="apt_sources",
                passed=False,
                message=f"APT source issues: {len(issues)}",
                details={"issues": issues},
                severity="warning"
            )

        return VerificationResult(
            name="apt_sources",
            passed=True,
            message=f"APT sources properly configured ({len(cortex_sources)} files)",
            details={"files": [f.name for f in cortex_sources]}
        )

    def verify_apt_signatures(self) -> VerificationResult:
        """Verify APT repository signatures."""
        # Check InRelease files
        apt_lists = Path("/var/lib/apt/lists")
        cortex_releases = list(apt_lists.glob("*cortex*InRelease"))

        if not cortex_releases:
            return VerificationResult(
                name="apt_signatures",
                passed=True,
                message="No cached Cortex repository metadata (run apt update)",
                severity="info"
            )

        verified = []
        failed = []

        for release_file in cortex_releases:
            result = self._run_cmd([
                "gpgv",
                "--keyring", str(KEYRING_PATH),
                str(release_file)
            ])

            if result.returncode == 0:
                verified.append(release_file.name)
            else:
                failed.append({
                    "file": release_file.name,
                    "error": result.stderr
                })

        if failed:
            return VerificationResult(
                name="apt_signatures",
                passed=False,
                message=f"Repository signature verification failed: {len(failed)} file(s)",
                details={"verified": verified, "failed": failed},
                severity="error"
            )

        return VerificationResult(
            name="apt_signatures",
            passed=True,
            message=f"Repository signatures verified ({len(verified)} file(s))",
            details={"verified": verified}
        )

    # =========================================================================
    # PACKAGE VERIFICATION
    # =========================================================================

    def verify_installed_packages(self) -> VerificationResult:
        """Verify installed Cortex packages."""
        # Get list of Cortex packages
        result = self._run_cmd(["dpkg", "-l", "cortex-*"])
        if result.returncode != 0 or not result.stdout.strip():
            return VerificationResult(
                name="installed_packages",
                passed=False,
                message="No Cortex packages installed",
                severity="warning"
            )

        packages = []
        for line in result.stdout.strip().split("\n"):
            if line.startswith("ii"):
                parts = line.split()
                if len(parts) >= 3:
                    packages.append({
                        "name": parts[1],
                        "version": parts[2],
                    })

        # Verify package integrity
        issues = []
        for pkg in packages:
            result = self._run_cmd(["dpkg", "-V", pkg["name"]])
            if result.stdout.strip():
                issues.append({
                    "package": pkg["name"],
                    "issues": result.stdout.strip()
                })

        if issues:
            return VerificationResult(
                name="installed_packages",
                passed=False,
                message=f"Package integrity issues found in {len(issues)} package(s)",
                details={"packages": packages, "issues": issues},
                severity="warning"
            )

        return VerificationResult(
            name="installed_packages",
            passed=True,
            message=f"Cortex packages verified ({len(packages)} installed)",
            details={"packages": packages}
        )

    # =========================================================================
    # SBOM VERIFICATION
    # =========================================================================

    def verify_sbom(self) -> VerificationResult:
        """Verify SBOM is present and valid."""
        if not SBOM_DIR.exists():
            return VerificationResult(
                name="sbom",
                passed=True,
                message="SBOM directory not found (optional)",
                severity="info"
            )

        sbom_files = list(SBOM_DIR.glob("*.json"))
        if not sbom_files:
            return VerificationResult(
                name="sbom",
                passed=True,
                message="No SBOM files found",
                severity="info"
            )

        valid_sboms = []
        invalid_sboms = []

        for sbom_file in sbom_files:
            try:
                with open(sbom_file) as f:
                    data = json.load(f)

                # Check for CycloneDX
                if "bomFormat" in data and data["bomFormat"] == "CycloneDX":
                    valid_sboms.append({
                        "file": sbom_file.name,
                        "format": "CycloneDX",
                        "version": data.get("specVersion", "unknown")
                    })
                # Check for SPDX
                elif "spdxVersion" in data:
                    valid_sboms.append({
                        "file": sbom_file.name,
                        "format": "SPDX",
                        "version": data.get("spdxVersion", "unknown")
                    })
                else:
                    invalid_sboms.append(sbom_file.name)

            except (json.JSONDecodeError, IOError) as e:
                invalid_sboms.append(f"{sbom_file.name}: {e}")

        if invalid_sboms:
            return VerificationResult(
                name="sbom",
                passed=False,
                message=f"Invalid SBOM files: {len(invalid_sboms)}",
                details={"valid": valid_sboms, "invalid": invalid_sboms},
                severity="warning"
            )

        return VerificationResult(
            name="sbom",
            passed=True,
            message=f"SBOM files valid ({len(valid_sboms)} files)",
            details={"sboms": valid_sboms}
        )

    # =========================================================================
    # ISO VERIFICATION
    # =========================================================================

    def verify_iso(self, iso_path: str) -> VerificationResult:
        """Verify ISO image checksum and signature."""
        iso_file = Path(iso_path)

        if not iso_file.exists():
            return VerificationResult(
                name="iso",
                passed=False,
                message=f"ISO file not found: {iso_path}",
                severity="error"
            )

        # Look for checksum file
        checksum_file = iso_file.with_suffix(iso_file.suffix + ".sha256")
        if not checksum_file.exists():
            checksum_file = iso_file.parent / "SHA256SUMS"

        if not checksum_file.exists():
            return VerificationResult(
                name="iso_checksum",
                passed=False,
                message="Checksum file not found",
                details={"searched": [
                    str(iso_file.with_suffix(iso_file.suffix + ".sha256")),
                    str(iso_file.parent / "SHA256SUMS")
                ]},
                severity="warning"
            )

        # Calculate checksum
        print(f"  Calculating SHA256 of {iso_file.name}...")
        sha256 = hashlib.sha256()
        with open(iso_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192 * 1024), b""):
                sha256.update(chunk)
        calculated = sha256.hexdigest()

        # Read expected checksum
        checksum_content = checksum_file.read_text()
        expected = None
        for line in checksum_content.split("\n"):
            if iso_file.name in line:
                expected = line.split()[0]
                break

        if not expected:
            return VerificationResult(
                name="iso_checksum",
                passed=False,
                message=f"No checksum found for {iso_file.name} in {checksum_file.name}",
                severity="error"
            )

        if calculated.lower() != expected.lower():
            return VerificationResult(
                name="iso_checksum",
                passed=False,
                message="ISO checksum mismatch!",
                details={
                    "expected": expected,
                    "calculated": calculated
                },
                severity="error"
            )

        # Look for signature file
        sig_file = checksum_file.with_suffix(checksum_file.suffix + ".asc")
        if not sig_file.exists():
            sig_file = checksum_file.with_suffix(checksum_file.suffix + ".sig")

        if sig_file.exists():
            result = self._run_cmd([
                "gpgv",
                "--keyring", str(KEYRING_PATH),
                str(sig_file),
                str(checksum_file)
            ])

            if result.returncode != 0:
                return VerificationResult(
                    name="iso",
                    passed=False,
                    message="ISO checksum signature verification failed",
                    details={"error": result.stderr},
                    severity="error"
                )

            return VerificationResult(
                name="iso",
                passed=True,
                message="ISO checksum and signature verified",
                details={"checksum": calculated, "signature": "valid"}
            )

        return VerificationResult(
            name="iso",
            passed=True,
            message="ISO checksum verified (no signature file found)",
            details={"checksum": calculated},
            severity="info"
        )

    # =========================================================================
    # SYSTEM INTEGRITY
    # =========================================================================

    def verify_system_integrity(self) -> VerificationResult:
        """Verify core system file integrity."""
        critical_files = [
            "/etc/apt/sources.list.d/cortex.sources",
            "/usr/share/keyrings/cortex-archive-keyring.gpg",
            "/etc/cortex/cortex.yaml",
        ]

        missing = []
        present = []

        for filepath in critical_files:
            if Path(filepath).exists():
                present.append(filepath)
            else:
                missing.append(filepath)

        if missing:
            return VerificationResult(
                name="system_integrity",
                passed=False,
                message=f"Missing critical files: {len(missing)}",
                details={"present": present, "missing": missing},
                severity="warning"
            )

        return VerificationResult(
            name="system_integrity",
            passed=True,
            message=f"Critical files present ({len(present)} files)",
            details={"files": present}
        )

    # =========================================================================
    # MAIN VERIFICATION
    # =========================================================================

    def run_all_checks(self, iso_path: Optional[str] = None) -> VerificationReport:
        """Run all verification checks."""
        self.results = []

        checks = [
            ("Keyring", self.verify_keyring),
            ("APT Sources", self.verify_apt_sources),
            ("APT Signatures", self.verify_apt_signatures),
            ("Installed Packages", self.verify_installed_packages),
            ("SBOM", self.verify_sbom),
            ("System Integrity", self.verify_system_integrity),
        ]

        if iso_path:
            checks.append(("ISO", lambda: self.verify_iso(iso_path)))

        for name, check_func in checks:
            try:
                result = check_func()
                self._add_result(result)
            except Exception as e:
                self._add_result(VerificationResult(
                    name=name.lower().replace(" ", "_"),
                    passed=False,
                    message=f"Check failed: {e}",
                    severity="error"
                ))

        # Calculate summary
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed and r.severity == "error")
        warnings = sum(1 for r in self.results if not r.passed and r.severity == "warning")

        if failed > 0:
            overall = "FAILED"
        elif warnings > 0:
            overall = "WARNING"
        else:
            overall = "PASSED"

        # Get hostname and version
        hostname = os.uname().nodename
        version = "unknown"
        try:
            result = self._run_cmd(["dpkg-query", "-W", "-f=${Version}", "cortex-core"])
            if result.returncode == 0:
                version = result.stdout.strip()
        except Exception:
            pass

        return VerificationReport(
            timestamp=datetime.now().isoformat(),
            hostname=hostname,
            cortex_version=version,
            checks=[{
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "severity": r.severity,
                "details": r.details,
            } for r in self.results],
            passed=passed,
            failed=failed,
            warnings=warnings,
            overall_status=overall,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Cortex Linux Offline Verification Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex-verify                    Run all verification checks
  cortex-verify --iso cortex.iso   Verify ISO file
  cortex-verify --json             Output as JSON
  cortex-verify --json > report.json  Save report
        """
    )

    parser.add_argument("--iso", metavar="FILE", help="ISO file to verify")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--sign-report", action="store_true",
                        help="Sign the JSON report (requires GPG key)")

    args = parser.parse_args()

    verifier = CortexVerify(verbose=args.verbose)

    print("\n" + "=" * 60)
    print("  CORTEX VERIFICATION")
    print("=" * 60 + "\n")

    report = verifier.run_all_checks(iso_path=args.iso)

    if args.json:
        output = {
            "timestamp": report.timestamp,
            "hostname": report.hostname,
            "cortex_version": report.cortex_version,
            "overall_status": report.overall_status,
            "summary": {
                "passed": report.passed,
                "failed": report.failed,
                "warnings": report.warnings,
            },
            "checks": report.checks,
        }
        print(json.dumps(output, indent=2))
    else:
        for check in report.checks:
            if check["passed"]:
                icon = "✅"
            elif check["severity"] == "error":
                icon = "❌"
            else:
                icon = "⚠️"

            print(f"  {icon} {check['name']}: {check['message']}")

        print("\n" + "-" * 60)
        print(f"  Status: {report.overall_status}")
        print(f"  Passed: {report.passed}  |  Failed: {report.failed}  |  Warnings: {report.warnings}")
        print("-" * 60 + "\n")

    # Exit code
    if report.overall_status == "FAILED":
        sys.exit(1)
    elif report.overall_status == "WARNING":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
