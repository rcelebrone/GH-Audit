"""
Cache local SQLite para resultados de auditoria.

Evita re-consultar a API do GitHub para períodos já processados.
Chave de cache: (username, date_start_iso, date_end_iso, orgs_sorted_json, count_files)
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".ghaudit" / "cache.db"


def _make_key(
    username: str,
    date_start: str,
    date_end: str,
    orgs_json: str,
    count_files: bool,
) -> str:
    """Retorna a chave canônica do cache (5-tupla separada por pipe)."""
    return f"{username}|{date_start}|{date_end}|{orgs_json}|{int(count_files)}"


class AuditCache:
    """
    Persiste e recupera resultados de auditoria usando SQLite.

    Thread-safe via threading.Lock + WAL mode.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()
        log.debug("[cache] banco: %s", self.db_path)

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_cache (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    created_at TEXT NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                );
            """)
            self._conn.commit()

    def get(self, key: str) -> Optional[Dict]:
        """Retorna o resultado cacheado ou None se não encontrado."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value, created_at FROM audit_cache WHERE key = ?",
                (key,),
            ).fetchone()
        if row:
            log.debug("[cache] HIT  key=%s  salvo_em=%s", key[:40], row[1])
            return json.loads(row[0])
        log.debug("[cache] MISS key=%s", key[:40])
        return None

    def put(self, key: str, value: Dict) -> None:
        """Persiste ou atualiza um resultado no cache."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_cache (key, value, created_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    created_at = excluded.created_at
                """,
                (key, json.dumps(value), now),
            )
            self._conn.commit()
        log.debug("[cache] SAVE key=%s", key[:40])

    def list_entries(self) -> List[Dict]:
        """Retorna todas as entradas do cache (para inspeção/diagnóstico)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, created_at FROM audit_cache ORDER BY created_at DESC"
            ).fetchall()
        return [{"key": r[0], "created_at": r[1]} for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
