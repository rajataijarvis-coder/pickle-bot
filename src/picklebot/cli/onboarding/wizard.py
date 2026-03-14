# src/picklebot/cli/onboarding/wizard.py
"""Onboarding wizard orchestrator."""

from importlib.resources import files
from pathlib import Path

from rich.console import Console

from picklebot.cli.onboarding.steps import (
    BaseStep,
    CheckWorkspaceStep,
    ConfigureExtraFunctionalityStep,
    ConfigureLLMStep,
    ConfigureChannelStep,
    CopyDefaultAssetsStep,
    SaveConfigStep,
    SetupWorkspaceStep,
)


def _get_default_workspace() -> Path:
    """Get default workspace path, supporting both dev and installed modes."""
    # Try installed mode first (bundled in package)
    bundled = Path(str(files("picklebot").joinpath("default_workspace")))
    if bundled.exists():
        return bundled
    # Fall back to development mode (relative to source)
    return Path(__file__).parent.parent.parent.parent.parent / "default_workspace"


class OnboardingWizard:
    """Guides users through initial configuration."""

    DEFAULT_WORKSPACE = _get_default_workspace()

    STEPS: list[type[BaseStep]] = [
        CheckWorkspaceStep,
        SetupWorkspaceStep,
        ConfigureLLMStep,
        ConfigureExtraFunctionalityStep,
        ConfigureChannelStep,
        CopyDefaultAssetsStep,
        SaveConfigStep,
    ]

    def __init__(self, workspace: Path | None = None):
        self.workspace = workspace or Path.home() / ".pickle-bot"

    def run(self) -> bool:
        """Run all onboarding steps. Returns True if successful."""
        console = Console()
        state: dict = {}

        console.print("\n[bold cyan]Welcome to Pickle-Bot![/bold cyan]")
        console.print("Let's set up your configuration.\n")

        for step_cls in self.STEPS:
            step = step_cls(self.workspace, console, self.DEFAULT_WORKSPACE)
            if not step.run(state):
                console.print("[yellow]Onboarding cancelled.[/yellow]")
                return False

        console.print("\n[green]Configuration saved![/green]")
        console.print(f"Config file: {self.workspace / 'config.user.yaml'}")
        console.print("Edit this file to make changes.\n")
        return True
