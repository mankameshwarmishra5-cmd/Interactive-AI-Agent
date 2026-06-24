"""
tools/base.py — Abstract base class for all agent tools.

Every concrete tool must implement:
    name        : str  — unique identifier used in TOOL:name:arg syntax
    description : str  — human-readable description shown in prompts
    execute()   : callable(argument: str) -> str
"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """Abstract base class for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique snake_case identifier for this tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this tool does."""
        ...

    @abstractmethod
    def execute(self, argument: str) -> str:
        """
        Executes the tool with the given *argument* string.

        Args:
            argument: Raw string argument from the agent or user.

        Returns:
            A plain-text or Markdown result string.

        Raises:
            ValueError: If the argument is invalid for this tool.
            Exception:  Any tool-specific error.
        """
        ...

    def __repr__(self) -> str:
        return f"<Tool name={self.name!r}>"
