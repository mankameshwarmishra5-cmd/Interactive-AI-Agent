"""
main.py - FastAPI application entry point.

Phases covered:
    Phase 1 — Stability:     Startup validation, structured logging.
    Phase 4 — Performance:   SSE streaming endpoint (/api/chat/stream).
    Phase 5 — Security:      SlowAPI rate limiting (30/min per session),
                              session-ID validation, input sanitisation,
                              max message length, session eviction cap.
    Phase 6 — Production:    /api/health and /api/metrics endpoints.
    Phase 8 — Quality:       Type hints and docstrings throughout.

Routes (unchanged routes keep identical paths/methods):
    POST /api/chat         — Send message, receive response.
    GET  /api/status       — Gemini + environment status.
    POST /api/clear        — Clear session history.
    GET  /api/health       — Health check (DB, Gemini, uptime).
    GET  /api/metrics      — Active sessions, total messages, uptime.
    GET  /api/chat/stream  — SSE streaming version of /api/chat.
    GET  /                 — Serves static/index.html.
"""

from __future__ import annotations

import html
import logging
import logging.handlers
import os
import re
import time
import asyncio
from typing import Dict

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent import GENAI_AVAILABLE, GeminiStatus, InteractiveAgent
from database import get_total_messages, init_db

# ──────────────────────────────────────────────────────────
#  Server-level logging
# ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

_srv_handler = logging.handlers.RotatingFileHandler(
    "logs/server.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_srv_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
)
server_logger = logging.getLogger("server")
server_logger.setLevel(logging.INFO)
if not server_logger.handlers:
    server_logger.addHandler(_srv_handler)

# ──────────────────────────────────────────────────────────
#  Rate limiter — 30 requests / minute keyed by session_id
# ──────────────────────────────────────────────────────────
def _rate_limit_key(request: Request) -> str:
    """Uses session_id as the rate-limit key; falls back to client IP."""
    session_id = request.query_params.get("session_id", "")
    return session_id if session_id else get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)

# ──────────────────────────────────────────────────────────
#  App
# ──────────────────────────────────────────────────────────
_startup_time: float = time.time()

app = FastAPI(
    title="Interactive AI Agent Dashboard",
    description="FastAPI + Gemini 2.5 Flash chatbot with tools, streaming, and rate limiting.",
    version="2.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────
#  Session store
# ──────────────────────────────────────────────────────────
agents_db: Dict[str, InteractiveAgent] = {}
MAX_SESSIONS = 100

# session_id must be 1-64 alphanumeric / underscore / hyphen characters
_SESSION_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

MAX_MESSAGE_LENGTH = 4_000  # characters


def _validate_session_id(session_id: str) -> str:
    """
    Validates the format of *session_id*.

    Raises:
        HTTPException 400: If the session_id contains invalid characters.
    """
    if not _SESSION_RE.match(session_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid session_id. Use only alphanumeric characters, "
                "underscores, or hyphens (max 64 chars)."
            ),
        )
    return session_id


def _sanitize_message(message: str) -> str:
    """
    Escapes HTML entities and enforces the maximum message length.

    Raises:
        HTTPException 400: If the message exceeds MAX_MESSAGE_LENGTH.
    """
    message = html.escape(message)
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long. Maximum is {MAX_MESSAGE_LENGTH} characters.",
        )
    return message


def get_agent_for_session(session_id: str) -> InteractiveAgent:
    """
    Retrieves or creates an InteractiveAgent for *session_id*.

    Evicts the oldest session when the store is at capacity.

    Args:
        session_id: Validated session identifier.

    Returns:
        The InteractiveAgent instance for this session.
    """
    _validate_session_id(session_id)

    if len(agents_db) >= MAX_SESSIONS:
        oldest = next(iter(agents_db))
        del agents_db[oldest]
        server_logger.info(f"Session evicted (capacity): {oldest!r}")

    if session_id not in agents_db:
        agent = InteractiveAgent()
        agent.load_session(session_id)
        agents_db[session_id] = agent
        server_logger.info(f"New session created: {session_id!r}")

    return agents_db[session_id]


# ──────────────────────────────────────────────────────────
#  Pydantic schemas
# ──────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:    str = Field(..., min_length=1, max_length=4_000)
    session_id: str = Field(default="default", max_length=64)


class ChatResponse(BaseModel):
    response:      str
    history:       list
    is_simulated:  bool
    gemini_status: str


class StatusResponse(BaseModel):
    genai_installed:    bool
    api_key_configured: bool
    is_simulated:       bool
    gemini_status:      str


class ClearRequest(BaseModel):
    session_id: str = Field(default="default", max_length=64)


class HealthResponse(BaseModel):
    status:         str
    database:       str
    gemini:         str
    uptime_seconds: float


class MetricsResponse(BaseModel):
    active_sessions: int
    total_messages:  int
    uptime_seconds:  float


