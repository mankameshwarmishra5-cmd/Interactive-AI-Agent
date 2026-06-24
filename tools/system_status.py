"""
tools/system_status.py — Reports the agent's current operational status.

Takes a reference to the InteractiveAgent at construction time so it can
read live status fields without circular imports.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from tools.base import Tool

if TYPE_CHECKING:
    from agent import InteractiveAgent


class SystemStatusTool(Tool):
    """Returns a live system/agent status report."""

    def __init__(self, agent: "InteractiveAgent") -> None:
        self._agent = agent

    @property
    def name(self) -> str:
        return "system_status"

    @property
    def description(self) -> str:
        return "Reports current agent status: Gemini mode, session info, memory usage."

    def execute(self, argument: str) -> str:
        """
        Generates a Markdown status report from the live agent state.

        Args:
            argument: Ignored.

        Returns:
            Markdown-formatted status table.
        """
        agent = self._agent

        history_count = len(agent.history)
        summary_blurb = (
            f"Yes ({len(agent.conversation_summary)} chars)"
            if getattr(agent, "conversation_summary", "")
            else "No"
        )

        uptime_sec = int(agent.get_uptime())
        h, rem = divmod(uptime_sec, 3600)
        m, s   = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

        return (
            "### 🖥️ System Status\n\n"
            f"| Property | Value |\n"
            f"|---|---|\n"
            f"| **Gemini Status** | `{agent.gemini_status.value}` |\n"
            f"| **Session ID** | `{agent.session_id}` |\n"
            f"| **Messages in Memory** | {history_count} / {agent.MAX_HISTORY} |\n"
            f"| **Conversation Summary** | {summary_blurb} |\n"
            f"| **Agent Uptime** | {uptime_str} |\n"
            f"| **Tools Available** | {', '.join(f'`{t}`' for t in agent.tools)} |\n"
        )
