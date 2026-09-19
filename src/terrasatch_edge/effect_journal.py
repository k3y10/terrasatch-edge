"""Durable at-most-once claims for physical non-radio Edge effects."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .models import EdgeCommand


class EffectJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS attempts (
                scope TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, detail TEXT NOT NULL, started REAL NOT NULL,
                PRIMARY KEY (scope, id))"""
            )

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
            raise ValueError("Command payload changed after physical execution began")
        if row[1] == "executing":
            raise RuntimeError(
                "Physical command already started; outcome is uncertain and will not replay"
            )
        return row[1], row[2]

    def claim(self, scope: str, command: EdgeCommand) -> bool:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM attempts WHERE scope=? AND id=?",
                (scope, command.id),
            ).fetchone():
                return False
            if db.execute(
                "SELECT 1 FROM attempts WHERE scope=? AND status='executing'",
                (scope,),
            ).fetchone():
                raise RuntimeError(
                    "Another physical command is active or uncertain for this asset"
                )
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    scope,
                    command.id,
                    self.fingerprint(command),
                    "executing",
                    "",
                    time.time(),
                ),
            )
        return True

    def finish(self, scope: str, command: EdgeCommand, result: tuple[str, str]) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE attempts SET status=?, detail=?, started=? WHERE scope=? AND id=?",
                (*result, time.time(), scope, command.id),
            )