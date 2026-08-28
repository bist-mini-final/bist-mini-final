from __future__ import annotations

from typing import Any
from uuid import uuid4

import psycopg2.extras

from backend.storage.db_manager import DatabaseManager


class ChatSessionRepository:
    """PostgreSQL persistence for chat sessions; auth can replace client_id later."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    def create_session(self, client_id: str, title: str) -> dict[str, Any]:
        session_id = f"chat-{uuid4().hex}"
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """INSERT INTO chat_sessions (session_id, client_id, title)
                    VALUES (%s, %s, %s) RETURNING session_id, title, created_at, updated_at""",
                    (session_id, client_id, title),
                )
                row = dict(cursor.fetchone())
            connection.commit()
        return self._session_payload(row)

    def list_sessions(self, client_id: str) -> list[dict[str, Any]]:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT session_id, title, created_at, updated_at FROM chat_sessions
                    WHERE client_id = %s ORDER BY updated_at DESC""", (client_id,)
                )
                return [self._session_payload(dict(row)) for row in cursor.fetchall()]

    def get_session(self, session_id: str, client_id: str) -> dict[str, Any] | None:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT session_id, title, created_at, updated_at FROM chat_sessions
                    WHERE session_id = %s AND client_id = %s""", (session_id, client_id)
                )
                session = cursor.fetchone()
                if session is None:
                    return None
                cursor.execute(
                    """SELECT message_id, role, content, status, workflow_run_id, visualization, attachments, created_at
                    FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC""", (session_id,)
                )
                result = self._session_payload(dict(session))
                result["messages"] = [self._message_payload(dict(row)) for row in cursor.fetchall()]
                return result

    def recent_user_messages(self, session_id: str, limit: int = 6) -> list[str]:
        """Return recent user prompts for lightweight conversational retrieval context."""
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT content FROM chat_messages
                    WHERE session_id = %s AND role = 'user'
                    ORDER BY created_at DESC LIMIT %s""",
                    (session_id, limit),
                )
                return [str(row[0]) for row in cursor.fetchall()]

    def company_names(self) -> list[str]:
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT display_name FROM bi_companies ORDER BY display_name")
                return [str(row[0]) for row in cursor.fetchall()]

    def session_id_for_run(self, run_id: str) -> str | None:
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT session_id FROM chat_messages WHERE workflow_run_id = %s",
                    (run_id,),
                )
                row = cursor.fetchone()
        return str(row[0]) if row else None

    def rename_session(self, session_id: str, client_id: str, title: str) -> dict[str, Any]:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """UPDATE chat_sessions SET title = %s, updated_at = NOW()
                    WHERE session_id = %s AND client_id = %s
                    RETURNING session_id, title, created_at, updated_at""",
                    (title, session_id, client_id),
                )
                row = cursor.fetchone()
            connection.commit()
        if row is None:
            raise LookupError("대화 세션을 찾을 수 없습니다")
        return self._session_payload(dict(row))

    def delete_session(self, session_id: str, client_id: str) -> None:
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM chat_sessions WHERE session_id = %s AND client_id = %s",
                    (session_id, client_id),
                )
            connection.commit()

    def create_attachment(self, session_id: str, *, attachment_id: str, file_name: str, content_type: str | None, file_size: int, storage_path: str, extracted_text: str) -> dict[str, Any]:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """INSERT INTO chat_attachments (attachment_id, session_id, file_name, content_type, file_size, storage_path, extracted_text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING attachment_id, file_name, content_type, file_size, created_at""",
                    (attachment_id, session_id, file_name, content_type, file_size, storage_path, extracted_text),
                )
                row = dict(cursor.fetchone())
            connection.commit()
        return {"id": row["attachment_id"], "name": row["file_name"], "content_type": row["content_type"], "size": row["file_size"], "created_at": row["created_at"].isoformat()}

    def get_attachment(self, session_id: str, attachment_id: str) -> dict[str, Any] | None:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """SELECT attachment_id, file_name, content_type, file_size, extracted_text, created_at
                    FROM chat_attachments WHERE attachment_id = %s AND session_id = %s""",
                    (attachment_id, session_id),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def create_turn(self, session_id: str, content: str, run_id: str, visualization: dict[str, str] | None = None, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        user_id, assistant_id = f"message-{uuid4().hex}", f"message-{uuid4().hex}"
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """INSERT INTO chat_messages (message_id, session_id, role, content, status, attachments)
                    VALUES (%s, %s, 'user', %s, 'completed', %s)""", (user_id, session_id, content, psycopg2.extras.Json(attachments or []))
                )
                cursor.execute(
                    """INSERT INTO chat_messages (message_id, session_id, role, content, status, workflow_run_id, visualization)
                    VALUES (%s, %s, 'assistant', '', 'processing', %s, %s)
                    RETURNING message_id, role, content, status, workflow_run_id, visualization, attachments, created_at""",
                    (assistant_id, session_id, run_id, psycopg2.extras.Json(visualization) if visualization else None),
                )
                assistant = self._message_payload(dict(cursor.fetchone()))
                cursor.execute(
                    """UPDATE chat_sessions SET title = CASE WHEN title = '새 대화' THEN %s ELSE title END,
                    updated_at = NOW() WHERE session_id = %s""", (content[:80], session_id)
                )
            connection.commit()
        return {"assistant_message": assistant, "run_id": run_id}

    def create_direct_turn(self, session_id: str, content: str, answer: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        user_id, assistant_id = f"message-{uuid4().hex}", f"message-{uuid4().hex}"
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("INSERT INTO chat_messages (message_id, session_id, role, content, status, attachments) VALUES (%s, %s, 'user', %s, 'completed', %s)", (user_id, session_id, content, psycopg2.extras.Json(attachments or [])))
                cursor.execute("""INSERT INTO chat_messages (message_id, session_id, role, content, status) VALUES (%s, %s, 'assistant', %s, 'completed')
                    RETURNING message_id, role, content, status, workflow_run_id, visualization, attachments, created_at""", (assistant_id, session_id, answer))
                assistant = self._message_payload(dict(cursor.fetchone()))
                cursor.execute("UPDATE chat_sessions SET title = CASE WHEN title = '새 대화' THEN %s ELSE title END, updated_at = NOW() WHERE session_id = %s", (content[:80], session_id))
            connection.commit()
        return {"assistant_message": assistant, "run_id": None, "mode": "direct"}

    def complete_turn(
        self,
        run_id: str,
        status: str,
        content: str,
        *,
        suppress_visualization: bool = False,
    ) -> dict[str, Any] | None:
        with self._database._raw_connection() as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    """UPDATE chat_messages SET status = %s, content = %s,
                    visualization = CASE WHEN %s THEN NULL ELSE visualization END
                    WHERE workflow_run_id = %s
                    RETURNING message_id, role, content, status, workflow_run_id, visualization, attachments, created_at""",
                    (status, content, suppress_visualization, run_id),
                )
                row = cursor.fetchone()
            connection.commit()
        return self._message_payload(dict(row)) if row else None

    def owns_run(self, run_id: str, client_id: str) -> bool:
        with self._database._raw_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM chat_messages message JOIN chat_sessions session
                    ON session.session_id = message.session_id
                    WHERE message.workflow_run_id = %s AND session.client_id = %s""",
                    (run_id, client_id),
                )
                return cursor.fetchone() is not None

    @staticmethod
    def _session_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["session_id"], "title": row["title"], "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()}

    @staticmethod
    def _message_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["message_id"], "role": row["role"], "content": row["content"], "status": row["status"], "run_id": row["workflow_run_id"], "visualization": row.get("visualization"), "attachments": row.get("attachments") or [], "created_at": row["created_at"].isoformat()}
