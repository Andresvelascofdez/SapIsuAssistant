"""
Chat history repository: sessions and messages persistence.
"""
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import ChatMessage, ChatSession


class ChatRepository:
    """Repository for chat sessions and messages."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    client_code TEXT NULL,
                    title TEXT NOT NULL,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    used_kb_items_json TEXT NOT NULL DEFAULT '[]',
                    model_called INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                        ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON chat_messages(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_message
                ON chat_sessions(last_message_at)
            """)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ── Sessions ──

    def create_session(
        self,
        scope: str,
        client_code: Optional[str] = None,
        title: str = "New Chat",
    ) -> ChatSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO chat_sessions
                   (session_id, scope, client_code, title, is_pinned, created_at, updated_at, last_message_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
                (session_id, scope, client_code, title, now, now, now),
            )
            conn.commit()
        return ChatSession(
            session_id=session_id, scope=scope, client_code=client_code,
            title=title, is_pinned=0, created_at=now, updated_at=now, last_message_at=now,
        )

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT session_id, scope, client_code, title, is_pinned, created_at, updated_at, last_message_at "
                "FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row:
            return ChatSession(*row)
        return None

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSession]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT session_id, scope, client_code, title, is_pinned, created_at, updated_at, last_message_at "
                "FROM chat_sessions ORDER BY is_pinned DESC, last_message_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [ChatSession(*r) for r in rows]

    def rename_session(self, session_id: str, title: str) -> Optional[ChatSession]:
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, now, session_id),
            )
            conn.commit()
        return self.get_session(session_id)

    def pin_session(self, session_id: str, pinned: bool) -> Optional[ChatSession]:
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE chat_sessions SET is_pinned = ?, updated_at = ? WHERE session_id = ?",
                (1 if pinned else 0, now, session_id),
            )
            conn.commit()
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._conn() as conn:
            # Foreign key CASCADE will delete messages
            cursor = conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = ?", (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def search_sessions(self, query: str, limit: int = 50) -> list[ChatSession]:
        """Search sessions by title or message content."""
        like = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT s.session_id, s.scope, s.client_code, s.title,
                          s.is_pinned, s.created_at, s.updated_at, s.last_message_at
                   FROM chat_sessions s
                   LEFT JOIN chat_messages m ON s.session_id = m.session_id
                   WHERE s.title LIKE ? OR m.content LIKE ?
                   ORDER BY s.is_pinned DESC, s.last_message_at DESC
                   LIMIT ?""",
                (like, like, limit),
            ).fetchall()
        return [ChatSession(*r) for r in rows]

    # ── Messages ──

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        used_kb_items_json: str = "[]",
        model_called: int = 0,
    ) -> ChatMessage:
        message_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO chat_messages
                   (message_id, session_id, role, content, created_at, used_kb_items_json, model_called)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (message_id, session_id, role, content, now, used_kb_items_json, model_called),
            )
            # Update session last_message_at
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ?, updated_at = ? WHERE session_id = ?",
                (now, now, session_id),
            )
            conn.commit()
        return ChatMessage(
            message_id=message_id, session_id=session_id, role=role,
            content=content, created_at=now, used_kb_items_json=used_kb_items_json,
            model_called=model_called,
        )

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT message_id, session_id, role, content, created_at, used_kb_items_json, model_called "
                "FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [ChatMessage(*r) for r in rows]

    # ── Retention ──

    def cleanup_retention(self, retention_days: int) -> int:
        """Delete unpinned sessions older than retention_days. Returns count deleted."""
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_sessions WHERE is_pinned = 0 AND last_message_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

    # ── Export ──

    def export_session_markdown(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        if not session:
            return None
        messages = self.get_messages(session_id)
        lines = [
            f"# {session.title}",
            f"",
            f"- **Scope:** {session.scope}",
            f"- **Client:** {session.client_code or 'N/A'}",
            f"- **Created:** {session.created_at}",
            f"- **Last activity:** {session.last_message_at}",
            f"",
            f"---",
            f"",
        ]
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            lines.append(f"### {role_label}")
            lines.append(f"")
            lines.append(msg.content)
            lines.append(f"")
            if msg.role == "assistant":
                kb_items = json.loads(msg.used_kb_items_json)
                if kb_items:
                    lines.append(f"*KB items used: {', '.join(str(k) for k in kb_items)}*")
                    lines.append(f"")
                lines.append(f"*Model called: {'Yes' if msg.model_called else 'No'}*")
                lines.append(f"")
        return "\n".join(lines)

    def export_session_json(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        if not session:
            return None
        messages = self.get_messages(session_id)
        data = {
            "session_id": session.session_id,
            "scope": session.scope,
            "client_code": session.client_code,
            "title": session.title,
            "is_pinned": session.is_pinned,
            "created_at": session.created_at,
            "last_message_at": session.last_message_at,
            "messages": [
                {
                    "message_id": m.message_id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "used_kb_items": json.loads(m.used_kb_items_json),
                    "model_called": bool(m.model_called),
                }
                for m in messages
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
