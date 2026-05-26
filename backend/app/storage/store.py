"""SQLite store for reports + traces.

Schema is intentionally tiny — each row stores its full JSON blob. The point
is auditability and replay, not analytical queries.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional

import aiosqlite

from ..config import get_settings
from ..observability.tracer import TraceEvent
from ..schema.report import FinalReport


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    market TEXT NOT NULL,
    locale TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    intent TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_run_id ON traces(run_id);
CREATE INDEX IF NOT EXISTS idx_reports_market ON reports(market);
"""


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ---- Reports ----
    async def save_report(self, report: FinalReport) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO reports(id, product, market, locale, generated_at, payload) "
                "VALUES(?,?,?,?,?,?)",
                (
                    report.id, report.product, report.market, report.locale,
                    report.generated_at.isoformat(),
                    report.model_dump_json(),
                ),
            )
            await db.commit()

    async def get_report(self, report_id: str) -> Optional[FinalReport]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT payload FROM reports WHERE id=?", (report_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return FinalReport.model_validate_json(row[0])

    async def list_reports(self, limit: int = 50) -> List[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT id, product, market, locale, generated_at FROM reports "
                "ORDER BY generated_at DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
            return [
                {"id": r[0], "product": r[1], "market": r[2], "locale": r[3], "generated_at": r[4]}
                for r in rows
            ]

    # ---- Traces ----
    async def save_trace_events(self, events: List[TraceEvent]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO traces(id, run_id, agent, intent, started_at, ended_at, "
                "status, payload) VALUES(?,?,?,?,?,?,?,?)",
                [
                    (
                        e.id, e.run_id, e.agent, e.intent,
                        e.started_at.isoformat(),
                        e.ended_at.isoformat() if e.ended_at else None,
                        e.status,
                        e.model_dump_json(),
                    )
                    for e in events
                ],
            )
            await db.commit()

    async def get_trace(self, run_id: str) -> List[TraceEvent]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT payload FROM traces WHERE run_id=? ORDER BY started_at ASC",
                (run_id,),
            )
            rows = await cur.fetchall()
            return [TraceEvent.model_validate_json(r[0]) for r in rows]


@lru_cache(maxsize=1)
def get_store() -> Store:
    settings = get_settings()
    return Store(db_path=str(settings.data_dir / "app.sqlite"))
