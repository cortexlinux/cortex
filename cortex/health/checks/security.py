import subprocess
import os
from ..monitor import HealthCheck, CheckResult

class SecurityCheck(HealthCheck):
    def run(self) -> CheckResult:
        score = 100
        issues = []
        recommendations = []
        
        # 1. Firewall (UFW) Check
        ufw_active = False
        try:
            # Add timeout to prevent hanging (Fixes Reliability Issue)
            res = subprocess.run(
                ["systemctl", "is-active", "ufw"], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            # Fix: Use exact match to avoid matching "inactive" which contains "active"
            if res.returncode == 0 and res.stdout.strip() == "active":
                ufw_active = True
        except subprocess.TimeoutExpired:
            pass # Command timed out, treat as inactive or unavailable
        except FileNotFoundError:
            pass # Environment without systemctl (e.g., Docker or non-systemd)
        except Exception:
            pass # Generic error protection

        if not ufw_active:
            score = 0 # Spec: 0 points if Firewall is inactive
            issues.append("Firewall Inactive")
            recommendations.append("Enable UFW Firewall")

        # 2. SSH Root Login Check
        try:
            ssh_config = "/etc/ssh/sshd_config"
            if os.path.exists(ssh_config):
                with open(ssh_config, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Check for uncommented PermitRootLogin yes
                        if line.startswith("PermitRootLogin") and "yes" in line.split():
                            score -= 50
                            issues.append("Root SSH Allowed")
                            recommendations.append("Disable SSH Root Login in sshd_config")
                            break
        except PermissionError:
            pass # Cannot read config, skip check
        except Exception:
            pass # Generic error protection

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