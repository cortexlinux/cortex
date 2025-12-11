import subprocess
import os
from ..monitor import HealthCheck, CheckResult

class SecurityCheck(HealthCheck):
    """Check security configuration including firewall and SSH settings."""

    def run(self) -> CheckResult:
        """
        Run security checks for firewall status and SSH configuration.
        
        Returns:
            CheckResult with security score based on detected issues.
        """
        score = 100
        issues = []
        recommendations = []
        
        # 1. Firewall (UFW) Check
        ufw_active, ufw_issue, ufw_rec = self._check_firewall()
        if not ufw_active:
            score = 0
            issues.append(ufw_issue)
            recommendations.append(ufw_rec)

        # 2. SSH Root Login Check
        ssh_penalty, ssh_issue, ssh_rec = self._check_ssh_root_login()
        if ssh_penalty > 0:
            score -= ssh_penalty
            issues.append(ssh_issue)
            recommendations.append(ssh_rec)

        status = "OK"
        if score < 50: status = "CRITICAL"
        elif score < 100: status = "WARNING"

        return CheckResult(
            name="Security Posture",
            category="security",
            score=max(0, score),
            status=status,
            details=", ".join(issues) if issues else "Secure",
            recommendation=", ".join(recommendations) if recommendations else None,
            weight=0.35
        )

    def _check_firewall(self):
        """Check if UFW is active."""
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "ufw"], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if res.returncode == 0 and res.stdout.strip() == "active":
                return True, None, None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
        
        return False, "Firewall Inactive", "Enable UFW Firewall"

    def _check_ssh_root_login(self):
        """Check for PermitRootLogin yes in sshd_config."""
        try:
            ssh_config = "/etc/ssh/sshd_config"
            if os.path.exists(ssh_config):
                with open(ssh_config, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("PermitRootLogin") and "yes" in line.split():
                            return 50, "Root SSH Allowed", "Disable SSH Root Login in sshd_config"
        except (PermissionError, Exception):
            pass
        
        return 0, None, None