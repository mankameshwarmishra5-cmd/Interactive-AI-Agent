"""
tools/current_time.py — Returns the current date and time in a formatted string.
"""

from datetime import datetime, timezone

from tools.base import Tool


class CurrentTimeTool(Tool):
    """Returns the current local date, time, and UTC offset."""

    @property
    def name(self) -> str:
        return "current_time"

    @property
    def description(self) -> str:
        return "Returns the current date and time in multiple formats."

    def execute(self, argument: str) -> str:
        """
        Returns a formatted current-time response.

        Args:
            argument: Ignored — the tool always returns the current time.

        Returns:
            Markdown-formatted date/time information.
        """
        now_local = datetime.now().astimezone()
        now_utc   = datetime.now(timezone.utc)

        local_str = now_local.strftime("%A, %B %d %Y at %I:%M:%S %p %Z")
        utc_str   = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        tz_name   = now_local.strftime("%Z")
        utc_off   = now_local.strftime("%z")

        return (
            f"🕐 **Current Time**\n\n"
            f"- **Local**: {local_str}\n"
            f"- **UTC**:   {utc_str}\n"
            f"- **Timezone**: {tz_name} (UTC{utc_off[:3]}:{utc_off[3:]})\n"
        )
