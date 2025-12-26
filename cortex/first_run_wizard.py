from typing import List  # Import List for type hinting

@dataclass
class WizardState:
    """Tracks the current state of the wizard."""

    current_step: WizardStep = WizardStep.WELCOME
    completed_steps: List[WizardStep] = field(default_factory=list)  # Use List instead of list
    skipped_steps: List[WizardStep] = field(default_factory=list)  # Use List instead of list
    collected_data: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # Other methods remain unchanged