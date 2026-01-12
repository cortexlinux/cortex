"""
Tutor Agent State - TypedDict for LangGraph workflow state.

Defines the state schema that flows through the Plan→Act→Reflect workflow.
"""

from typing import Any, TypedDict


class StudentProfileState(TypedDict, total=False):
    """Student profile state within the agent."""

    learning_style: str
    mastered_concepts: list[str]
    weak_concepts: list[str]
    last_session: str | None


class LessonContentState(TypedDict, total=False):
    """Lesson content state."""

    package_name: str
    summary: str
    explanation: str
    use_cases: list[str]
    best_practices: list[str]
    code_examples: list[dict[str, Any]]
    tutorial_steps: list[dict[str, Any]]
    installation_command: str
    confidence: float


class PlanState(TypedDict, total=False):
    """Plan phase output state."""

    strategy: str  # "use_cache", "generate_full", "generate_quick", "qa_mode"
    cached_data: dict[str, Any] | None
    estimated_cost: float
    reasoning: str


class ErrorState(TypedDict):
    """Error entry in state."""

    node: str
    error: str
    recoverable: bool


class TutorAgentState(TypedDict, total=False):
    """
    Complete state for the Tutor Agent workflow.

    This state flows through all nodes in the LangGraph:
    Plan → Act → Reflect → Output

    Attributes:
        input: User input and request parameters
        force_fresh: Skip cache and generate fresh content
        plan: Output from the PLAN phase
        student_profile: Student's learning profile
        lesson_content: Generated or cached lesson content
        qa_result: Result from Q&A if in qa_mode
        results: Combined results from ACT phase
        errors: List of errors encountered
        checkpoints: Monitoring checkpoints
        cost_gbp: Total cost accumulated
        cache_hit: Whether cache was used
        replan_count: Number of replanning attempts
        output: Final output to return
    """

    # Input
    input: dict[str, Any]
    force_fresh: bool

    # PLAN phase
    plan: PlanState

    # Context
    student_profile: StudentProfileState

    # ACT phase outputs
    lesson_content: LessonContentState
    qa_result: dict[str, Any] | None
    examples_result: dict[str, Any] | None

    # Combined results
    results: dict[str, Any]

    # Errors and monitoring
    errors: list[ErrorState]
    checkpoints: list[dict[str, Any]]

    # Costs
    cost_gbp: float
    cost_saved_gbp: float

    # Flags
    cache_hit: bool
    replan_count: int

    # Final output
    output: dict[str, Any] | None


def create_initial_state(
    package_name: str,
    session_type: str = "lesson",
    question: str | None = None,
    force_fresh: bool = False,
) -> TutorAgentState:
    """
    Create initial state for a tutor session.

    Args:
        package_name: Package to teach.
        session_type: Type of session (lesson, qa, tutorial, quiz).
        question: User question for Q&A mode.
        force_fresh: Skip cache.

    Returns:
        Initial TutorAgentState.
    """
    return TutorAgentState(
        input={
            "package_name": package_name,
            "session_type": session_type,
            "question": question,
        },
        force_fresh=force_fresh,
        plan={},
        student_profile={
            "learning_style": "reading",
            "mastered_concepts": [],
            "weak_concepts": [],
            "last_session": None,
        },
        lesson_content={},
        qa_result=None,
        examples_result=None,
        results={},
        errors=[],
        checkpoints=[],
        cost_gbp=0.0,
        cost_saved_gbp=0.0,
        cache_hit=False,
        replan_count=0,
        output=None,
    )


def add_error(state: TutorAgentState, node: str, error: str, recoverable: bool = True) -> None:
    """
    Add an error to the state.

    Args:
        state: Current state.
        node: Node where error occurred.
        error: Error message.
        recoverable: Whether error is recoverable.
    """
    if "errors" not in state:
        state["errors"] = []
    state["errors"].append(
        {
            "node": node,
            "error": error,
            "recoverable": recoverable,
        }
    )


def add_checkpoint(state: TutorAgentState, name: str, status: str, details: str = "") -> None:
    """
    Add a monitoring checkpoint to the state.

    Args:
        state: Current state.
        name: Checkpoint name.
        status: Status (ok, warning, error).
        details: Additional details.
    """
    if "checkpoints" not in state:
        state["checkpoints"] = []
    state["checkpoints"].append(
        {
            "name": name,
            "status": status,
            "details": details,
        }
    )


def add_cost(state: TutorAgentState, cost: float) -> None:
    """
    Add cost to the state.

    Args:
        state: Current state.
        cost: Cost in GBP to add.
    """
    current = state.get("cost_gbp", 0.0)
    state["cost_gbp"] = current + cost


def has_critical_error(state: TutorAgentState) -> bool:
    """
    Check if state has any non-recoverable errors.

    Args:
        state: Current state.

    Returns:
        True if there are critical errors.
    """
    errors = state.get("errors", [])
    return any(not e.get("recoverable", True) for e in errors)


def get_session_type(state: TutorAgentState) -> str:
    """
    Get the session type from state.

    Args:
        state: Current state.

    Returns:
        Session type string.
    """
    return state.get("input", {}).get("session_type", "lesson")


def get_package_name(state: TutorAgentState) -> str:
    """
    Get the package name from state.

    Args:
        state: Current state.

    Returns:
        Package name string.
    """
    return state.get("input", {}).get("package_name", "")
