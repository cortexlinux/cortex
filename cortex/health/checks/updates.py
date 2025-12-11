import subprocess
from ..monitor import HealthCheck, CheckResult

class UpdateCheck(HealthCheck):
    def run(self) -> CheckResult:
        score = 100
        pkg_count = 0
        sec_count = 0
        rec = None
        
        # Parse apt list --upgradable
        try:
            # Execute safely without pipeline
            res = subprocess.run(
                ["apt", "list", "--upgradable"], 
                capture_output=True, text=True
            )
            
            lines = res.stdout.splitlines()
            # Skip first line "Listing..."
            for line in lines[1:]:
                if line.strip():
                    pkg_count += 1
                    if "security" in line.lower():
                        sec_count += 1
            
            # Scoring
            score -= (pkg_count * 2) # -2 pts per normal package
            score -= (sec_count * 10) # -10 pts per security package
            
            if pkg_count > 0:
                rec = f"Install {pkg_count} updates (+{100-score} pts)"

        except FileNotFoundError:
            # Skip on non-apt environments (100 pts)
            return CheckResult("Updates", "updates", 100, "SKIP", "apt not found", weight=0.30)
        except Exception:
            pass # Ignore errors

        status = "OK"
        if score < 60: status = "CRITICAL"
        elif score < 100: status = "WARNING"
        
        details = f"{pkg_count} pending"
        if sec_count > 0:
            details += f" ({sec_count} security)"

        return CheckResult(
            name="System Updates",
            category="updates",
            score=max(0, score),
            status=status,
            details=details,
            recommendation=rec,
            weight=0.30 # 30%
        )