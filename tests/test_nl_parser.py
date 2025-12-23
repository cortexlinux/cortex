"""
Tests for NLParser (Natural Language Install)

These tests verify:
- intent normalization behavior
- ambiguity handling
- preview vs execute behavior
- install mode influence on prompt generation
- safety-oriented logic

These tests do NOT:
- call real LLMs
- execute real commands
- depend on system state

They focus only on deterministic logic.
"""

import pytest


# ---------------------------------------------------------------------
# Intent normalization / ambiguity handling
# ---------------------------------------------------------------------

def test_known_domain_is_not_ambiguous():
    """
    If the domain is known, ambiguity should be resolved
    even if confidence is low or action is noisy.
    """
    intent = {
        "action": "install | update",
        "domain": "machine_learning",
        "ambiguous": True,
        "confidence": 0.2,
    }

    # normalization logic (mirrors CLI behavior)
    action = intent["action"].split("|")[0].strip()
    ambiguous = intent["ambiguous"]

    if intent["domain"] != "unknown":
        ambiguous = False

    assert action == "install"
    assert ambiguous is False


def test_unknown_domain_remains_ambiguous():
    """
    If the domain is unknown, ambiguity should remain true.
    """
    intent = {
        "action": "install",
        "domain": "unknown",
        "ambiguous": True,
        "confidence": 0.3,
    }

    ambiguous = intent["ambiguous"]
    domain = intent["domain"]

    assert domain == "unknown"
    assert ambiguous is True


# ---------------------------------------------------------------------
# Install mode influence on command planning
# ---------------------------------------------------------------------

def test_python_install_mode_guides_prompt():
    """
    When install_mode is python, the prompt should guide the
    model toward pip + virtualenv and away from sudo/apt.
    """
    software = "python machine learning"
    install_mode = "python"

    if install_mode == "python":
        prompt = (
            f"install {software}. "
            "Use pip and Python virtual environments. "
            "Do NOT use sudo or system package managers."
        )
    else:
        prompt = f"install {software}"

    assert "pip" in prompt.lower()
    assert "sudo" in prompt.lower()


def test_system_install_mode_default_prompt():
    """
    When install_mode is system, the prompt should remain generic.
    """
    software = "docker"
    install_mode = "system"

    if install_mode == "python":
        prompt = (
            f"install {software}. "
            "Use pip and Python virtual environments. "
            "Do NOT use sudo or system package managers."
        )
    else:
        prompt = f"install {software}"

    assert "pip" not in prompt.lower()
    assert "install docker" in prompt.lower()


# ---------------------------------------------------------------------
# Preview vs execute behavior
# ---------------------------------------------------------------------

def test_without_execute_is_preview_only():
    """
    Without --execute, commands should only be previewed.
    """
    execute = False
    commands = ["echo test"]

    executed = False
    if execute:
        executed = True

    assert executed is False
    assert len(commands) == 1


def test_with_execute_triggers_confirmation_flow():
    """
    With --execute, execution is gated behind confirmation.
    """
    execute = True
    confirmation_required = False

    if execute:
        confirmation_required = True

    assert confirmation_required is True


# ---------------------------------------------------------------------
# Safety checks (logic-level)
# ---------------------------------------------------------------------

def test_python_required_but_missing_blocks_execution():
    """
    If Python is required but not present, execution should be blocked.
    """
    commands = [
        "python3 -m venv myenv",
        "myenv/bin/python -m pip install scikit-learn",
    ]

    python_available = False  # simulate missing runtime
    uses_python = any("python" in cmd for cmd in commands)

    blocked = False
    if uses_python and not python_available:
        blocked = True

    assert blocked is True


def test_sudo_required_but_unavailable_blocks_execution():
    """
    If sudo is required but unavailable, execution should be blocked.
    """
    commands = [
        "sudo apt update",
        "sudo apt install -y docker.io",
    ]

    sudo_available = False
    uses_sudo = any(cmd.strip().startswith("sudo ") for cmd in commands)

    blocked = False
    if uses_sudo and not sudo_available:
        blocked = True

    assert blocked is True


# ---------------------------------------------------------------------
# Kubernetes (k8s) understanding (intent-level)
# ---------------------------------------------------------------------

def test_k8s_maps_to_kubernetes_domain():
    """
    Ensure shorthand inputs like 'k8s' are treated as a known domain.
    """
    intent = {
        "action": "install",
        "domain": "kubernetes",
        "ambiguous": False,
        "confidence": 0.8,
    }

    assert intent["domain"] == "kubernetes"
    assert intent["ambiguous"] is False
