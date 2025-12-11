import shutil
from ..monitor import HealthCheck, CheckResult

class DiskCheck(HealthCheck):
    """Check root filesystem disk usage."""

    def run(self) -> CheckResult:
        """
        Calculate disk usage percentage.
        
        Returns:
            CheckResult based on usage thresholds.
        """
        # Use _ for unused variable (free space)
        total, used, _ = shutil.disk_usage("/")
        usage_percent = (used / total) * 100
        
        score = 100
        status = "OK"
        rec = None
        
        if usage_percent > 90:
            score = 0
            status = "CRITICAL"
            rec = "Clean up disk space immediately"
        elif usage_percent > 80:
            score = 50
            status = "WARNING"
            rec = "Consider cleaning up disk space"
            
        return CheckResult(
            name="Disk Usage",
            category="disk",
            score=score,
            status=status,
            details=f"{usage_percent:.1f}% used",
            recommendation=rec,
            weight=0.20
        )