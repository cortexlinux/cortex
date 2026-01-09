#!/usr/bin/env python3
"""
Cortex Linux Upgrade Orchestrator
Safe, auditable system upgrades with preflight checks, snapshots, and rollback.

Copyright 2025 AI Venture Holdings LLC
SPDX-License-Identifier: Apache-2.0
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Configuration
CORTEX_CONFIG_DIR = Path("/etc/cortex")
CORTEX_STATE_DIR = Path("/var/lib/cortex")
CORTEX_LOG_DIR = Path("/var/log/cortex")
UPGRADE_STATE_FILE = CORTEX_STATE_DIR / "upgrade-state.json"
AUDIT_LOG = CORTEX_LOG_DIR / "upgrade-audit.log"

# Minimum requirements
MIN_BOOT_SPACE_MB = 500
MIN_ROOT_SPACE_MB = 2000
MIN_KERNELS_TO_KEEP = 2


class UpgradePhase(Enum):
    """Upgrade workflow phases."""
    PREFLIGHT = "preflight"
    SNAPSHOT = "snapshot"
    DOWNLOAD = "download"
    INSTALL = "install"
    VALIDATE = "validate"
    COMPLETE = "complete"
    ROLLBACK = "rollback"
    FAILED = "failed"


@dataclass
class PreflightResult:
    """Result of a single preflight check."""
    name: str
    passed: bool
    message: str
    blocking: bool = True
    details: dict = field(default_factory=dict)


@dataclass
class UpgradeState:
    """Persistent upgrade state for recovery."""
    phase: UpgradePhase
    started_at: str
    snapshot_id: Optional[str] = None
    packages_to_upgrade: list = field(default_factory=list)
    packages_upgraded: list = field(default_factory=list)
    validation_results: dict = field(default_factory=dict)
    error: Optional[str] = None


class CortexUpgrade:
    """Cortex upgrade orchestrator."""

    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.state: Optional[UpgradeState] = None

    def _setup_logging(self) -> logging.Logger:
        """Configure logging."""
        logger = logging.getLogger("cortex-upgrade")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

        # Console handler
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console)

        # Audit log handler
        CORTEX_LOG_DIR.mkdir(parents=True, exist_ok=True)
        audit = logging.FileHandler(AUDIT_LOG)
        audit.setLevel(logging.INFO)
        audit.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        ))
        logger.addHandler(audit)

        return logger

    def _run_cmd(self, cmd: list, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
        """Run a command with logging."""
        self.logger.debug(f"Running: {' '.join(cmd)}")
        if self.dry_run and cmd[0] in ["apt-get", "apt", "dpkg", "lvcreate", "btrfs", "zfs"]:
            self.logger.info(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture,
            text=True
        )

    def _save_state(self):
        """Persist upgrade state for recovery."""
        CORTEX_STATE_DIR.mkdir(parents=True, exist_ok=True)
        if self.state:
            with open(UPGRADE_STATE_FILE, "w") as f:
                json.dump({
                    "phase": self.state.phase.value,
                    "started_at": self.state.started_at,
                    "snapshot_id": self.state.snapshot_id,
                    "packages_to_upgrade": self.state.packages_to_upgrade,
                    "packages_upgraded": self.state.packages_upgraded,
                    "validation_results": self.state.validation_results,
                    "error": self.state.error,
                }, f, indent=2)

    def _load_state(self) -> Optional[UpgradeState]:
        """Load existing upgrade state."""
        if UPGRADE_STATE_FILE.exists():
            with open(UPGRADE_STATE_FILE) as f:
                data = json.load(f)
                return UpgradeState(
                    phase=UpgradePhase(data["phase"]),
                    started_at=data["started_at"],
                    snapshot_id=data.get("snapshot_id"),
                    packages_to_upgrade=data.get("packages_to_upgrade", []),
                    packages_upgraded=data.get("packages_upgraded", []),
                    validation_results=data.get("validation_results", {}),
                    error=data.get("error"),
                )
        return None

    # =========================================================================
    # PREFLIGHT CHECKS
    # =========================================================================

    def check_disk_space(self) -> PreflightResult:
        """Check available disk space."""
        boot_stat = os.statvfs("/boot")
        root_stat = os.statvfs("/")

        boot_free_mb = (boot_stat.f_bavail * boot_stat.f_frsize) // (1024 * 1024)
        root_free_mb = (root_stat.f_bavail * root_stat.f_frsize) // (1024 * 1024)

        if boot_free_mb < MIN_BOOT_SPACE_MB:
            return PreflightResult(
                name="disk_space_boot",
                passed=False,
                message=f"/boot has {boot_free_mb}MB free, need {MIN_BOOT_SPACE_MB}MB",
                details={"boot_free_mb": boot_free_mb, "required_mb": MIN_BOOT_SPACE_MB}
            )

        if root_free_mb < MIN_ROOT_SPACE_MB:
            return PreflightResult(
                name="disk_space_root",
                passed=False,
                message=f"/ has {root_free_mb}MB free, need {MIN_ROOT_SPACE_MB}MB",
                details={"root_free_mb": root_free_mb, "required_mb": MIN_ROOT_SPACE_MB}
            )

        return PreflightResult(
            name="disk_space",
            passed=True,
            message=f"Disk space OK: /boot {boot_free_mb}MB, / {root_free_mb}MB",
            details={"boot_free_mb": boot_free_mb, "root_free_mb": root_free_mb}
        )

    def check_apt_state(self) -> PreflightResult:
        """Check APT is in a clean state."""
        # Check for dpkg interruptions
        result = self._run_cmd(
            ["dpkg", "--audit"],
            check=False
        )
        if result.returncode != 0 or result.stdout.strip():
            return PreflightResult(
                name="apt_state",
                passed=False,
                message="dpkg has interrupted packages. Run: sudo dpkg --configure -a",
                details={"dpkg_audit": result.stdout}
            )

        # Check for held packages
        result = self._run_cmd(
            ["dpkg", "--get-selections"],
            check=False
        )
        held = [line for line in result.stdout.split("\n") if "hold" in line]
        if held:
            return PreflightResult(
                name="apt_state",
                passed=True,
                message=f"Warning: {len(held)} packages on hold",
                blocking=False,
                details={"held_packages": held}
            )

        return PreflightResult(
            name="apt_state",
            passed=True,
            message="APT state is clean"
        )

    def check_repository_access(self) -> PreflightResult:
        """Check repository accessibility."""
        result = self._run_cmd(
            ["apt-get", "update", "-qq"],
            check=False
        )
        if result.returncode != 0:
            # Check if we're in offline mode
            if "Could not resolve" in result.stderr or "Failed to fetch" in result.stderr:
                return PreflightResult(
                    name="repository_access",
                    passed=False,
                    message="Cannot reach repositories. Use --offline for air-gapped upgrades.",
                    details={"error": result.stderr}
                )
            return PreflightResult(
                name="repository_access",
                passed=False,
                message=f"apt-get update failed: {result.stderr}",
                details={"error": result.stderr}
            )

        return PreflightResult(
            name="repository_access",
            passed=True,
            message="Repository access OK"
        )

    def check_kernel_count(self) -> PreflightResult:
        """Check kernel retention for rollback."""
        kernels = list(Path("/boot").glob("vmlinuz-*"))
        kernel_count = len(kernels)

        if kernel_count < MIN_KERNELS_TO_KEEP:
            return PreflightResult(
                name="kernel_count",
                passed=True,
                message=f"Only {kernel_count} kernel(s) installed",
                blocking=False,
                details={"kernel_count": kernel_count, "kernels": [k.name for k in kernels]}
            )

        return PreflightResult(
            name="kernel_count",
            passed=True,
            message=f"{kernel_count} kernels available for rollback",
            details={"kernel_count": kernel_count}
        )

    def check_systemd_health(self) -> PreflightResult:
        """Check for failed systemd units."""
        result = self._run_cmd(
            ["systemctl", "--failed", "--no-legend", "--plain"],
            check=False
        )
        failed_units = [u for u in result.stdout.strip().split("\n") if u]

        if failed_units:
            return PreflightResult(
                name="systemd_health",
                passed=True,
                message=f"Warning: {len(failed_units)} failed unit(s)",
                blocking=False,
                details={"failed_units": failed_units}
            )

        return PreflightResult(
            name="systemd_health",
            passed=True,
            message="All systemd units healthy"
        )

    def check_secure_boot(self) -> PreflightResult:
        """Check Secure Boot status for DKMS compatibility."""
        mokutil_path = shutil.which("mokutil")
        if not mokutil_path:
            return PreflightResult(
                name="secure_boot",
                passed=True,
                message="mokutil not available, skipping Secure Boot check",
                blocking=False
            )

        result = self._run_cmd(
            ["mokutil", "--sb-state"],
            check=False
        )

        secure_boot_enabled = "SecureBoot enabled" in result.stdout

        # Check for DKMS packages
        result = self._run_cmd(
            ["dpkg", "-l", "dkms"],
            check=False
        )
        has_dkms = result.returncode == 0

        if secure_boot_enabled and has_dkms:
            return PreflightResult(
                name="secure_boot",
                passed=True,
                message="Secure Boot enabled with DKMS - ensure MOK keys are enrolled",
                blocking=False,
                details={"secure_boot": True, "dkms_installed": True}
            )

        return PreflightResult(
            name="secure_boot",
            passed=True,
            message=f"Secure Boot: {'enabled' if secure_boot_enabled else 'disabled'}",
            details={"secure_boot": secure_boot_enabled}
        )

    def run_preflights(self) -> list[PreflightResult]:
        """Run all preflight checks."""
        self.logger.info("\n📋 Running preflight checks...\n")

        checks = [
            self.check_disk_space,
            self.check_apt_state,
            self.check_repository_access,
            self.check_kernel_count,
            self.check_systemd_health,
            self.check_secure_boot,
        ]

        results = []
        for check in checks:
            try:
                result = check()
                results.append(result)

                icon = "✅" if result.passed else ("⚠️" if not result.blocking else "❌")
                self.logger.info(f"  {icon} {result.name}: {result.message}")

            except Exception as e:
                results.append(PreflightResult(
                    name=check.__name__,
                    passed=False,
                    message=f"Check failed: {e}",
                    blocking=True
                ))
                self.logger.error(f"  ❌ {check.__name__}: {e}")

        return results

    # =========================================================================
    # SNAPSHOT MANAGEMENT
    # =========================================================================

    def detect_snapshot_backend(self) -> Optional[str]:
        """Detect available snapshot backend."""
        # Check for LVM
        result = self._run_cmd(["lvs", "--noheadings"], check=False)
        if result.returncode == 0 and result.stdout.strip():
            return "lvm"

        # Check for Btrfs
        result = self._run_cmd(["findmnt", "-n", "-o", "FSTYPE", "/"], check=False)
        if "btrfs" in result.stdout:
            return "btrfs"

        # Check for ZFS
        result = self._run_cmd(["zfs", "list", "-H"], check=False)
        if result.returncode == 0:
            return "zfs"

        return None

    def create_snapshot(self) -> Optional[str]:
        """Create a pre-upgrade snapshot if possible."""
        backend = self.detect_snapshot_backend()

        if not backend:
            self.logger.warning("  ⚠️ No snapshot backend available - using package-level rollback only")
            return None

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"cortex-upgrade-{timestamp}"

        self.logger.info(f"\n📸 Creating {backend.upper()} snapshot: {snapshot_id}")

        if self.dry_run:
            self.logger.info(f"  [DRY-RUN] Would create {backend} snapshot")
            return snapshot_id

        try:
            if backend == "lvm":
                # Find root LV
                result = self._run_cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
                root_lv = result.stdout.strip()
                self._run_cmd([
                    "lvcreate", "-s", "-n", snapshot_id,
                    "-L", "10G", root_lv
                ])

            elif backend == "btrfs":
                self._run_cmd([
                    "btrfs", "subvolume", "snapshot",
                    "/", f"/.snapshots/{snapshot_id}"
                ])

            elif backend == "zfs":
                result = self._run_cmd(["zfs", "list", "-H", "-o", "name", "/"])
                root_ds = result.stdout.strip()
                self._run_cmd([
                    "zfs", "snapshot", f"{root_ds}@{snapshot_id}"
                ])

            self.logger.info(f"  ✅ Snapshot created: {snapshot_id}")
            return snapshot_id

        except subprocess.CalledProcessError as e:
            self.logger.error(f"  ❌ Snapshot failed: {e}")
            return None

    def rollback_snapshot(self, snapshot_id: str) -> bool:
        """Rollback to a snapshot."""
        backend = self.detect_snapshot_backend()

        if not backend or not snapshot_id:
            self.logger.error("Cannot rollback: no snapshot available")
            return False

        self.logger.info(f"\n🔄 Rolling back to snapshot: {snapshot_id}")

        if self.dry_run:
            self.logger.info(f"  [DRY-RUN] Would rollback {backend} snapshot")
            return True

        try:
            if backend == "lvm":
                result = self._run_cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
                root_lv = result.stdout.strip()
                self._run_cmd(["lvconvert", "--merge", f"{root_lv.rsplit('/', 1)[0]}/{snapshot_id}"])
                self.logger.info("  ⚠️ LVM merge scheduled - reboot required")

            elif backend == "btrfs":
                self.logger.info("  ⚠️ Btrfs rollback requires boot from snapshot subvolume")
                self.logger.info(f"     Boot parameter: rootflags=subvol=.snapshots/{snapshot_id}")

            elif backend == "zfs":
                result = self._run_cmd(["zfs", "list", "-H", "-o", "name", "/"])
                root_ds = result.stdout.strip()
                self._run_cmd(["zfs", "rollback", f"{root_ds}@{snapshot_id}"])

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"  ❌ Rollback failed: {e}")
            return False

    # =========================================================================
    # UPGRADE EXECUTION
    # =========================================================================

    def get_upgradable_packages(self) -> list[dict]:
        """Get list of packages that can be upgraded."""
        self._run_cmd(["apt-get", "update", "-qq"], check=False)

        result = self._run_cmd([
            "apt", "list", "--upgradable"
        ], check=False)

        packages = []
        for line in result.stdout.strip().split("\n"):
            if "/" in line and "Listing" not in line:
                parts = line.split()
                if parts:
                    name = parts[0].split("/")[0]
                    packages.append({"name": name, "line": line})

        return packages

    def download_packages(self) -> bool:
        """Download packages without installing."""
        self.logger.info("\n📥 Downloading packages...")

        result = self._run_cmd([
            "apt-get", "upgrade", "-d", "-y", "--download-only"
        ], check=False)

        if result.returncode != 0:
            self.logger.error(f"  ❌ Download failed: {result.stderr}")
            return False

        self.logger.info("  ✅ Packages downloaded")
        return True

    def install_packages(self) -> bool:
        """Install downloaded packages."""
        self.logger.info("\n📦 Installing packages...")

        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"

        result = self._run_cmd([
            "apt-get", "upgrade", "-y",
            "-o", "Dpkg::Options::=--force-confold",
            "-o", "Dpkg::Options::=--force-confdef"
        ], check=False)

        if result.returncode != 0:
            self.logger.error(f"  ❌ Installation failed: {result.stderr}")
            return False

        self.logger.info("  ✅ Packages installed")
        return True

    # =========================================================================
    # POST-UPGRADE VALIDATION
    # =========================================================================

    def validate_upgrade(self) -> dict:
        """Run post-upgrade validation checks."""
        self.logger.info("\n🔍 Running post-upgrade validation...\n")

        results = {}

        # Check dpkg state
        result = self._run_cmd(["dpkg", "--audit"], check=False)
        results["dpkg_clean"] = result.returncode == 0 and not result.stdout.strip()
        icon = "✅" if results["dpkg_clean"] else "❌"
        self.logger.info(f"  {icon} dpkg state: {'clean' if results['dpkg_clean'] else 'needs attention'}")

        # Check critical services
        critical_services = ["ssh", "systemd-journald", "systemd-networkd"]
        results["services"] = {}

        for service in critical_services:
            result = self._run_cmd(
                ["systemctl", "is-active", service],
                check=False
            )
            active = result.stdout.strip() == "active"
            results["services"][service] = active
            icon = "✅" if active else "❌"
            self.logger.info(f"  {icon} {service}: {'active' if active else 'inactive'}")

        # Check for reboot required
        reboot_required = Path("/var/run/reboot-required").exists()
        results["reboot_required"] = reboot_required
        if reboot_required:
            self.logger.info("  ⚠️ Reboot required")

        # Check for services needing restart
        result = self._run_cmd(
            ["needrestart", "-b"],
            check=False
        )
        if "NEEDRESTART-SVC" in result.stdout:
            services = [l for l in result.stdout.split("\n") if "NEEDRESTART-SVC" in l]
            results["services_need_restart"] = len(services)
            self.logger.info(f"  ⚠️ {len(services)} service(s) may need restart")

        return results

    # =========================================================================
    # MAIN WORKFLOW
    # =========================================================================

    def plan(self) -> dict:
        """Generate upgrade plan without executing."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  CORTEX UPGRADE PLAN")
        self.logger.info("=" * 60)

        plan = {
            "generated_at": datetime.now().isoformat(),
            "preflights": [],
            "snapshot_backend": None,
            "packages": [],
            "blocking_issues": [],
            "warnings": [],
        }

        # Run preflights
        preflight_results = self.run_preflights()
        for r in preflight_results:
            plan["preflights"].append({
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "blocking": r.blocking,
            })
            if not r.passed and r.blocking:
                plan["blocking_issues"].append(r.message)
            elif not r.passed:
                plan["warnings"].append(r.message)

        # Check snapshot capability
        plan["snapshot_backend"] = self.detect_snapshot_backend()

        # Get upgradable packages
        packages = self.get_upgradable_packages()
        plan["packages"] = packages

        # Summary
        self.logger.info("\n" + "-" * 60)
        self.logger.info("  SUMMARY")
        self.logger.info("-" * 60)
        self.logger.info(f"  Packages to upgrade: {len(packages)}")
        self.logger.info(f"  Snapshot backend: {plan['snapshot_backend'] or 'none'}")
        self.logger.info(f"  Blocking issues: {len(plan['blocking_issues'])}")
        self.logger.info(f"  Warnings: {len(plan['warnings'])}")

        if plan["blocking_issues"]:
            self.logger.error("\n❌ Cannot proceed due to blocking issues:")
            for issue in plan["blocking_issues"]:
                self.logger.error(f"   - {issue}")

        return plan

    def execute(self, skip_snapshot: bool = False, auto_confirm: bool = False) -> bool:
        """Execute full upgrade workflow."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("  CORTEX UPGRADE")
        self.logger.info("=" * 60)

        # Initialize state
        self.state = UpgradeState(
            phase=UpgradePhase.PREFLIGHT,
            started_at=datetime.now().isoformat()
        )
        self._save_state()

        # PHASE 1: Preflight
        preflight_results = self.run_preflights()
        blocking = [r for r in preflight_results if not r.passed and r.blocking]

        if blocking:
            self.logger.error("\n❌ Upgrade blocked by preflight failures")
            self.state.phase = UpgradePhase.FAILED
            self.state.error = "Preflight failures"
            self._save_state()
            return False

        # Get upgrade plan
        packages = self.get_upgradable_packages()
        self.state.packages_to_upgrade = [p["name"] for p in packages]

        if not packages:
            self.logger.info("\n✅ System is up to date")
            self.state.phase = UpgradePhase.COMPLETE
            self._save_state()
            return True

        self.logger.info(f"\n📦 {len(packages)} package(s) to upgrade")

        # Confirmation
        if not auto_confirm and not self.dry_run:
            response = input("\nProceed with upgrade? [y/N]: ")
            if response.lower() != "y":
                self.logger.info("Upgrade cancelled")
                return False

        # PHASE 2: Snapshot
        self.state.phase = UpgradePhase.SNAPSHOT
        self._save_state()

        if not skip_snapshot:
            snapshot_id = self.create_snapshot()
            self.state.snapshot_id = snapshot_id

        # PHASE 3: Download
        self.state.phase = UpgradePhase.DOWNLOAD
        self._save_state()

        if not self.download_packages():
            self.state.phase = UpgradePhase.FAILED
            self.state.error = "Download failed"
            self._save_state()
            return False

        # PHASE 4: Install
        self.state.phase = UpgradePhase.INSTALL
        self._save_state()

        if not self.install_packages():
            self.state.phase = UpgradePhase.FAILED
            self.state.error = "Installation failed"
            self._save_state()

            if self.state.snapshot_id:
                self.logger.info("\n⚠️ Installation failed. Rollback available.")
                response = input("Rollback to snapshot? [y/N]: ")
                if response.lower() == "y":
                    self.rollback_snapshot(self.state.snapshot_id)
            return False

        # PHASE 5: Validate
        self.state.phase = UpgradePhase.VALIDATE
        self._save_state()

        validation = self.validate_upgrade()
        self.state.validation_results = validation

        # PHASE 6: Complete
        self.state.phase = UpgradePhase.COMPLETE
        self._save_state()

        self.logger.info("\n" + "=" * 60)
        self.logger.info("  ✅ UPGRADE COMPLETE")
        self.logger.info("=" * 60)

        if validation.get("reboot_required"):
            self.logger.info("\n⚠️ A reboot is required to complete the upgrade")

        # Cleanup state file on success
        if UPGRADE_STATE_FILE.exists():
            UPGRADE_STATE_FILE.unlink()

        return True


def main():
    parser = argparse.ArgumentParser(
        description="Cortex Linux Upgrade Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex-upgrade plan              Show upgrade plan without executing
  cortex-upgrade execute           Perform upgrade interactively
  cortex-upgrade execute -y        Perform upgrade without confirmation
  cortex-upgrade execute --dry-run Show what would be done
  cortex-upgrade rollback          Rollback to last snapshot
        """
    )

    parser.add_argument("command", choices=["plan", "execute", "rollback", "status"],
                        help="Command to run")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Auto-confirm upgrade")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without executing")
    parser.add_argument("--skip-snapshot", action="store_true",
                        help="Skip pre-upgrade snapshot")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--json", action="store_true",
                        help="Output in JSON format")

    args = parser.parse_args()

    upgrader = CortexUpgrade(dry_run=args.dry_run, verbose=args.verbose)

    if args.command == "plan":
        plan = upgrader.plan()
        if args.json:
            print(json.dumps(plan, indent=2))
        sys.exit(0 if not plan["blocking_issues"] else 1)

    elif args.command == "execute":
        success = upgrader.execute(
            skip_snapshot=args.skip_snapshot,
            auto_confirm=args.yes
        )
        sys.exit(0 if success else 1)

    elif args.command == "rollback":
        state = upgrader._load_state()
        if state and state.snapshot_id:
            success = upgrader.rollback_snapshot(state.snapshot_id)
            sys.exit(0 if success else 1)
        else:
            print("No snapshot available for rollback")
            sys.exit(1)

    elif args.command == "status":
        state = upgrader._load_state()
        if state:
            if args.json:
                print(json.dumps({
                    "phase": state.phase.value,
                    "started_at": state.started_at,
                    "snapshot_id": state.snapshot_id,
                    "error": state.error,
                }, indent=2))
            else:
                print(f"Phase: {state.phase.value}")
                print(f"Started: {state.started_at}")
                if state.snapshot_id:
                    print(f"Snapshot: {state.snapshot_id}")
                if state.error:
                    print(f"Error: {state.error}")
        else:
            print("No upgrade in progress")


if __name__ == "__main__":
    main()
