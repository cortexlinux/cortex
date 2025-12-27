import io
import sys

from cortex.cli import CortexCLI


def test_build_prompt_without_stdin():
    cli = CortexCLI()
    prompt = cli._build_prompt_with_stdin("install docker")
    assert prompt == "install docker"


def test_build_prompt_with_stdin():
    cli = CortexCLI()
    cli.stdin_data = "some context from stdin"
    prompt = cli._build_prompt_with_stdin("install docker")

    assert "Context (from stdin):" in prompt
    assert "some context from stdin" in prompt
    assert "User instruction:" in prompt
    assert "install docker" in prompt
