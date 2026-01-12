"""
Tests for TutorAgent methods and graph nodes.

Comprehensive tests for agent functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cortex.tutor.agents.tutor_agent.graph import (
    create_tutor_graph,
    fail_node,
    generate_lesson_node,
    get_tutor_graph,
    load_cache_node,
    plan_node,
    qa_node,
    reflect_node,
    route_after_act,
    route_after_plan,
)
from cortex.tutor.agents.tutor_agent.state import (
    TutorAgentState,
    add_checkpoint,
    add_cost,
    add_error,
    create_initial_state,
    get_package_name,
    get_session_type,
    has_critical_error,
)


class TestTutorAgentMethods:
    """Tests for TutorAgent class methods."""

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_teach_success(self, mock_tracker_class, mock_graph):
        """Test successful teach method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True}
        mock_tracker_class.return_value = mock_tracker

        mock_g = Mock()
        mock_g.invoke.return_value = {
            "output": {
                "validation_passed": True,
                "type": "lesson",
                "content": {"summary": "Docker is..."},
            }
        }
        mock_graph.return_value = mock_g

        agent = TutorAgent(verbose=False)
        result = agent.teach("docker")

        assert result["validation_passed"] is True

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_teach_verbose(self, mock_tracker_class, mock_graph):
        """Test teach with verbose mode."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True}
        mock_tracker_class.return_value = mock_tracker

        mock_g = Mock()
        mock_g.invoke.return_value = {
            "output": {
                "validation_passed": True,
                "type": "lesson",
                "source": "cache",
                "cache_hit": True,
                "cost_gbp": 0.0,
                "cost_saved_gbp": 0.02,
                "confidence": 0.9,
            }
        }
        mock_graph.return_value = mock_g

        with patch("cortex.tutor.agents.tutor_agent.tutor_agent.tutor_print"):
            with patch("cortex.tutor.agents.tutor_agent.tutor_agent.console"):
                agent = TutorAgent(verbose=True)
                result = agent.teach("docker")

        assert result["validation_passed"] is True

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_ask_success(self, mock_tracker_class, mock_graph):
        """Test successful ask method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker_class.return_value = mock_tracker

        mock_g = Mock()
        mock_g.invoke.return_value = {
            "output": {
                "validation_passed": True,
                "type": "qa",
                "content": {"answer": "Docker is a container platform."},
            }
        }
        mock_graph.return_value = mock_g

        agent = TutorAgent()
        result = agent.ask("docker", "What is Docker?")

        assert result["validation_passed"] is True

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_get_profile(self, mock_tracker_class, mock_graph):
        """Test get_profile method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {
            "success": True,
            "profile": {"learning_style": "visual"},
        }
        mock_tracker_class.return_value = mock_tracker

        agent = TutorAgent()
        result = agent.get_profile()

        assert result["success"] is True
        assert "profile" in result

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_update_learning_style(self, mock_tracker_class, mock_graph):
        """Test update_learning_style method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True}
        mock_tracker_class.return_value = mock_tracker

        agent = TutorAgent()
        result = agent.update_learning_style("visual")

        assert result is True

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_mark_completed(self, mock_tracker_class, mock_graph):
        """Test mark_completed method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True}
        mock_tracker_class.return_value = mock_tracker

        agent = TutorAgent()
        result = agent.mark_completed("docker", "basics", 0.9)

        assert result is True

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_reset_progress(self, mock_tracker_class, mock_graph):
        """Test reset_progress method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True, "count": 5}
        mock_tracker_class.return_value = mock_tracker

        agent = TutorAgent()
        result = agent.reset_progress()

        assert result == 5

    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.get_tutor_graph")
    @patch("cortex.tutor.agents.tutor_agent.tutor_agent.ProgressTrackerTool")
    def test_get_packages_studied(self, mock_tracker_class, mock_graph):
        """Test get_packages_studied method."""
        from cortex.tutor.agents.tutor_agent import TutorAgent

        mock_tracker = Mock()
        mock_tracker._run.return_value = {"success": True, "packages": ["docker", "nginx"]}
        mock_tracker_class.return_value = mock_tracker

        agent = TutorAgent()
        result = agent.get_packages_studied()

        assert result == ["docker", "nginx"]


class TestGenerateLessonNode:
    """Tests for generate_lesson_node."""

    @patch("cortex.tutor.agents.tutor_agent.graph.LessonLoaderTool")
    @patch("cortex.tutor.agents.tutor_agent.graph.LessonGeneratorTool")
    def test_generate_lesson_success(self, mock_generator_class, mock_loader_class):
        """Test successful lesson generation."""
        mock_generator = Mock()
        mock_generator._run.return_value = {
            "success": True,
            "lesson": {
                "package_name": "docker",
                "summary": "Docker is a container platform.",
                "explanation": "Docker allows...",
            },
            "cost_gbp": 0.02,
        }
        mock_generator_class.return_value = mock_generator

        mock_loader = Mock()
        mock_loader.cache_lesson.return_value = True
        mock_loader_class.return_value = mock_loader

        state = create_initial_state("docker")
        state["student_profile"] = {"learning_style": "reading"}

        result = generate_lesson_node(state)

        assert result["results"]["type"] == "lesson"
        assert result["results"]["source"] == "generated"

    @patch("cortex.tutor.agents.tutor_agent.graph.LessonGeneratorTool")
    def test_generate_lesson_failure(self, mock_generator_class):
        """Test lesson generation failure."""
        mock_generator = Mock()
        mock_generator._run.return_value = {
            "success": False,
            "error": "API error",
        }
        mock_generator_class.return_value = mock_generator

        state = create_initial_state("docker")
        state["student_profile"] = {}

        result = generate_lesson_node(state)

        assert len(result["errors"]) > 0

    @patch("cortex.tutor.agents.tutor_agent.graph.LessonGeneratorTool")
    def test_generate_lesson_exception(self, mock_generator_class):
        """Test lesson generation with exception."""
        mock_generator_class.side_effect = Exception("Test exception")

        state = create_initial_state("docker")
        state["student_profile"] = {}

        result = generate_lesson_node(state)

        assert len(result["errors"]) > 0


