"""
agent.py - InteractiveAgent with Gemini 2.5 Flash integration.

Phases covered:
    Phase 1 — Stability:   GeminiStatus enum, classified error handling,
                            clean user messages, fix clear_history bug.
    Phase 2 — Memory:      100-message limit, conversation summarisation.
    Phase 3 — Tool System: ToolRegistry, TOOL:name:arg dispatch.
    Phase 4 — Performance: Retry logic with backoff, request timeout.
    Phase 8 — Quality:     Full type hints and docstrings.
"""


from __future__ import annotations

import os
import re
import time
import random
import logging
import logging.handlers
from enum import Enum
from typing import Dict, List, Optional

from dotenv import load_dotenv

from database import (
    save_message,
    load_history_limited,
    clear_history as db_clear_history,
)

# ──────────────────────────────────────────────────────────
#  Bootstrap — env + logging
# ──────────────────────────────────────────────────────────
load_dotenv()
print("API KEY FOUND:", bool(os.getenv("GEMINI_API_KEY")))
print("API KEY PREFIX:", os.getenv("GEMINI_API_KEY", "")[:8])
os.makedirs("logs", exist_ok=True)

_log_handler = logging.handlers.RotatingFileHandler(
    "logs/agent.log",
    maxBytes=5 * 1024 * 1024,   # 5 MB per file
    backupCount=3,
    encoding="utf-8",
)
_log_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
)

logger = logging.getLogger("agent")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    logger.addHandler(_log_handler)
    _console = logging.StreamHandler()
    _console.setLevel(logging.WARNING)
    _console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_console)

# ──────────────────────────────────────────────────────────
#  Optional Google GenAI SDK import
# ──────────────────────────────────────────────────────────
GENAI_AVAILABLE: bool = False
genai        = None
types        = None
APIError     = None

try:
    from google import genai as _genai
    from google.genai import types as _types
    from google.genai.errors import APIError as _APIError
    genai        = _genai
    types        = _types
    APIError     = _APIError
    GENAI_AVAILABLE = True
    logger.info("Google GenAI SDK loaded successfully.")
except ImportError:
    logger.warning("google-genai package not installed — running in simulation mode.")


# ──────────────────────────────────────────────────────────
#  Gemini Status Enum
# ──────────────────────────────────────────────────────────
class GeminiStatus(str, Enum):
    """
    Operational state of the Gemini connection.

    Values:
        LIVE            — Gemini API is responding normally.
        FALLBACK        — Transient error; using simulation this turn.
        QUOTA_EXCEEDED  — HTTP 429 / RESOURCE_EXHAUSTED received.
        API_KEY_MISSING — Key absent or rejected by Google.
        SDK_MISSING     — google-genai package not installed.
        INITIALIZING    — Agent has just been constructed.
    """
    LIVE            = "live"
    FALLBACK        = "fallback"
    QUOTA_EXCEEDED  = "quota_exceeded"
    API_KEY_MISSING = "api_key_missing"
    SDK_MISSING     = "sdk_missing"
    INITIALIZING    = "initializing"


