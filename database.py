"""
database.py - SQLite persistence layer for chat session messages.

Tables:
    messages — one row per user/model turn, with session_id, role, text, timestamp.

Functions:
    init_db()                           — Creates tables if needed.
    save_message(session_id, role, text) — Persists one message.
    load_history(session_id)            — Returns full history (oldest first).
    load_history_limited(session_id, N) — Returns latest N messages (oldest first).
    clear_history(session_id)           — Deletes all messages for a session.
    get_session_count()                 — Count of distinct session IDs.
    get_total_messages()                — Total message count across all sessions.
"""

import sqlite3
from typing import List, Dict

DB_NAME = "chat_memory.db"


def init_db() -> None:
    """Creates the messages table if it does not already exist."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER  PRIMARY KEY AUTOINCREMENT,
            session_id TEXT     NOT NULL,
            role       TEXT     NOT NULL,
            text       TEXT     NOT NULL,
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Index for fast per-session queries
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session
        ON messages (session_id, id)
    """)
    conn.commit()
    conn.close()


def save_message(session_id: str, role: str, text: str) -> None:
    """
    Persists a single chat message to the database.

    Args:
        session_id: The session this message belongs to.
        role:       Either 'user' or 'model'.
        text:       The message content.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        "INSERT INTO messages (session_id, role, text) VALUES (?, ?, ?)",
        (session_id, role, text),
    )
    conn.commit()
    conn.close()


def load_history(session_id: str) -> List[Dict[str, str]]:
    """
    Returns the complete message history for *session_id*, oldest first.

    Args:
        session_id: Target session identifier.

    Returns:
        List of dicts with keys 'role' and 'text'.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute(
        "SELECT role, text FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": role, "text": text} for role, text in rows]


def load_history_limited(session_id: str, limit: int = 100) -> List[Dict[str, str]]:
    """
    Returns the latest *limit* messages for *session_id*, ordered oldest-first.

    This prevents unbounded memory growth — the agent only keeps the most
    recent *limit* exchanges in memory.

    Args:
        session_id: Target session identifier.
        limit:      Maximum number of messages to load (default 100).

    Returns:
        List of dicts with keys 'role' and 'text'.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute(
        """
        SELECT role, text FROM (
            SELECT id, role, text
            FROM   messages
            WHERE  session_id = ?
            ORDER  BY id DESC
            LIMIT  ?
        )
        ORDER BY id ASC
        """,
        (session_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": role, "text": text} for role, text in rows]


def clear_history(session_id: str) -> None:
    """
    Deletes all messages for *session_id* from the database.

    Args:
        session_id: Target session identifier.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def get_session_count() -> int:
    """Returns the number of distinct session IDs stored in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT COUNT(DISTINCT session_id) FROM messages")
    count: int = cursor.fetchone()[0]
    conn.close()
    return count


def get_total_messages() -> int:
    """Returns the total number of messages across all sessions."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.execute("SELECT COUNT(*) FROM messages")
    count: int = cursor.fetchone()[0]
    conn.close()
    return count