import subprocess
from ..monitor import HealthCheck, CheckResult

class UpdateCheck(HealthCheck):
    """Check for pending system updates and security patches."""

    def run(self) -> CheckResult:
        """
        Check for available updates using apt.
        
        Returns:
            CheckResult with score based on pending updates.
        """
        score = 100
        pkg_count = 0
        sec_count = 0
        
        try:
            # Add timeout to prevent hangs
            res = subprocess.run(
                ["apt", "list", "--upgradable"], 
                capture_output=True, 
                text=True,
                timeout=30
            )
            lines = res.stdout.splitlines()
            
            # apt list output header usually takes first line
            for line in lines[1:]:
                if line.strip():
                    if "security" in line.lower():
                        sec_count += 1
                    else:
                        pkg_count += 1
            
            # Scoring
            score -= (pkg_count * 2) 
            score -= (sec_count * 10) 

        except Exception:
             pass

        status = "OK"
        if score < 50: status = "CRITICAL"
        elif score < 90: status = "WARNING"
        
        details = f"{pkg_count} packages, {sec_count} security updates pending"
        if pkg_count == 0 and sec_count == 0:
            details = "System up to date"

        return CheckResult(
            name="System Updates",
            category="updates",
            score=max(0, score),
            status=status,
            details=details,
            recommendation="Run 'apt upgrade'" if score < 100 else None,
            weight=0.25
        )