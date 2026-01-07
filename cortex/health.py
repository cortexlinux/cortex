"""
Cortex Health Scoring Engine.
Calculates system health scores based on security, resources, and performance.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Any

class HealthEngine:
    """
    Analyzes system diagnostics to produce a numerical health score (0-100).
    
    Acceptance Criteria (Issue #128):
    - Multiple health factors (Security, Resources, Performance)
    - Track score over time via persistent JSON history
    - Generate actionable remediation recommendations
    """
    
    def __init__(self, doctor_results: Dict[str, Any]):
        """
        Initialize with results from the SystemDoctor.
        
        Args:
            doctor_results: Dictionary of diagnostic flags from doctor.py
        """
        self.results = doctor_results
        self.history_file = Path.home() / ".cortex" / "health_history.json"
        
    def get_factor_scores(self) -> Dict[str, int]:
        """
        Calculate independent scores for core health pillars.
        Generalized to remove Role-specific logic.
        """
        factors = {"security": 100, "performance": 100, "resources": 100}
        
        # 1. Security (Weight: 40%)
        # Deduct for lack of sandboxing or missing cloud credentials
        if not self.results.get("firejail_installed"): 
            factors["security"] -= 30
        if not self.results.get("api_keys_set"): 
            factors["security"] -= 20
        
        # 2. Resources (Weight: 30%)
        # Penalize based on hardware limitations
        ram = self.results.get("ram_gb", 0)
        if ram < 4: 
            factors["resources"] -= 50
        elif ram < 8: 
            factors["resources"] -= 20
        
        # 3. Performance (Weight: 30%)
        # Evaluate optimization readiness (GPU presence)
        if not self.results.get("gpu_detected"):
            factors["performance"] -= 20
            
        return {k: max(0, v) for k, v in factors.items()}

    def calculate_overall_score(self) -> int:
        """Calculates a weighted average score from 0-100."""
        factors = self.get_factor_scores()
        
        # Scoring weights define the priority of system health
        overall = (factors["security"] * 0.4) + \
                  (factors["resources"] * 0.3) + \
                  (factors["performance"] * 0.3)
                  
        return int(overall)

    def save_history(self, score: int):
        """
        Persists the current score to a sliding window history file.
        Satisfies 'Track score over time' requirement.
        """
        history = []
        if self.history_file.exists():
            try:
                history = json.loads(self.history_file.read_text())
            except Exception:
                history = []
        
        history.append({
            "timestamp": time.time(),
            "score": score
        })
        
        # Maintain a 10-entry window for trend analysis
        history = history[-10:]
        
        # Ensure the .cortex config directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.history_file.write_text(json.dumps(history, indent=2))

    def get_recommendations(self) -> List[Dict[str, str]]:
        """
        Generates actionable fixes and manual advice based on failed checks.
        """
        recs = []
        
        # Actionable: Security (Firejail installation)
        if not self.results.get("firejail_installed"):
            recs.append({
                "text": "Sandboxing unavailable (Firejail missing)",
                "fix": "sudo apt-get install -y firejail"
            })
            
        # Actionable: Provider Setup (Configuration Wizard)
        if not self.results.get("api_keys_set"):
            recs.append({
                "text": "Cloud AI models not configured",
                "fix": "cortex wizard"
            })

        # Advisory: Hardware upgrade (Non-actionable via script)
        if self.results.get("ram_gb", 0) < 8:
            recs.append({
                "text": "Low RAM detected for AI tasks (16GB+ recommended)",
                "fix": None  
            })
            
        return recs