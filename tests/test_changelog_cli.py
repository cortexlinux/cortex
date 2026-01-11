import subprocess
import sys


def test_changelog_command_runs():
    result = subprocess.run(
        [sys.executable, "-m", "cortex.cli", "changelog", "docker"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""