# ──────────────────────────────────────────────────────────
#  InteractiveAgent
# ──────────────────────────────────────────────────────────
class InteractiveAgent:
    """
    Manages a single chat session against Gemini 2.5 Flash (or simulation).

    Architecture:
        - On init, tries to connect to Gemini; sets gemini_status accordingly.
        - send_message() routes to Gemini or simulation based on status.
        - Errors are classified into GeminiStatus variants and shown as
          friendly Markdown — raw exceptions are never surfaced to users.
        - On errors, the agent falls back to simulation for that turn rather
          than crashing.
        - Tools are invoked when Gemini emits a TOOL:name:arg directive.
        - Memory is capped at MAX_HISTORY; older messages are auto-summarised.

    Attributes:
        session_id:           Current session identifier.
        gemini_status:        Current GeminiStatus value.
        history:              In-memory list of {role, text} dicts.
        conversation_summary: Compressed summary of older messages.
        tools:                Dict[tool_name, Tool] registry.
    """

    MAX_HISTORY:     int   = 100   # Max messages kept in memory
    SUMMARY_TRIGGER: int   = 80    # Summarise when history exceeds this
    SUMMARY_KEEP:    int   = 40    # Retain this many recent msgs after summary
    MAX_RETRIES:     int   = 2     # Retry attempts on transient network errors
    RETRY_DELAY:     float = 1.0   # Seconds between retries
    REQUEST_TIMEOUT: int   = 30    # Gemini call timeout (seconds)

    # ── Construction ─────────────────────────────────────

    def __init__(self, system_instruction: Optional[str] = None) -> None:
        self.api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.system_instruction: str = system_instruction or (
            "You are a helpful, creative, and intelligent AI companion. "
            "Keep responses concise, informative, and beautifully formatted using Markdown. "
            "You have access to tools: calculator, current_time, system_status, web_search. "
            "When the user asks for a calculation, current time, system status, or web search, "
            "emit a line exactly like: TOOL:tool_name:argument — the system will execute it "
            "and return the result for you to use in your final answer."
        )
        self.session_id:           str                   = "default"
        self.history:              List[Dict[str, str]]  = []
        self.conversation_summary: str                   = ""
        self.gemini_status:        GeminiStatus          = GeminiStatus.INITIALIZING
        self.client                                      = None
        self.chat_session                                = None
        self._start_time:          float                 = time.time()

        # Load tools first (needed by SystemStatusTool)
        self.tools: Dict[str, object] = self._init_tools()

        # Attempt Gemini connection
        self._init_gemini()
        print("GEMINI STATUS =", self.gemini_status)

    # ── Private: initialisation ──────────────────────────

    def _init_tools(self) -> Dict[str, object]:
        """Instantiates all tools and returns a name-keyed registry dict."""
        try:
            from tools.calculator    import CalculatorTool
            from tools.current_time  import CurrentTimeTool
            from tools.system_status import SystemStatusTool
            from tools.web_search    import WebSearchTool

            instances = [
                CalculatorTool(),
                CurrentTimeTool(),
                SystemStatusTool(self),
                WebSearchTool(),
            ]
            registry = {t.name: t for t in instances}
            logger.info(f"Tools loaded: {list(registry.keys())}")
            return registry
        except Exception as exc:
            logger.error(f"Tool initialisation failed: {exc}", exc_info=True)
            return {}

    def _init_gemini(self) -> None:
        """Tries to create the Gemini client + chat session; sets gemini_status."""
        if not GENAI_AVAILABLE:
            self.gemini_status = GeminiStatus.SDK_MISSING
            logger.warning("GenAI SDK unavailable — SDK_MISSING.")
            return

        if not self.api_key or not self.api_key.strip():
            self.gemini_status = GeminiStatus.API_KEY_MISSING
            logger.warning("GEMINI_API_KEY not set — API_KEY_MISSING.")
            return

        try:
            logger.warning(f"API KEY FOUND: {self.api_key[:10]}...")
            print("API KEY FOUND:", self.api_key[:10], "...")
            self.client = genai.Client(api_key=self.api_key)
            config = types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                temperature=0.7,
            )
            self.chat_session = self.client.chats.create(
                model="gemini-2.5-flash",
                config=config,
            )
            self.gemini_status = GeminiStatus.LIVE
            logger.info("Gemini client initialised — status: LIVE.")
        except Exception as exc:
            print("\nINIT EXCEPTION")
            print("TYPE:", type(exc))
            print("ERROR:", exc)
            status = self._classify_api_error(exc)
            self.gemini_status = status
            logger.error(f"Gemini init failed ({status.value}): {exc}", exc_info=True)

    # ── Private: error handling ──────────────────────────

    def _classify_api_error(self, exc: Exception) -> GeminiStatus:
        """
        Maps an exception to the appropriate GeminiStatus.

        Logs full technical details server-side.
        Returns a status enum — callers produce friendly messages from it.
        """
        err_str = str(exc).lower()

        # Google APIError with a numeric or string code
        if APIError and isinstance(exc, APIError):
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code == 429 or "resource_exhausted" in err_str or "quota" in err_str:
                logger.warning(f"Quota exhausted: {exc}")
                return GeminiStatus.QUOTA_EXCEEDED
            if code in (401, 403) or any(k in err_str for k in ("api_key", "invalid_api", "permission")):
                logger.error(f"API key rejected: {exc}")
                return GeminiStatus.API_KEY_MISSING

        # Generic network / timeout signals
        if any(k in err_str for k in ("timeout", "timed out", "deadline exceeded")):
            logger.warning(f"Gemini timeout: {exc}")
        elif any(k in err_str for k in ("connection", "network", "unavailable", "socket", "refused")):
            logger.warning(f"Gemini network error: {exc}")
        else:
            logger.error(f"Gemini unexpected error: {exc}", exc_info=True)

        return GeminiStatus.FALLBACK

    def _friendly_error_message(self, status: GeminiStatus) -> str:
        """Returns a user-facing Markdown notice for a given GeminiStatus."""
        messages = {
            GeminiStatus.QUOTA_EXCEEDED: (
                "> ⚠️ **Gemini quota exceeded.**\n"
                "> Please wait or use another API key.\n\n"
            ),
            GeminiStatus.API_KEY_MISSING: (
                "> 🔑 **API Key Missing or Invalid.**\n"
                "> Please check your `.env` file and restart the server.\n\n"
            ),
            GeminiStatus.FALLBACK: (
                "> ⚙️ **Connection Issue** — Could not reach Gemini API (network/timeout). "
                "Responding in simulation mode for this turn.\n\n"
            ),
        }
        return messages.get(status, "> ⚠️ **Unknown Error** — Switched to simulation mode.\n\n")

    # ── Private: Gemini call with retry ─────────────────

    def _call_gemini_with_retry(self, message: str) -> str:
        """
        Sends *message* to the Gemini chat session with up to MAX_RETRIES attempts.

        Does not retry quota or auth errors (they won't resolve with retries).

        Args:
            message: The text to send to the chat session.

        Returns:
            The response text from Gemini.

        Raises:
            Exception: Re-raises the last exception after all retries are spent.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 2):  # +2 = initial + retries
            try:
                response = self.chat_session.send_message(message)
                return response.text
            except Exception as exc:
                print("\nSEND_MESSAGE EXCEPTION")
                print("TYPE:", type(exc))
                print("ERROR:", exc)
                last_exc = exc
                status   = self._classify_api_error(exc)
                # Non-retryable errors
                if status in (GeminiStatus.QUOTA_EXCEEDED, GeminiStatus.API_KEY_MISSING):
                    raise
                if attempt <= self.MAX_RETRIES:
                    logger.info(f"Retry {attempt}/{self.MAX_RETRIES} after: {exc}")
                    time.sleep(self.RETRY_DELAY * attempt)  # Linear backoff

        raise last_exc  # type: ignore[misc]

    # ── Private: memory management ───────────────────────

    def _maybe_summarize(self) -> None:
        """
        If in-memory history exceeds SUMMARY_TRIGGER, compresses the oldest
        messages into a brief summary and trims history to SUMMARY_KEEP items.

        Uses Gemini for the summary when LIVE; falls back to a placeholder.
        """
        if len(self.history) <= self.SUMMARY_TRIGGER:
            return

        older_msgs  = self.history[: -self.SUMMARY_KEEP]
        self.history = self.history[-self.SUMMARY_KEEP :]
        logger.info(
            f"[{self.session_id}] Summarising {len(older_msgs)} older messages."
        )

        if self.gemini_status == GeminiStatus.LIVE and self.client:
            try:
                blob = "\n".join(
                    f"{m['role'].upper()}: {m['text'][:300]}" for m in older_msgs
                )
                prompt = (
                    "Summarise this conversation in 3-4 sentences, preserving key facts:\n\n"
                    + blob
                )
                resp = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                self.conversation_summary = resp.text.strip()
                logger.info("Conversation summary generated successfully.")
            except Exception as exc:
                logger.warning(f"Summary generation failed: {exc}")
                self.conversation_summary = (
                    f"[Earlier conversation: {len(older_msgs)} messages condensed]"
                )
        else:
            self.conversation_summary = (
                f"[Earlier conversation: {len(older_msgs)} messages condensed]"
            )

    # ── Private: tool dispatch ───────────────────────────

    def _check_for_tool_call(self, text: str) -> Optional[str]:
        """
        Scans text for a TOOL:name:argument directive.

        Supports:
        TOOL:current_time
        TOOL:current_time:
        TOOL:calculator:2+2
        """
        print("\nCHECKING FOR TOOL CALL")
        print("TEXT =", repr(text))
        match = re.search(
            r"TOOL:([a-zA-Z0-9_]+)(?::(.*))?$",
            text.strip(),
            re.IGNORECASE,
        )

        if not match:
            return None

        tool_name = match.group(1).lower()
        tool_arg = (match.group(2) or "").strip()

        print(f"TOOL DETECTED -> {tool_name}")
        print(f"TOOL ARG -> {repr(tool_arg)}")

        tool = self.tools.get(tool_name)

        if not tool:
            available = ", ".join(self.tools.keys())
            return f"[Tool '{tool_name}' not found. Available: {available}]"

        try:
            result = tool.execute(tool_arg)
            print("TOOL RESULT ->", result)

            logger.info(
                f"Tool '{tool_name}' executed with arg={repr(tool_arg)[:80]}"
            )

            return result

        except Exception as exc:
            logger.error(f"Tool '{tool_name}' error: {exc}")
            return f"[Tool error ({tool_name}): {exc}]"

    # ── Public API ───────────────────────────────────────

    @property
    def is_simulated(self) -> bool:
        """Legacy boolean — True when the agent is not in LIVE mode."""
        return self.gemini_status != GeminiStatus.LIVE

    def get_uptime(self) -> float:
        """Returns seconds elapsed since this agent instance was created."""
        return time.time() - self._start_time

    def load_session(self, session_id: str) -> None:
        """
        Sets the active session and loads history from the database.

        Args:
            session_id: The session identifier to activate.
        """
        self.session_id = session_id
        self.history    = load_history_limited(session_id, limit=self.MAX_HISTORY)
        logger.info(f"Session loaded: {session_id!r} ({len(self.history)} messages).")

    def save_session(self, session_id: str) -> None:
        """
        Updates the active session ID.
        Messages are persisted incrementally in send_message(), so this
        method is provided for API compatibility only.

        Args:
            session_id: New session identifier.
        """
        self.session_id = session_id

    def send_message(self, message: str) -> str:
        """
        Processes a user message and returns the agent's response.

        Flow:
            1. Validate input.
            2. Compress history if above threshold.
            3. Persist user message to DB + in-memory history.
            4. If LIVE: call Gemini with retry.
               - If Gemini returns a TOOL directive: execute → feed result back.
               - On error: classify → update status → prepend friendly notice → fallback.
            5. If not LIVE: route to simulation (with basic tool support).
            6. Persist agent response and return.

        Args:
            message: The user's input string (already sanitised by caller).

        Returns:
            Agent response as a Markdown string.
        """
        if not message.strip():
            return "Please type a message!"

        # Compress history if needed
        self._maybe_summarize()

        # Persist user turn
        self.history.append({"role": "user", "text": message})
        save_message(self.session_id, "user", message)
        logger.info(f"[{self.session_id}] USER: {message[:200]}")

        response_text: str

        # ── LIVE branch ─────────────────────────────────
        if self.gemini_status != GeminiStatus.LIVE:
            self._init_gemini()
        if self.gemini_status == GeminiStatus.LIVE and self.chat_session:
            try:
                # Prepend older conversation context if available
                send_text = message
                if self.conversation_summary:
                    send_text = (
                        f"[Prior context: {self.conversation_summary}]\n\n{message}"
                    )

                gemini_reply = self._call_gemini_with_retry(send_text)
                print("\n========== GEMINI RAW ==========")
                print(gemini_reply)
                print("================================\n")

                # Tool dispatch
                tool_result = self._check_for_tool_call(gemini_reply)
                if tool_result:
                    follow_up = (
                        f"The requested tool has already been executed.\n\n"
                        f"Tool Output:\n{tool_result}\n\n"
                        "DO NOT call any tool again.\n"
                        "DO NOT output TOOL: syntax.\n"
                        "Answer the user directly using the tool output."
                    )
                    try:
                        response_text = self._call_gemini_with_retry(follow_up)
                    except Exception:
                        response_text = f"**Tool Result:**\n\n{tool_result}"
                else:
                    response_text = gemini_reply

                logger.info(f"[{self.session_id}] BOT: {response_text[:200]}")

            except Exception as exc:
                new_status    = self._classify_api_error(exc)
                self.gemini_status = new_status
                error_prefix  = self._friendly_error_message(new_status)
                sim_resp      = self._generate_simulated_response(message)
                response_text = error_prefix + sim_resp
                logger.warning(
                    f"[{self.session_id}] Gemini error — switched to {new_status.value}."
                )

        # ── Simulation branch ────────────────────────────
        else:
            response_text = self._simulation_with_tools(message)

        # Persist agent turn
        self.history.append({"role": "model", "text": response_text})
        save_message(self.session_id, "model", response_text)
        return response_text

    def get_history(self) -> List[Dict[str, str]]:
        """Returns the full in-memory chat history."""
        return self.history

    def clear_history(self) -> None:
        """
        Clears chat history from in-memory storage and the database,
        and resets the Gemini chat session.
        """
        self.history              = []
        self.conversation_summary = ""
        db_clear_history(self.session_id)
        logger.info(f"[{self.session_id}] History cleared.")

        # Reset Gemini chat session if live
        if self.gemini_status == GeminiStatus.LIVE and self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                )
                self.chat_session = self.client.chats.create(
                    model="gemini-2.5-flash",
                    config=config,
                )
                logger.info(f"[{self.session_id}] Gemini chat session reset.")
            except Exception as exc:
                logger.warning(f"Could not reset Gemini session: {exc}")
                self.gemini_status = GeminiStatus.FALLBACK

    # ── Simulation ───────────────────────────────────────

    def _simulation_with_tools(self, prompt: str) -> str:
        """
        Simulation mode with basic keyword-based tool triggering.
        Used when Gemini is unavailable (any non-LIVE status).
        """
        pl = prompt.lower()

        # Calculator shortcut
        if any(op in prompt for op in ["+", "-", "*", "/", "**", "%"]) and any(
            c.isdigit() for c in prompt
        ):
            tool = self.tools.get("calculator")
            if tool:
                result = tool.execute(prompt)
                if not result.startswith("❌"):
                    return f"### 🧮 Calculator\n\n{result}"

        # Time shortcut
        if any(k in pl for k in ["current time", "what time", "what date", "today"]):
            tool = self.tools.get("current_time")
            if tool:
                return tool.execute("")

        # System status shortcut
        if "system status" in pl or "agent status" in pl:
            tool = self.tools.get("system_status")
            if tool:
                return tool.execute("")

        # Web search shortcut
        if pl.startswith(("search", "look up", "find", "google", "web search")):
            tool = self.tools.get("web_search")
            if tool:
                query = re.sub(r"^(search|look up|find|google|web search)\s*", "", pl).strip()
                if query:
                    return tool.execute(query)

        return self._generate_simulated_response(prompt)

    def _generate_simulated_response(self, prompt: str) -> str:
        """
        Rule-based fallback responder.
        Handles common keyword patterns; returns generic responses otherwise.
        """
        p = prompt.lower().strip()

        if any(g in p for g in ["hello", "hi ", "hey ", "greetings"]):
            return (
                "### Hello there! 👋\n\n"
                "I am your Interactive AI Agent, currently in **simulation mode**.\n\n"
                f"- **Status**: `{self.gemini_status.value}`\n"
                "- Set `GEMINI_API_KEY` in `.env` and restart the server for full AI.\n\n"
                "Try **'help'**, **'code'**, **'tell a joke'**, or **'status'**."
            )

        if p == "help" or "help me" in p:
            return (
                "### Agent Help 🛠️\n\n"
                "**Simulation commands:**\n\n"
                "| Command | Description |\n"
                "|---|---|\n"
                "| `status` | Environment & Gemini status |\n"
                "| `code` | Python code templates |\n"
                "| `tell a joke` | Developer humor |\n"
                "| `calculate 2+2` | Basic math |\n"
                "| `current time` | Date & time |\n"
                "| `about` | System architecture |\n\n"
                "*In live mode, ask anything — Gemini will answer!*"
            )

        if "status" in p:
            tool = self.tools.get("system_status")
            if tool:
                return tool.execute("")
            return (
                "### System Status 📊\n\n"
                f"- **GenAI SDK**: {'✅ Installed' if GENAI_AVAILABLE else '❌ Not Installed'}\n"
                f"- **API Key**: {'✅ Set' if self.api_key else '❌ Missing'}\n"
                f"- **Mode**: `{self.gemini_status.value}`\n"
            )

        if "code" in p or "program" in p:
            return (
                "### Python + Gemini Example 🐍\n\n"
                "```python\n"
                "from google import genai\n\n"
                "client = genai.Client()  # reads GEMINI_API_KEY from env\n\n"
                "response = client.models.generate_content(\n"
                "    model='gemini-2.5-flash',\n"
                "    contents='Explain quantum computing in 3 sentences.',\n"
                ")\n\n"
                "print(response.text)\n"
                "```"
            )

        if "joke" in p or "laugh" in p or "funny" in p:
            jokes = [
                "Why do programmers wear glasses? Because they can't C#! 😂",
                "10 types of people: those who understand binary, and those who don't. 🤓",
                "How many programmers to change a bulb? None — that's hardware. 💡",
                "['hip', 'hip'] → hip hip array! 🚀",
                "Why did the DBA leave? Too many tables to join! 📊",
                "A SQL query walks into a bar, walks up to two tables and asks… 'Can I join you?' 🍺",
            ]
            return f"### Developer Joke 🎭\n\n{random.choice(jokes)}"

        if "about" in p:
            return (
                "### About Interactive Agent 🧠\n\n"
                "- **Backend**: FastAPI + Python 3\n"
                "- **AI**: Gemini 2.5 Flash (google-genai SDK)\n"
                "- **Tools**: Calculator · Current Time · System Status · Web Search\n"
                "- **Memory**: SQLite (100-msg limit with auto-summarisation)\n"
                "- **Frontend**: HTML5 + CSS3 (glassmorphism) + Vanilla JS\n"
                "- **Streaming**: SSE via `/api/chat/stream`\n"
                "- **Security**: Rate limiting (30 req/min) · Input sanitisation\n"
            )

        # Generic fallbacks
        responses = [
            "Interesting! Add `GEMINI_API_KEY` to `.env` for a full AI-powered answer.",
            "Try **'help'** for a list of simulation commands.",
            "I'm tracking our conversation! Type **'status'** to check the system.",
            "Once the API key is configured, Gemini will answer this brilliantly.",
        ]
        return f"### Simulated Response 🤖\n\n{random.choice(responses)}"
