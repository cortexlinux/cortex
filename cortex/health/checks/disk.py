import shutil
from ..monitor import HealthCheck, CheckResult

class DiskCheck(HealthCheck):
    def run(self) -> CheckResult:
        total, used, free = shutil.disk_usage("/")
        # Calculate usage percentage
        usage_percent = (used / total) * 100
        
        score = 100
        status = "OK"
        details = f"{usage_percent:.1f}% Used"
        rec = None

        # Scoring logic (Spec compliant)
        if usage_percent > 90:
            score = 0
            status = "CRITICAL"
            rec = "Clean package cache (+50 pts)"
        elif usage_percent > 80:
            score = 50
            status = "WARNING"
            rec = "Clean package cache (+10 pts)"
        
        return CheckResult(
            name="Disk Space",
            category="disk",
            score=score,
            status=status,
            details=details,
            recommendation=rec,
            weight=0.15  # 15%
        )