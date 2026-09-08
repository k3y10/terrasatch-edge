"""Durable at-most-once RF attempt claims, including across Edge processes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .models import EdgeCommand


class CommandJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS attempts (
                scope TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, detail TEXT NOT NULL, started REAL NOT NULL,
                PRIMARY KEY (scope, id))""")

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def fingerprint(command: EdgeCommand) -> str:
        content = [
            command.organization_id,
            command.site_id,
            command.edge_device_id,
            command.command_type,
            command.payload,
        ]
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()

    def previous(self, scope: str, command: EdgeCommand) -> tuple[str, str] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT fingerprint, status, detail FROM attempts WHERE scope=? AND id=?",
                (scope, command.id),
            ).fetchone()
        if row is None:
            return None
        if row[0] != self.fingerprint(command):
            raise ValueError("Command payload changed after an RF attempt")
        if row[1] == "executing":
            # Another process may still be transmitting, or the first process died.
            # Neither repeat the operation nor invent a terminal outcome.
            raise RuntimeError(
                "RF attempt already started; outcome requires reconciliation; will not replay"
            )
        return row[1], row[2]

    def claim(self, scope: str, command: EdgeCommand, cooldown: float) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM attempts WHERE scope=? AND id=?", (scope, command.id)
            ).fetchone():
                return False
            if db.execute(
                "SELECT 1 FROM attempts WHERE scope=? AND status='executing'", (scope,)
            ).fetchone():
                raise RuntimeError("Another RF attempt is active or uncertain; will not overlap")
            last = db.execute(
                "SELECT MAX(started) FROM attempts WHERE scope=?", (scope,)
            ).fetchone()[0]
            if last is not None and time.time() < last + cooldown:
                raise RuntimeError("RF response cooldown is active; retry later")
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)",
                (scope, command.id, self.fingerprint(command), "executing", "", time.time()),
            )
        return True

    def finish(self, scope: str, command: EdgeCommand, result: tuple[str, str]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE attempts SET status=?, detail=?, started=? WHERE scope=? AND id=?",
                (*result, time.time(), scope, command.id),
            )

    def reconcile_failed(self, scope: str, command_id: str) -> None:
        """Record an operator-confirmed stop without deleting or replaying an attempt."""
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE attempts SET status='failed', detail=?, started=? "
                "WHERE scope=? AND id=? AND status='executing'",
                ('Operator confirmed provider stopped; RF outcome uncertain; no replay',
                 time.time(), scope, command_id),
            )
            if cursor.rowcount != 1:
                raise ValueError('No unresolved RF attempt found for this paired identity')
