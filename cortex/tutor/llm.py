"""
LLM functions for the Intelligent Tutor.

Uses Anthropic API with structured outputs via tool use.
"""

import logging
import threading
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from cortex.tutor.config import get_config
from cortex.tutor.contracts import LessonResponse, QAResponse

logger = logging.getLogger(__name__)

# Thread-safe client initialization
_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()

T = TypeVar("T", bound=BaseModel)


def get_client() -> anthropic.Anthropic:
    """Get or create the Anthropic client instance (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                config = get_config()
                if not config.anthropic_api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable is required")
                _client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    return _client


# Cost per 1M tokens for Claude Sonnet
COST_INPUT_PER_1M = 3.0
COST_OUTPUT_PER_1M = 15.0


def _calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD."""
    input_cost = (input_tokens / 1_000_000) * COST_INPUT_PER_1M
    output_cost = (output_tokens / 1_000_000) * COST_OUTPUT_PER_1M
    return input_cost + output_cost


def _error_response(error: str, result_key: str = "result") -> dict:
    """Create a consistent error response structure."""
    return {"success": False, "error": error, result_key: None}


def _create_tool_from_model(name: str, description: str, model: type[T]) -> dict:
    """Create an Anthropic tool definition from a Pydantic model."""
    schema = model.model_json_schema()
    # Remove title and description from schema (not needed in input_schema)
    schema.pop("title", None)
    schema.pop("description", None)
    return {
        "name": name,
        "description": description,
        "input_schema": schema,
    }


def _call_with_structured_output(
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
    tool_name: str,
    tool_description: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> tuple[T, float]:
    """
    Call Anthropic API with structured output using tool use.

    Returns:
        Tuple of (parsed response model, cost in USD)

    Raises:
        ValueError: If response is empty or no tool use found.
    """
    client = get_client()
    config = get_config()
    tool = _create_tool_from_model(tool_name, tool_description, response_model)

    response = client.messages.create(
        model=config.model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Handle empty or None response content
    if not response.content:
        raise ValueError(f"Empty response from API for {tool_name}")

    # Extract tool use result
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            result = response_model.model_validate(block.input)
            cost = _calculate_cost(response.usage.input_tokens, response.usage.output_tokens)
            return result, cost

    raise ValueError(f"No tool use response found for {tool_name}")


# ==============================================================================
# Lesson Generator
# ==============================================================================

LESSON_SYSTEM_PROMPT = """You are a Lesson Content Generator for technical education.

Your role:
- Create educational content about software packages and tools
- Provide clear explanations, practical use cases, best practices
- Include safe, working code examples
- Structure content for the student's level and learning style

CRITICAL RULES:
- NEVER invent command flags - only use flags you're certain exist
- NEVER fabricate URLs - suggest "official documentation" instead
- NEVER claim specific versions - use "recent versions"
- Express uncertainty via the confidence score (0.5-1.0)

Confidence guidelines:
- 0.9-1.0: Well-known packages (docker, git, nginx)
- 0.7-0.9: Less common but documented packages
- 0.5-0.7: Uncertain or niche packages"""


def _build_lesson_user_prompt(
    package_name: str,
    student_level: str,
    learning_style: str,
    skip_areas: list[str] | None,
) -> str:
    """Build user prompt for lesson generation."""
    skip_text = ", ".join(skip_areas) if skip_areas else "none"

    return f"""Generate a comprehensive lesson for: {package_name}

Student Profile:
- Level: {student_level}
- Learning Style: {learning_style}
- Skip Topics: {skip_text}

Guidelines:
1. ANALYZE the package category (system tool, library, service)
2. STRUCTURE content for {student_level} level
3. ADAPT to {learning_style} learning style
4. Include practical code examples
5. Set confidence based on your knowledge certainty"""


def generate_lesson(
    package_name: str,
    student_level: str = "beginner",
    learning_style: str = "reading",
    skip_areas: list[str] | None = None,
) -> dict:
    """
    Generate a lesson for a package using structured outputs.

    Args:
        package_name: Name of the package to teach.
        student_level: Student level (beginner, intermediate, advanced).
        learning_style: Learning style (visual, reading, hands-on).
        skip_areas: Topics to skip (already mastered).

    Returns:
        Dict with success status, lesson content, and cost.
    """
    user_prompt = _build_lesson_user_prompt(package_name, student_level, learning_style, skip_areas)

    try:
        lesson, cost = _call_with_structured_output(
            system_prompt=LESSON_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=LessonResponse,
            tool_name="generate_lesson",
            tool_description="Generate structured lesson content for a software package",
            temperature=0.3,
            max_tokens=4096,
        )
        return {"success": True, "lesson": lesson.model_dump(), "cost_usd": cost}

    except ValidationError as e:
        logger.error("Failed to validate lesson response: %s", e)
        return _error_response(str(e), "lesson")
    except Exception as e:
        logger.error("Failed to generate lesson: %s", e)
        return _error_response(str(e), "lesson")


# ==============================================================================
# Q&A Handler
# ==============================================================================

QA_SYSTEM_PROMPT = """You are a Q&A Handler for technical education.

Your role:
- Answer questions about software packages clearly
- Provide helpful code examples when relevant
- Suggest related topics for further learning
- Be honest about uncertainty

CRITICAL RULES:
- NEVER fabricate features - only describe what you're confident exists
- NEVER invent benchmarks or statistics
- NEVER generate fake URLs
- Express uncertainty via the confidence score (0.5-1.0)

Confidence guidelines:
- 0.9-1.0: Common knowledge, confident answer
- 0.7-0.9: Likely correct, recommend verification
- 0.5-0.7: Uncertain, suggest official documentation"""


def _build_qa_user_prompt(
    package_name: str,
    question: str,
    context: str | None,
) -> str:
    """Build user prompt for Q&A."""
    context_text = f"\nContext: {context}" if context else ""

    return f"""Package: {package_name}
Question: {question}{context_text}

Provide a clear, accurate answer. Include a code example if helpful."""


def answer_question(
    package_name: str,
    question: str,
    context: str | None = None,
) -> dict:
    """
    Answer a question about a package using structured outputs.

    Args:
        package_name: Package context for the question.
        question: The user's question.
        context: Optional additional context.

    Returns:
        Dict with success status, answer content, and cost.
    """
    user_prompt = _build_qa_user_prompt(package_name, question, context)

    try:
        answer, cost = _call_with_structured_output(
            system_prompt=QA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=QAResponse,
            tool_name="answer_question",
            tool_description="Provide a structured answer to a question about a package",
            temperature=0.5,
            max_tokens=2048,
        )
        return {"success": True, "answer": answer.model_dump(), "cost_usd": cost}

    except ValidationError as e:
        logger.error("Failed to validate answer response: %s", e)
        return _error_response(str(e), "answer")
    except Exception as e:
        logger.error("Failed to answer question: %s", e)
        return _error_response(str(e), "answer")
