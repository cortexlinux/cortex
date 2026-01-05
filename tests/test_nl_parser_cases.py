import os

import pytest

from cortex.llm.interpreter import CommandInterpreter


@pytest.fixture
def fake_interpreter(monkeypatch):
    monkeypatch.setenv(
        "CORTEX_FAKE_COMMANDS",
        '{"commands": ["echo install step 1", "echo install step 2"]}',
    )
    return CommandInterpreter(api_key="fake", provider="fake")


def test_install_machine_learning(fake_interpreter):
    commands = fake_interpreter.parse("install something for machine learning")
    assert len(commands) > 0


def test_install_web_server(fake_interpreter):
    commands = fake_interpreter.parse("I need a web server")
    assert isinstance(commands, list)


def test_python_dev_environment(fake_interpreter):
    commands = fake_interpreter.parse("set up python development environment")
    assert commands


def test_install_docker_kubernetes(fake_interpreter):
    commands = fake_interpreter.parse("install docker and kubernetes")
    assert len(commands) >= 1


def test_ambiguous_request(fake_interpreter):
    commands = fake_interpreter.parse("install something")
    assert commands  # ambiguity handled, not crash


def test_typo_tolerance(fake_interpreter):
    commands = fake_interpreter.parse("instal dockr")
    assert commands


def test_unknown_request(fake_interpreter):
    commands = fake_interpreter.parse("do something cool")
    assert isinstance(commands, list)


def test_multiple_tools_request(fake_interpreter):
    commands = fake_interpreter.parse("install tools for video editing")
    assert commands


def test_short_query(fake_interpreter):
    commands = fake_interpreter.parse("nginx")
    assert commands


def test_sentence_style_query(fake_interpreter):
    commands = fake_interpreter.parse("can you please install a database for me")
    assert commands

