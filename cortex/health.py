"""
Cortex Health Monitor Module
Integrates system health checks, history tracking, and automated fixes.
"""
import shutil
import psutil
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Persistence Configuration
HISTORY_FILE = Path.home() / ".cortex" / "health_history.json"
console = Console()

@dataclass
class HealthFactor:
    name: str
    status: str  # "good", "warning", "critical"
    details: str
    recommendation: str = ""
    score_impact: int = 0
    fix_action: str = ""

class HealthHistory:
    def __init__(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()

    def _load(self) -> List[Dict]:
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def save(self, score: int, details: List[Dict]):
        record = {
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "details": details
        }
        self.history.append(record)
        self.history = self.history[-50:]
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except IOError:
            pass

    def get_trend(self) -> str:
        if len(self.history) < 1:
            return "No history"
        last_score = self.history[-1]['score']
        return f"Previous: {last_score}"

class HealthEngine:
    def __init__(self):
        self.score = 100
        self.factors: List[HealthFactor] = []
        self.history_mgr = HealthHistory()

    def _check_disk(self):
        total, used, free = shutil.disk_usage("/")
        percent = (used / total) * 100
        if percent > 90:
            self.score -= 20
            self.factors.append(HealthFactor("Disk Space", "critical", f"{percent:.1f}% Used", "Run cleanup.", -20, "clean_disk"))
        elif percent > 80:
            self.score -= 10
            self.factors.append(HealthFactor("Disk Space", "warning", f"{percent:.1f}% Used", "Consider cleanup.", -10, "clean_disk"))
        else:
            self.factors.append(HealthFactor("Disk Space", "good", f"{percent:.1f}% Used"))

    def _check_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            self.score -= 15
            self.factors.append(HealthFactor("Memory", "critical", f"{mem.percent}% Used", "Close apps.", -15))
        else:
            self.factors.append(HealthFactor("Memory", "good", f"{mem.percent}% Used"))

    def _check_cpu(self):
        try:
            load = psutil.getloadavg()[0]
            cores = psutil.cpu_count() or 1
            usage = (load / cores) * 100
        except AttributeError:
            usage = psutil.cpu_percent()

        if usage > 90:
            self.score -= 10
            self.factors.append(HealthFactor("CPU Load", "warning", f"{usage:.1f}%", "High load.", -10))
        else:
            self.factors.append(HealthFactor("CPU Load", "good", f"{usage:.1f}%"))

    def apply_fix(self, fix_id: str) -> bool:
        """Execute automated fixes."""
        if fix_id == "clean_disk":
            time.sleep(0.5) # Mocking fix action
            return True
        return False

    def run_diagnostics(self) -> Tuple[int, List[HealthFactor], str]:
        trend = self.history_mgr.get_trend()
        
        with Progress(SpinnerColumn(), TextColumn("[bold cyan]Scanning...[/bold cyan]"), transient=True) as progress:
            task = progress.add_task("scan", total=3)
            self._check_disk(); progress.advance(task)
            self._check_memory(); progress.advance(task)
            self._check_cpu(); progress.advance(task)
        
        self.score = max(0, self.score)
        self.history_mgr.save(self.score, [asdict(f) for f in self.factors])
        return self.score, self.factors, trend

def check_health():
    """Entry point for the CLI command."""
    engine = HealthEngine()
    score, factors, trend = engine.run_diagnostics()

    color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    emoji = "✅" if score >= 80 else "⚠️" if score >= 50 else "🚨"

    console.print(Panel(
        f"[bold {color}]System Health Score: {score}/100 {emoji}[/bold {color}]\n[dim]{trend}[/dim]",
        title="🛡️ Cortex Health Report",
        expand=False,
        border_style=color
    ))

    table = Table(box=None, show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    recommendations = []
    for f in factors:
        status_style = "red bold" if f.status == "critical" else "yellow" if f.status == "warning" else "green"
        table.add_row(f.name, f"[{status_style}]{f.status.upper()}[/{status_style}]", f.details)
        if f.recommendation:
            recommendations.append(f)

    console.print(table)
    console.print()

    if recommendations:
        console.print("[bold]🔧 Recommendations:[/bold]")
        for rec in recommendations:
            console.print(f" • {rec.name}: {rec.recommendation}")
    else:
        console.print("[green]✨ System is optimal.[/green]")

if __name__ == "__main__":
    check_health()