class TestQANode:
    """Tests for qa_node."""

    @patch("cortex.tutor.agents.tutor_agent.graph.QAHandlerTool")
    def test_qa_success(self, mock_qa_class):
        """Test successful Q&A."""
        mock_qa = Mock()
        mock_qa._run.return_value = {
            "success": True,
            "answer": {
                "answer": "Docker is a containerization platform.",
                "explanation": "It allows...",
            },
            "cost_gbp": 0.02,
        }
        mock_qa_class.return_value = mock_qa

        state = create_initial_state("docker", session_type="qa", question="What is Docker?")
        state["student_profile"] = {}

        result = qa_node(state)

        assert result["results"]["type"] == "qa"
        assert result["qa_result"] is not None

    @patch("cortex.tutor.agents.tutor_agent.graph.QAHandlerTool")
    def test_qa_no_question(self, mock_qa_class):
        """Test Q&A without question."""
        state = create_initial_state("docker", session_type="qa")
        # No question provided

        result = qa_node(state)

        assert len(result["errors"]) > 0

    @patch("cortex.tutor.agents.tutor_agent.graph.QAHandlerTool")
    def test_qa_failure(self, mock_qa_class):
        """Test Q&A failure."""
        mock_qa = Mock()
        mock_qa._run.return_value = {
            "success": False,
            "error": "Could not answer",
        }
        mock_qa_class.return_value = mock_qa

        state = create_initial_state("docker", session_type="qa", question="What?")
        state["student_profile"] = {}

        result = qa_node(state)

        assert len(result["errors"]) > 0

    @patch("cortex.tutor.agents.tutor_agent.graph.QAHandlerTool")
    def test_qa_exception(self, mock_qa_class):
        """Test Q&A with exception."""
        mock_qa_class.side_effect = Exception("Test error")

        state = create_initial_state("docker", session_type="qa", question="What?")
        state["student_profile"] = {}

        result = qa_node(state)

        assert len(result["errors"]) > 0


class TestReflectNode:
    """Tests for reflect_node."""

    def test_reflect_with_errors(self):
        """Test reflect with non-critical errors."""
        state = create_initial_state("docker")
        state["results"] = {"type": "lesson", "content": {"summary": "Test"}, "source": "cache"}
        add_error(state, "test", "Minor error", recoverable=True)

        result = reflect_node(state)

        assert result["output"]["validation_passed"] is True
        assert result["output"]["confidence"] < 1.0

    def test_reflect_with_critical_error(self):
        """Test reflect with critical error."""
        state = create_initial_state("docker")
        state["results"] = {"type": "lesson", "content": {"summary": "Test"}}
        add_error(state, "test", "Critical error", recoverable=False)

        result = reflect_node(state)

        assert result["output"]["validation_passed"] is False


class TestFailNode:
    """Tests for fail_node."""

    def test_fail_node_with_errors(self):
        """Test fail node with multiple errors."""
        state = create_initial_state("docker")
        add_error(state, "test1", "Error 1")
        add_error(state, "test2", "Error 2")
        state["cost_gbp"] = 0.01

        result = fail_node(state)

        assert result["output"]["type"] == "error"
        assert result["output"]["validation_passed"] is False
        assert len(result["output"]["validation_errors"]) == 2


class TestRouting:
    """Tests for routing functions."""

    def test_route_after_plan_fail_on_error(self):
        """Test routing to fail on critical error."""
        state = create_initial_state("docker")
        add_error(state, "test", "Critical", recoverable=False)

        route = route_after_plan(state)
        assert route == "fail"

    def test_route_after_act_fail_no_results(self):
        """Test routing to fail when no results."""
        state = create_initial_state("docker")
        state["results"] = {}

        route = route_after_act(state)
        assert route == "fail"

    def test_route_after_act_success(self):
        """Test routing to reflect on success."""
        state = create_initial_state("docker")
        state["results"] = {"type": "lesson", "content": {}}

        route = route_after_act(state)
        assert route == "reflect"


class TestGraphCreation:
    """Tests for graph creation."""

    def test_create_tutor_graph(self):
        """Test graph is created successfully."""
        graph = create_tutor_graph()
        assert graph is not None

    def test_get_tutor_graph_singleton(self):
        """Test get_tutor_graph returns singleton."""
        graph1 = get_tutor_graph()
        graph2 = get_tutor_graph()
        assert graph1 is graph2


class TestStateHelpers:
    """Tests for state helper functions."""

    def test_add_checkpoint(self):
        """Test add_checkpoint adds to list."""
        state = create_initial_state("docker")
        add_checkpoint(state, "test", "ok", "Test checkpoint")

        assert len(state["checkpoints"]) == 1
        assert state["checkpoints"][0]["name"] == "test"
        assert state["checkpoints"][0]["status"] == "ok"

    def test_add_cost(self):
        """Test add_cost accumulates."""
        state = create_initial_state("docker")
        add_cost(state, 0.01)
        add_cost(state, 0.02)
        add_cost(state, 0.005)

        assert abs(state["cost_gbp"] - 0.035) < 0.0001

    def test_get_session_type_default(self):
        """Test default session type."""
        state = create_initial_state("docker")
        assert get_session_type(state) == "lesson"

    def test_get_package_name(self):
        """Test getting package name."""
        state = create_initial_state("nginx")
        assert get_package_name(state) == "nginx"
