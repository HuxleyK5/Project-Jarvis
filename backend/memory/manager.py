"""SQLite memory boundary. Uses only stdlib; no automatic fact extraction or embeddings."""

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.memory.privacy import normalize, sensitive
from backend.core.context import terms
from backend.core.personality import DEFAULT_STYLE, valid_style


class MemoryError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL, history INTEGER NOT NULL);
INSERT OR IGNORE INTO settings VALUES (1,0,0);
CREATE TABLE IF NOT EXISTS memories (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('preference','project','fact')),
 content TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
 user_text TEXT NOT NULL, assistant_text TEXT NOT NULL, searchable TEXT NOT NULL,
 fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(conversation_id,fingerprint));
CREATE INDEX IF NOT EXISTS turns_conversation ON turns(conversation_id,created_at);
CREATE TABLE IF NOT EXISTS options (key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version=2;
"""


class MemoryManager:
    def __init__(self, path: Path, allowed: bool = True):
        self.path = Path(path)
        self.allowed = allowed

    @contextmanager
    def database(self, write=False):
        if not self.path.exists() and not write:
            yield None
            return
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            # No WAL/transcript caches. Zero deleted SQLite cells where SQLite supports it.
            db.execute("PRAGMA secure_delete=ON")
            if write:
                db.executescript(SCHEMA)
                db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    def settings(self):
        with self.database() as db:
            row = db.execute("SELECT enabled,history FROM settings WHERE id=1").fetchone() if db else None
            recall = self.option(db, 'recall_history', 'false') == 'true'
        return {"enabled": self.allowed and bool(row and row["enabled"]),
                "save_history": self.allowed and bool(row and row["enabled"] and row["history"]),
                "allowed": self.allowed,
                "recall_history": self.allowed and bool(row and row['enabled']) and recall}

    @staticmethod
    def option(db, key, default):
        if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='options'").fetchone():
            return default
        row = db.execute("SELECT value FROM options WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def configure(self, enabled: bool, save_history: bool, approved: bool, recall_history: bool = False):
        if enabled and (not approved or not self.allowed):
            raise MemoryError("Memory requires explicit approval and must be allowed by local configuration.", 403)
        with self.database(write=True) as db:
            db.execute("UPDATE settings SET enabled=?,history=? WHERE id=1", (int(enabled), int(enabled and save_history)))
            db.execute("INSERT OR REPLACE INTO options VALUES('recall_history',?)", ('true' if enabled and recall_history else 'false',))
        return self.settings()

    def personality(self):
        if not self.settings()['enabled']:
            return dict(DEFAULT_STYLE)
        with self.database() as db:
            try:
                result = json.loads(self.option(db, 'personality', '{}'))
            except (ValueError, TypeError):
                return dict(DEFAULT_STYLE)
        return result if valid_style(result) else dict(DEFAULT_STYLE)

    def save_personality(self, style, approved):
        if not approved or not valid_style(style):
            raise MemoryError('A valid assistant style and explicit approval are required.', 403)
        self.require_enabled()
        with self.database(write=True) as db:
            if not self.allowed or not db.execute('SELECT enabled FROM settings WHERE id=1').fetchone()[0]:
                raise MemoryError('Memory is disabled.', 403)
            db.execute("INSERT OR REPLACE INTO options VALUES('personality',?)", (json.dumps(style),))
        return dict(style)

    def require_enabled(self):
        if not self.settings()["enabled"]:
            raise MemoryError("Memory is disabled. Enable it explicitly before saving.", 403)

    def save(self, kind: str, content: str, approved: bool, memory_id: int | None = None):
        if not approved:
            raise MemoryError("Review and explicitly approve this exact memory before saving.", 403)
        if sensitive(content):
            raise MemoryError("This text may contain credentials or sensitive personal data and cannot be saved.")
        if not normalize(content):
            raise MemoryError("Memory must contain meaningful text.")
        self.require_enabled()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.database(write=True) as db:
                if not self.allowed or not db.execute("SELECT enabled FROM settings WHERE id=1").fetchone()[0]:
                    raise MemoryError("Memory is disabled. Enable it explicitly before saving.", 403)
                if memory_id is None:
                    cursor = db.execute("INSERT INTO memories(kind,content,normalized,created_at,updated_at) VALUES(?,?,?,?,?)",
                                        (kind, content.strip(), normalize(content), now, now))
                    memory_id = cursor.lastrowid
                else:
                    cursor = db.execute("UPDATE memories SET kind=?,content=?,normalized=?,updated_at=? WHERE id=?",
                                        (kind, content.strip(), normalize(content), now, memory_id))
                    if not cursor.rowcount:
                        raise MemoryError("Saved memory was not found.", 404)
                return dict(db.execute("SELECT id,kind,content,created_at,updated_at FROM memories WHERE id=?", (memory_id,)).fetchone())
        except sqlite3.IntegrityError as exc:
            raise MemoryError("An equivalent memory is already saved.", 409) from exc

    def list_memories(self, query=""):
        with self.database() as db:
            if db is None:
                return []
            rows = db.execute("SELECT id,kind,content,created_at,updated_at FROM memories ORDER BY updated_at DESC,id DESC").fetchall()
        query = normalize(query)
        return [dict(row) for row in rows if query in normalize(row["content"])][:100]

    def relevant(self, question: str):
        if not self.settings()["enabled"]:
            return []
        words = terms(question)
        if not words:
            return []
        with self.database() as db:
            rows = db.execute("SELECT id,kind,content FROM memories ORDER BY updated_at DESC,id DESC").fetchall() if db else []
        ranked = []
        documents = [terms(row['content']) for row in rows]
        for row, tokens in zip(rows, documents):
            if sensitive(row["content"]):
                continue
            overlap = words & tokens
            score = sum(math.log(1 + len(rows) / (1 + sum(word in document for document in documents))) for word in overlap)
            if overlap:
                ranked.append((score, dict(row)))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [{**row, "content": row["content"][:500]} for _, row in ranked[:5]]

    def recall(self, question: str, exclude_conversation: str | None = None):
        if not self.settings()['recall_history']:
            return []
        with self.database() as db:
            rows = db.execute('SELECT conversation_id,user_text,assistant_text,created_at FROM turns ORDER BY created_at DESC LIMIT 500').fetchall() if db else []
        rows = [dict(row) for row in rows if row['conversation_id'] != exclude_conversation
                and not sensitive(row['user_text']) and not sensitive(row['assistant_text'])]
        words = terms(question)
        ranked = [(len(words & terms(row['user_text'] + ' ' + row['assistant_text'])), row) for row in rows]
        if words:
            ranked = [item for item in ranked if item[0] > 0]
            ranked.sort(key=lambda item: item[0], reverse=True)
        elif rows:
            ranked = [item for item in ranked if item[1]['conversation_id'] == rows[0]['conversation_id']]
        return [{**row, 'user_text': row['user_text'][:500], 'assistant_text': row['assistant_text'][:500]} for _, row in ranked[:3]]

    def save_turn(self, conversation_id: str, turn_id: str, user: str, assistant: str):
        if not self.settings()["save_history"]:
            return "disabled"
        if sensitive(user) or sensitive(assistant):
            return "skipped_sensitive"
        fingerprint = hashlib.sha256((normalize(user) + "\0" + normalize(assistant)).encode()).hexdigest()
        with self.database(write=True) as db:
            flags = db.execute("SELECT enabled,history FROM settings WHERE id=1").fetchone()
            if not self.allowed or not flags[0] or not flags[1]:
                return "disabled"
            cursor = db.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?,?,?,?)",
                                (turn_id, conversation_id, user, assistant, normalize(user + " " + assistant), fingerprint,
                                 datetime.now(timezone.utc).isoformat()))
            return "saved" if cursor.rowcount else "duplicate"

    def conversations(self, query="", conversation_id=None):
        with self.database() as db:
            if db is None:
                return []
            # Literal LIKE: searches cannot inject SQL or turn '%' into a wildcard.
            escaped = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql = "SELECT id,conversation_id,user_text,assistant_text,created_at FROM turns WHERE searchable LIKE ? ESCAPE '\\'"
            params = ["%" + escaped + "%"]
            if conversation_id:
                sql += " AND conversation_id=?"
                params.append(conversation_id)
            return [dict(row) for row in db.execute(sql + " ORDER BY created_at DESC LIMIT 100", params)]

    def delete(self, category: str, identifier, confirmed: bool):
        if not confirmed:
            raise MemoryError("Confirm deletion of this saved item.", 403)
        if category not in {"memories", "turns"}:
            raise MemoryError("Unknown memory category")
        with self.database() as db:
            if db is None or not db.execute(f"DELETE FROM {category} WHERE id=?", (identifier,)).rowcount:
                raise MemoryError("Saved item was not found.", 404)