# ──────────────────────────────────────────────────────────
#  Startup validation
# ──────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_validation() -> None:
    """
    Runs at server start. Validates:
        - Required folders exist (logs/, static/).
        - Database is reachable and schema is initialised.
        - GEMINI_API_KEY presence (warning only — simulation still works).
        - google-genai SDK availability.
    """
    for folder in ("logs", "static", "tools", "memory"):
        os.makedirs(folder, exist_ok=True)

    try:
        init_db()
        server_logger.info("Database initialised successfully.")
    except Exception as exc:
        server_logger.critical(f"Database initialisation FAILED: {exc}")
        raise RuntimeError(f"Cannot initialise database: {exc}") from exc

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        server_logger.info("GEMINI_API_KEY detected.")
        if GENAI_AVAILABLE:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                client.models.get(model="gemini-2.5-flash")
                server_logger.info("Gemini connection test: SUCCESS")
            except Exception as e:
                server_logger.error(f"Gemini connection test: FAILED - {e}")
    else:
        server_logger.warning("GEMINI_API_KEY not set — simulation mode active.")

    if not GENAI_AVAILABLE:
        server_logger.warning("google-genai SDK not installed.")

    server_logger.info(f"🚀 Server started. Version 2.0.0. Uptime ref: {_startup_time:.0f}")


# ──────────────────────────────────────────────────────────
#  Routes — existing (preserved paths/methods)
# ──────────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat_endpoint(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Processes a user message synchronously and returns the agent's response.

    Rate limit: 30 requests per minute per session_id.
    """
    try:
        clean_msg = _sanitize_message(body.message)
        agent     = get_agent_for_session(body.session_id)
        response  = await asyncio.to_thread(agent.send_message, clean_msg)
        return ChatResponse(
            response=response,
            history=agent.get_history(),
            is_simulated=agent.is_simulated,
            gemini_status=agent.gemini_status.value,
        )
    except HTTPException:
        raise
    except Exception as exc:
        server_logger.error(f"Chat endpoint error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/api/status", response_model=StatusResponse)
async def status_endpoint(session_id: str = "default") -> StatusResponse:
    """Returns Gemini connection state and environment configuration."""
    agent = get_agent_for_session(session_id)
    return StatusResponse(
        genai_installed=GENAI_AVAILABLE,
        api_key_configured=bool(agent.api_key),
        is_simulated=agent.is_simulated,
        gemini_status=agent.gemini_status.value,
    )


@app.post("/api/clear")
async def clear_endpoint(request: ClearRequest) -> dict:
    """Clears chat history for the specified session."""
    agent = get_agent_for_session(request.session_id)
    agent.clear_history()
    server_logger.info(f"History cleared for session: {request.session_id!r}")
    return {"status": "cleared", "session_id": request.session_id}


# ──────────────────────────────────────────────────────────
#  Routes — new (Phase 6: production readiness)
# ──────────────────────────────────────────────────────────
@app.get("/api/health", response_model=HealthResponse)
async def health_endpoint() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        JSON with status, database connectivity, Gemini status, and uptime.
    """
    db_ok = True
    try:
        get_total_messages()
    except Exception as exc:
        server_logger.error(f"Health check DB error: {exc}")
        db_ok = False

    # Determine Gemini health from any active session or env inspection
    if agents_db:
        sample     = next(iter(agents_db.values()))
        gemini_str = sample.gemini_status.value
    elif GENAI_AVAILABLE and os.getenv("GEMINI_API_KEY", "").strip():
        gemini_str = "configured_not_tested"
    elif not GENAI_AVAILABLE:
        gemini_str = GeminiStatus.SDK_MISSING.value
    else:
        gemini_str = GeminiStatus.API_KEY_MISSING.value

    overall = "ok" if db_ok else "degraded"
    return HealthResponse(
        status=overall,
        database="ok" if db_ok else "error",
        gemini=gemini_str,
        uptime_seconds=round(time.time() - _startup_time, 2),
    )


@app.get("/api/metrics", response_model=MetricsResponse)
async def metrics_endpoint() -> MetricsResponse:
    """
    Runtime metrics endpoint.

    Returns:
        JSON with active in-memory sessions, total DB messages, and uptime.
    """
    return MetricsResponse(
        active_sessions=len(agents_db),
        total_messages=get_total_messages(),
        uptime_seconds=round(time.time() - _startup_time, 2),
    )


# ──────────────────────────────────────────────────────────
#  Routes — new (Phase 4: SSE streaming)
# ──────────────────────────────────────────────────────────
@app.get("/api/chat/stream")
@limiter.limit("30/minute")
async def chat_stream_endpoint(
    request: Request, message: str, session_id: str = "default"
) -> StreamingResponse:
    """
    Server-Sent Events streaming version of /api/chat.

    Streams the full response word-by-word with a small delay to simulate
    real-time token output. Falls back gracefully on errors.

    Rate limit: 30 requests per minute per session_id.
    """
    try:
        clean_msg = _sanitize_message(message)
        agent     = get_agent_for_session(session_id)
    except HTTPException as exc:
        async def _err():
            yield f"data: ERROR:{exc.detail}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    async def _event_gen():
        try:
            response_text = await asyncio.to_thread(agent.send_message, clean_msg)
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                # Escape newlines for SSE data field
                escaped = chunk.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"
                await asyncio.sleep(0.025)
            # Send final status metadata
            yield f"data: [DONE]\n\n"
            yield f"data: STATUS:{agent.gemini_status.value}\n\n"
        except Exception as exc:
            server_logger.error(f"Stream error ({session_id!r}): {exc}", exc_info=True)
            yield f"data: ERROR:{exc}\n\n"

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ──────────────────────────────────────────────────────────
#  Static files + root
# ──────────────────────────────────────────────────────────
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_dashboard():
    """Serves the main HTML dashboard page."""
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Server running — create static/index.html to enable the UI."}


# ──────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting Interactive AI Agent on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
