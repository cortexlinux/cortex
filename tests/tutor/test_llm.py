"""Tests for cortex.tutor.llm module."""

from unittest.mock import MagicMock, patch

import pytest


class TestGetClient:
    """Tests for get_client function."""

    def test_get_client_creates_singleton(self):
        """Test that get_client creates a singleton instance."""
        from cortex.tutor import llm

        # Reset the global client
        llm._client = None

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(llm.anthropic, "Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                client1 = llm.get_client()
                client2 = llm.get_client()

                # Should only create one instance
                assert mock_anthropic.call_count == 1
                assert client1 is client2

        # Clean up
        llm._client = None

    def test_get_client_raises_without_api_key(self):
        """Test that get_client raises error without API key."""
        from cortex.tutor import llm
        from cortex.tutor.config import reset_config

        llm._client = None
        reset_config()

        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            import os

            os.environ.pop("ANTHROPIC_API_KEY", None)

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                llm.get_client()

        llm._client = None
        reset_config()


class TestCalculateCost:
    """Tests for _calculate_cost function."""

    def test_calculate_cost(self):
        """Test cost calculation."""
        from cortex.tutor.llm import _calculate_cost

        # 1M input tokens at $3/1M = $3
        # 1M output tokens at $15/1M = $15
        cost = _calculate_cost(1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)

    def test_calculate_cost_small(self):
        """Test cost calculation for small token counts."""
        from cortex.tutor.llm import _calculate_cost

        # 1000 input tokens, 500 output tokens
        cost = _calculate_cost(1000, 500)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected)


class TestCreateToolFromModel:
    """Tests for _create_tool_from_model function."""

    def test_create_tool_from_model(self):
        """Test tool creation from Pydantic model."""
        from cortex.tutor.contracts import QAResponse
        from cortex.tutor.llm import _create_tool_from_model

        tool = _create_tool_from_model("test_tool", "A test tool description", QAResponse)

        assert tool["name"] == "test_tool"
        assert tool["description"] == "A test tool description"
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]


class TestGenerateLesson:
    """Tests for generate_lesson function."""

    def test_generate_lesson_success(self):
        """Test successful lesson generation."""
        from cortex.tutor import llm

        # Create a proper mock for the tool_use block
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "generate_lesson"
        tool_block.input = {
            "summary": "Test summary",
            "explanation": "Test explanation",
            "use_cases": ["use case 1"],
            "best_practices": ["practice 1"],
            "code_examples": [],
            "tutorial_steps": [],
            "installation_command": "apt install test",
            "related_packages": [],
            "confidence": 0.9,
        }

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = llm.generate_lesson("docker")

            assert result["success"] is True
            assert result["lesson"]["summary"] == "Test summary"
            assert result["lesson"]["confidence"] == pytest.approx(0.9)

    def test_generate_lesson_with_options(self):
        """Test lesson generation with custom options."""
        from cortex.tutor import llm

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "generate_lesson"
        tool_block.input = {
            "summary": "Advanced lesson",
            "explanation": "Advanced explanation",
            "use_cases": [],
            "best_practices": [],
            "code_examples": [],
            "tutorial_steps": [],
            "installation_command": "apt install nginx",
            "related_packages": [],
            "confidence": 0.85,
        }

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = llm.generate_lesson(
                "nginx",
                student_level="advanced",
                learning_style="hands-on",
                skip_areas=["basics", "intro"],
            )

            assert result["success"] is True
            # Verify the call was made with correct parameters
            call_args = mock_client.messages.create.call_args
            assert "nginx" in call_args[1]["messages"][0]["content"]

    def test_generate_lesson_api_error(self):
        """Test lesson generation with API error."""
        from cortex.tutor import llm

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API error")
            mock_get_client.return_value = mock_client

            result = llm.generate_lesson("docker")

            assert result["success"] is False
            assert "API error" in result["error"]


class TestAnswerQuestion:
    """Tests for answer_question function."""

    def test_answer_question_success(self):
        """Test successful question answering."""
        from cortex.tutor import llm

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "answer_question"
        tool_block.input = {
            "answer": "Docker is a containerization platform",
            "code_example": {"code": "docker ps", "language": "bash"},
            "related_topics": ["containers", "images"],
            "confidence": 0.95,
        }

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 100

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = llm.answer_question("docker", "What is Docker?")

            assert result["success"] is True
            assert "containerization" in result["answer"]["answer"]
            assert result["answer"]["confidence"] == pytest.approx(0.95)

    def test_answer_question_with_context(self):
        """Test question answering with context."""
        from cortex.tutor import llm

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "answer_question"
        tool_block.input = {
            "answer": "test",
            "code_example": None,
            "related_topics": [],
            "confidence": 0.9,
        }

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 100

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = llm.answer_question(
                "docker",
                "How do I build?",
                context="Learning about Dockerfiles",
            )

            assert result["success"] is True
            # Verify context is in the prompt
            call_args = mock_client.messages.create.call_args
            user_msg = call_args[1]["messages"][0]["content"]
            assert "Learning about Dockerfiles" in user_msg

    def test_answer_question_api_error(self):
        """Test question answering with API error."""
        from cortex.tutor import llm

        with patch.object(llm, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = RuntimeError("Connection failed")
            mock_get_client.return_value = mock_client

            result = llm.answer_question("docker", "What is Docker?")

            assert result["success"] is False
            assert "Connection failed" in result["error"]
