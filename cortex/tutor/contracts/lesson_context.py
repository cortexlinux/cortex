"""
Lesson Context - Pydantic contract for lesson generation output.

Defines the structured output schema for lesson content.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CodeExample(BaseModel):
    """A code example with description."""

    title: str = Field(..., description="Title of the code example")
    code: str = Field(..., description="The actual code snippet")
    language: str = Field(
        default="bash", description="Programming language for syntax highlighting"
    )
    description: str = Field(..., description="Explanation of what the code does")


class TutorialStep(BaseModel):
    """A step in a tutorial sequence."""

    step_number: int = Field(..., ge=1, description="Step number in sequence")
    title: str = Field(..., description="Brief title for this step")
    content: str = Field(..., description="Detailed instruction for this step")
    code: Optional[str] = Field(default=None, description="Optional code for this step")
    expected_output: Optional[str] = Field(
        default=None, description="Expected output if code is executed"
    )


class LessonContext(BaseModel):
    """
    Output contract for lesson generation.

    Contains all the content generated for a package lesson including
    explanations, best practices, code examples, and tutorials.
    """

    # Core content
    package_name: str = Field(..., description="Name of the package being taught")
    summary: str = Field(
        ...,
        description="Brief 1-2 sentence summary of what the package does",
        max_length=500,
    )
    explanation: str = Field(
        ...,
        description="Detailed explanation of the package functionality",
        max_length=5000,
    )
    use_cases: List[str] = Field(
        default_factory=list,
        description="Common use cases for this package",
        max_length=10,
    )
    best_practices: List[str] = Field(
        default_factory=list,
        description="Best practices when using this package",
        max_length=10,
    )
    code_examples: List[CodeExample] = Field(
        default_factory=list,
        description="Code examples demonstrating package usage",
        max_length=5,
    )
    tutorial_steps: List[TutorialStep] = Field(
        default_factory=list,
        description="Step-by-step tutorial for hands-on learning",
        max_length=10,
    )

    # Package metadata
    installation_command: str = Field(
        ..., description="Command to install the package (apt, pip, etc.)"
    )
    official_docs_url: Optional[str] = Field(
        default=None, description="URL to official documentation"
    )
    related_packages: List[str] = Field(
        default_factory=list,
        description="Related packages the user might want to learn",
        max_length=5,
    )

    # Metadata
    confidence: float = Field(
        ...,
        description="Confidence score (0-1) based on knowledge quality",
        ge=0.0,
        le=1.0,
    )
    cached: bool = Field(default=False, description="Whether result came from cache")
    cost_gbp: float = Field(default=0.0, description="Cost for LLM calls", ge=0.0)
    generated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of generation (UTC)"
    )

    def to_json(self) -> str:
        """Serialize to JSON for caching."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "LessonContext":
        """Deserialize from JSON cache."""
        return cls.model_validate_json(json_str)

    def get_total_steps(self) -> int:
        """Get total number of tutorial steps."""
        return len(self.tutorial_steps)

    def get_practice_count(self) -> int:
        """Get count of best practices."""
        return len(self.best_practices)

    def to_display_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for display purposes."""
        return {
            "package": self.package_name,
            "summary": self.summary,
            "explanation": self.explanation,
            "use_cases": self.use_cases,
            "best_practices": self.best_practices,
            "examples_count": len(self.code_examples),
            "tutorial_steps_count": len(self.tutorial_steps),
            "installation": self.installation_command,
            "confidence": f"{self.confidence:.0%}",
        }


class LessonPlanOutput(BaseModel):
    """Output from the PLAN phase for lesson generation."""

    strategy: Literal["use_cache", "generate_full", "generate_quick"] = Field(
        ..., description="Strategy chosen for lesson generation"
    )
    cached_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Cached lesson data if strategy is use_cache"
    )
    estimated_cost: float = Field(
        default=0.0, description="Estimated cost for this strategy", ge=0.0
    )
    reasoning: str = Field(..., description="Explanation for why this strategy was chosen")


class LessonReflectionOutput(BaseModel):
    """Output from the REFLECT phase for lesson validation."""

    confidence: float = Field(
        ...,
        description="Overall confidence in the lesson quality",
        ge=0.0,
        le=1.0,
    )
    quality_score: float = Field(
        ...,
        description="Quality score based on completeness and accuracy",
        ge=0.0,
        le=1.0,
    )
    insights: List[str] = Field(
        default_factory=list,
        description="Key insights about the generated lesson",
    )
    improvements: List[str] = Field(
        default_factory=list,
        description="Suggested improvements for future iterations",
    )
    validation_passed: bool = Field(
        ..., description="Whether the lesson passed all validation checks"
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="List of validation errors if any",
    )
