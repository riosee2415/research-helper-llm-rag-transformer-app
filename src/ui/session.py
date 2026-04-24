"""Local file-based session persistence for conversation history."""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from config import SESSION_DIR

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


class SessionManager:
    """
    Manages conversation sessions as JSON files in SESSION_DIR.

    One JSON file = one session.
    Schema: {session_id, created_at, updated_at, messages[{role,content,timestamp}],
             memory_messages[{type,content}]}
    """

    def __init__(self, session_dir: Optional[Path] = None):
        self._dir = Path(session_dir) if session_dir else SESSION_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _read(self, session_id: str) -> Optional[dict]:
        p = self._path(session_id)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error("세션 파일 읽기 실패 (E-S-01): %s — %s", session_id, e)
            return None

    def _write(self, data: dict) -> bool:
        session_id = data["session_id"]
        p = self._path(session_id)
        try:
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            logger.error("세션 파일 쓰기 실패 (E-S-02): %s — %s", session_id, e)
            return False

    def create_session(self) -> str:
        """Create a new empty session and return its session_id."""
        session_id = str(uuid.uuid4())
        now = _now()
        data = {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "memory_messages": [],
        }
        self._write(data)
        logger.debug("Created session: %s", session_id)
        return session_id

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        memory_messages: Optional[list] = None,
    ) -> None:
        """
        Append a message to the session and optionally update memory_messages.

        role: "user" | "assistant"
        """
        data = self._read(session_id)
        if data is None:
            logger.warning("Save attempted on missing session: %s — creating new", session_id)
            now = _now()
            data = {
                "session_id": session_id,
                "created_at": now,
                "updated_at": now,
                "messages": [],
                "memory_messages": [],
            }

        data["messages"].append({
            "role": role,
            "content": content,
            "timestamp": _now(),
        })
        data["updated_at"] = _now()
        if memory_messages is not None:
            data["memory_messages"] = memory_messages

        self._write(data)

    def load_session(self, session_id: str) -> Optional[dict]:
        """Load and return session data, or None if not found / unreadable."""
        return self._read(session_id)

    def load_latest_session(self) -> Optional[dict]:
        """
        Return the most recently updated session, or None if no sessions exist.
        Used on app startup to restore the previous conversation.
        """
        sessions = self.list_sessions()
        if not sessions:
            return None
        latest = sessions[0]
        return self._read(latest["session_id"])

    def list_sessions(self) -> list[dict]:
        """
        Return a list of session summaries sorted by updated_at descending.

        Each item: {session_id, created_at, updated_at, message_count}
        """
        results = []
        try:
            for p in self._dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    results.append({
                        "session_id": data["session_id"],
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "message_count": len(data.get("messages", [])),
                    })
                except Exception as e:
                    logger.warning("세션 요약 읽기 실패: %s — %s", p.name, e)
        except Exception as e:
            logger.error("세션 목록 조회 실패 (E-S-01): %s", e)

        results.sort(key=lambda x: x["updated_at"], reverse=True)
        return results

    def delete_session(self, session_id: str) -> None:
        """Delete the session file if it exists. Silently ignores missing files."""
        p = self._path(session_id)
        try:
            if p.exists():
                p.unlink()
                logger.debug("Deleted session: %s", session_id)
        except Exception as e:
            logger.warning("세션 삭제 실패: %s — %s", session_id, e)

    def rebuild_memory(self, session_id: str) -> list[dict]:
        """
        Return memory_messages from the session for RAGEngine.load_memory_messages().

        Returns empty list on failure (E-S-04).
        """
        data = self._read(session_id)
        if data is None:
            logger.error("메모리 복원 실패 (E-S-04): 세션 없음 %s", session_id)
            return []
        return data.get("memory_messages", [])
