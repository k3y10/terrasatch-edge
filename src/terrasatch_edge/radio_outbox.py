"""Small durable SQLite outbox for validated Edge radio transmissions."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RadioOutboxFull(RuntimeError):
    """Raised when the configured durable queue bound has been reached."""


@dataclass(frozen=True)
class RadioOutboxItem:
    source_message_id: str
    payload: dict[str, Any]
    attempts: int
    next_attempt_at: float
    created_at: float
    last_error: str | None


def retry_delay_seconds(attempts: int) -> float:
    """Return the bounded field-network retry schedule after a failed attempt."""

    schedule = (10.0, 30.0, 60.0, 300.0)
    index = max(attempts - 1, 0)
    if index < len(schedule):
        return schedule[index]
    return min(schedule[-1] * (2 ** (index - len(schedule) + 1)), 3600.0)


class RadioOutbox:
    def __init__(self, path: str | Path, *, max_items: int = 1000) -> None:
        self.path = Path(path)
        self.max_items = max(max_items, 1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS radio_outbox (
                    source_message_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    last_error TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_radio_outbox_due "
                "ON radio_outbox(next_attempt_at, created_at)"
            )

    def depth(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM radio_outbox").fetchone()
            return int(row["count"] if row else 0)

    def enqueue(self, source_message_id: str, payload: dict[str, Any]) -> bool:
        """Persist one payload; duplicate source IDs remain one durable item."""

        now = time.time()
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM radio_outbox WHERE source_message_id = ?",
                (source_message_id,),
            ).fetchone()
            if existing is not None:
                return False
            count = connection.execute("SELECT COUNT(*) AS count FROM radio_outbox").fetchone()
            if count is not None and int(count["count"]) >= self.max_items:
                raise RadioOutboxFull(
                    f"Radio outbox limit of {self.max_items} validated transmissions was reached"
                )
            connection.execute(
                """
                INSERT INTO radio_outbox (
                    source_message_id, payload_json, attempts, next_attempt_at, created_at
                ) VALUES (?, ?, 0, ?, ?)
                """,
                (source_message_id, encoded, now, now),
            )
        return True

    def due(self, *, now: float | None = None) -> RadioOutboxItem | None:
        current = time.time() if now is None else now
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_message_id, payload_json, attempts, next_attempt_at,
                       created_at, last_error
                FROM radio_outbox
                WHERE next_attempt_at <= ?
                ORDER BY next_attempt_at, created_at
                LIMIT 1
                """,
                (current,),
            ).fetchone()
        if row is None:
            return None
        return RadioOutboxItem(
            source_message_id=str(row["source_message_id"]),
            payload=json.loads(str(row["payload_json"])),
            attempts=int(row["attempts"]),
            next_attempt_at=float(row["next_attempt_at"]),
            created_at=float(row["created_at"]),
            last_error=str(row["last_error"]) if row["last_error"] else None,
        )

    def delivered(self, source_message_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM radio_outbox WHERE source_message_id = ?",
                (source_message_id,),
            )

    def failed(
        self,
        source_message_id: str,
        error: str,
        *,
        now: float | None = None,
    ) -> float:
        current = time.time() if now is None else now
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts FROM radio_outbox WHERE source_message_id = ?",
                (source_message_id,),
            ).fetchone()
            attempts = (int(row["attempts"]) if row else 0) + 1
            next_attempt = current + retry_delay_seconds(attempts)
            connection.execute(
                """
                UPDATE radio_outbox
                SET attempts = ?, next_attempt_at = ?, last_error = ?
                WHERE source_message_id = ?
                """,
                (attempts, next_attempt, error[:500], source_message_id),
            )
        return next_attempt
