"""
tools/web_search.py — Lightweight web search via DuckDuckGo Instant Answer API.

No API key required. Uses DuckDuckGo's free JSON endpoint:
    https://api.duckduckgo.com/?q=QUERY&format=json&no_html=1&skip_disambig=1

Falls back to a list of related topics when no direct abstract is available.
"""

import urllib.request
import urllib.parse
import json
import logging
from typing import List, Dict, Any

from tools.base import Tool

logger = logging.getLogger("agent.web_search")

_DDG_URL = "https://api.duckduckgo.com/"
_TIMEOUT = 8  # seconds


class WebSearchTool(Tool):
    """Searches the web using DuckDuckGo's Instant Answer API (no key needed)."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Searches the web via DuckDuckGo and returns a summary of results."

    def execute(self, argument: str) -> str:
        """
        Queries DuckDuckGo Instant Answers for *argument*.

        Args:
            argument: The search query string.

        Returns:
            Markdown-formatted search results, or an error message.
        """
        query = argument.strip()
        if not query:
            return "❌ No search query provided. Usage: `TOOL:web_search:your query here`"

        try:
            params = urllib.parse.urlencode({
                "q":              query,
                "format":         "json",
                "no_html":        "1",
                "skip_disambig":  "1",
                "t":              "interactive-agent",
            })
            url = f"{_DDG_URL}?{params}"

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "InteractiveAgent/2.0 (educational project)"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))

            return self._format_results(query, data)

        except urllib.error.URLError as exc:
            logger.warning(f"Web search network error for '{query}': {exc}")
            return f"❌ **Network error** — could not reach DuckDuckGo: `{exc.reason}`"
        except Exception as exc:
            logger.error(f"Web search unexpected error for '{query}': {exc}", exc_info=True)
            return f"❌ **Search error** — `{exc}`"

    # ── Private ──────────────────────────────────────────

    def _format_results(self, query: str, data: Dict[str, Any]) -> str:
        """Builds a Markdown result block from raw DDG JSON."""
        parts: List[str] = [f"### 🔍 Web Search: *{query}*\n"]

        abstract = data.get("AbstractText", "").strip()
        abstract_url = data.get("AbstractURL", "")
        source = data.get("AbstractSource", "")

        if abstract:
            parts.append(f"{abstract}\n")
            if abstract_url:
                parts.append(f"**Source**: [{source or abstract_url}]({abstract_url})\n")

        # Related topics
        topics = data.get("RelatedTopics", [])
        if topics:
            parts.append("\n**Related:**\n")
            shown = 0
            for topic in topics:
                if shown >= 4:
                    break
                if isinstance(topic, dict) and topic.get("Text"):
                    text = topic["Text"][:160]
                    url  = topic.get("FirstURL", "")
                    link = f" — [link]({url})" if url else ""
                    parts.append(f"- {text}{link}")
                    shown += 1

        # Infobox answer (e.g. calculator-type queries)
        answer = data.get("Answer", "").strip()
        if answer and not abstract:
            parts.append(f"\n**Answer**: {answer}\n")

        if len(parts) == 1:
            parts.append(
                "_No instant answer found. Try a more specific query or ask Gemini directly._"
            )

        return "\n".join(parts)
