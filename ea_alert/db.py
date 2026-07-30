from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from ea_alert.models import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  datetime_jst TEXT NOT NULL,
  time_known INTEGER NOT NULL DEFAULT 1,
  country TEXT NOT NULL,
  title TEXT NOT NULL,
  importance INTEGER NOT NULL,
  forecast TEXT,
  previous TEXT,
  source_url TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sent_log (
  event_id TEXT NOT NULL,
  notice_type TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  PRIMARY KEY (event_id, notice_type)
);
CREATE TABLE IF NOT EXISTS seen_news (
  news_id TEXT PRIMARY KEY,
  seen_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)

    def upsert_events(self, events: list[Event]) -> None:
        rows = [
            (
                e.id, e.kind, e.datetime_jst.isoformat(), int(e.time_known),
                e.country, e.title, e.importance, e.forecast, e.previous, e.source_url,
            )
            for e in events
        ]
        self.conn.executemany(
            """INSERT INTO events
               (id, kind, datetime_jst, time_known, country, title,
                importance, forecast, previous, source_url)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 forecast=excluded.forecast,
                 previous=excluded.previous""",
            rows,
        )
        self.conn.commit()

    def events_between(
        self, start: datetime, end: datetime, kind: str | None = None
    ) -> list[Event]:
        sql = (
            "SELECT kind, datetime_jst, time_known, country, title,"
            " importance, forecast, previous, source_url"
            " FROM events WHERE datetime_jst >= ? AND datetime_jst <= ?"
        )
        params: list[str] = [start.isoformat(), end.isoformat()]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY datetime_jst"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Event(
                kind=r[0],
                datetime_jst=datetime.fromisoformat(r[1]),
                time_known=bool(r[2]),
                country=r[3],
                title=r[4],
                importance=r[5],
                forecast=r[6],
                previous=r[7],
                source_url=r[8],
            )
            for r in rows
        ]

    def was_sent(self, event_id: str, notice_type: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sent_log WHERE event_id = ? AND notice_type = ?",
            (event_id, notice_type),
        ).fetchone()
        return row is not None

    def mark_sent(self, event_id: str, notice_type: str, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO sent_log (event_id, notice_type, sent_at) VALUES (?,?,?)",
            (event_id, notice_type, now.isoformat()),
        )
        self.conn.commit()

    def is_seen(self, news_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_news WHERE news_id = ?", (news_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, news_id: str, now: datetime) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_news (news_id, seen_at) VALUES (?,?)",
            (news_id, now.isoformat()),
        )
        self.conn.commit()

    def seen_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM seen_news").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
