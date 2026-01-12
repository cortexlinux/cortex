"""
Tests for agentic tools structure methods.

Tests the _structure_response methods with mocked responses.
"""

from unittest.mock import Mock, patch

import pytest


class TestLessonGeneratorStructure:
    """Tests for LessonGeneratorTool structure methods."""

    @patch("cortex.tutor.tools.agentic.lesson_generator.get_config")
    @patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic")
    def test_structure_response_full(self, mock_llm_class, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = LessonGeneratorTool()

        response = {
            "package_name": "docker",
            "summary": "Docker is a platform.",
            "explanation": "Docker allows...",
            "use_cases": ["Dev", "Prod"],
            "best_practices": ["Use official images"],
            "code_examples": [{"title": "Run", "code": "docker run", "language": "bash"}],
            "tutorial_steps": [{"step_number": 1, "title": "Start", "content": "Begin"}],
            "installation_command": "apt install docker",
            "related_packages": ["podman"],
            "confidence": 0.9,
        }

        result = tool._structure_response(response, "docker")

        assert result["package_name"] == "docker"
        assert result["summary"] == "Docker is a platform."
        assert len(result["use_cases"]) == 2
        assert result["confidence"] == pytest.approx(0.9)

    @patch("cortex.tutor.tools.agentic.lesson_generator.get_config")
    @patch("cortex.tutor.tools.agentic.lesson_generator.ChatAnthropic")
    def test_structure_response_minimal(self, mock_llm_class, mock_config):
        """Test structure_response with minimal response."""
        from cortex.tutor.tools.agentic.lesson_generator import LessonGeneratorTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = LessonGeneratorTool()

        response = {
            "package_name": "test",
            "summary": "Test summary",
        }

        result = tool._structure_response(response, "test")

        assert result["package_name"] == "test"
        assert result["use_cases"] == []
        assert result["best_practices"] == []


class TestExamplesProviderStructure:
    """Tests for ExamplesProviderTool structure methods."""

    @patch("cortex.tutor.tools.agentic.examples_provider.get_config")
    @patch("cortex.tutor.tools.agentic.examples_provider.ChatAnthropic")
    def test_structure_response_full(self, mock_llm_class, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.examples_provider import ExamplesProviderTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )
        mock_llm_class.return_value = Mock()

        tool = ExamplesProviderTool()

        response = {
            "package_name": "git",
            "topic": "branching",
            "examples": [{"title": "Create", "code": "git checkout -b", "language": "bash"}],
            "tips": ["Use descriptive names"],
            "common_mistakes": ["Forgetting to commit"],
            "confidence": 0.95,
        }

        result = tool._structure_response(response, "git", "branching")

        assert result["package_name"] == "git"
        assert result["topic"] == "branching"
        assert len(result["examples"]) == 1


class TestQAHandlerStructure:
    """Tests for QAHandlerTool structure methods."""

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_structure_response_full(self, mock_config):
        """Test structure_response with full response."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        # QAHandlerTool now uses lazy LLM init, so we don't need to mock ChatAnthropic
        # for _structure_response tests (it's not called during instantiation)
        tool = QAHandlerTool()

        response = {
            "question_understood": "What is Docker?",
            "answer": "Docker is a container platform.",
            "explanation": "It allows packaging applications.",
            "code_example": {"code": "docker run", "language": "bash"},
            "related_topics": ["containers", "images"],
            "confidence": 0.9,
        }

        result = tool._structure_response(response, "docker", "What is Docker?")

        assert result["answer"] == "Docker is a container platform."
        assert result["code_example"] is not None

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_structure_response_handles_non_dict(self, mock_config):
        """Test structure_response handles non-dict input."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        tool = QAHandlerTool()

        # Test with non-dict response
        result = tool._structure_response(None, "docker", "What is Docker?")

        assert result["answer"] == "I couldn't generate an answer."
        assert result["package_name"] == "docker"

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_structure_response_handles_invalid_confidence(self, mock_config):
        """Test structure_response handles invalid confidence value."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        tool = QAHandlerTool()

        response = {
            "answer": "Test answer",
            "confidence": "not a number",  # Invalid type
        }

        result = tool._structure_response(response, "docker", "What?")

        # Should default to 0.7
        assert result["confidence"] == pytest.approx(0.7)

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_structure_response_clamps_confidence(self, mock_config):
        """Test structure_response clamps confidence to 0-1 range."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        tool = QAHandlerTool()

        # Test confidence > 1
        response = {"answer": "Test", "confidence": 1.5}
        result = tool._structure_response(response, "docker", "What?")
        assert result["confidence"] == pytest.approx(1.0)

        # Test confidence < 0
        response = {"answer": "Test", "confidence": -0.5}
        result = tool._structure_response(response, "docker", "What?")
        assert result["confidence"] == pytest.approx(0.0)

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_structure_response_handles_string_code_example(self, mock_config):
        """Test structure_response handles code_example as string."""
        from cortex.tutor.tools.agentic.qa_handler import QAHandlerTool

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        tool = QAHandlerTool()

        response = {
            "answer": "Test answer",
            "code_example": "docker run nginx",  # String instead of dict
        }

        result = tool._structure_response(response, "docker", "How to run?")

        assert result["code_example"] is not None
        assert result["code_example"]["code"] == "docker run nginx"
        assert result["code_example"]["language"] == "bash"


class TestConversationHandler:
    """Tests for ConversationHandler."""

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_build_context_empty(self, mock_config):
        """Test context building with empty history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        # ConversationHandler now uses lazy init, no LLM created on __init__
        handler = ConversationHandler("docker")
        handler.history = []

        context = handler._build_context()
        assert "Starting fresh" in context

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_build_context_with_history(self, mock_config):
        """Test context building with history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        handler = ConversationHandler("docker")
        handler.history = [
            {"question": "What is Docker?", "answer": "A platform"},
        ]

        context = handler._build_context()
        assert "What is Docker?" in context

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_clear_history(self, mock_config):
        """Test clearing history."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        handler = ConversationHandler("docker")
        handler.history = [{"question": "test", "answer": "response"}]
        handler.clear_history()

        assert len(handler.history) == 0

    @patch("cortex.tutor.tools.agentic.qa_handler.get_config")
    def test_lazy_qa_tool_init(self, mock_config):
        """Test QA tool is lazily initialized."""
        from cortex.tutor.tools.agentic.qa_handler import ConversationHandler

        mock_config.return_value = Mock(
            anthropic_api_key="test_key",
            model="claude-sonnet-4-20250514",
        )

        handler = ConversationHandler("docker")

        # qa_tool should be None before first ask()
        assert handler.qa_tool is None
