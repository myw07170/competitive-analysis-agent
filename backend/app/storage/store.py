"""用于报告、追踪、跨运行知识、修正、运行状态与 DAG 检查点的 SQLite 存储。

每一行都存储其完整的 JSON blob —— 目的是可审计、可回放、可跨运行演化，
而非重度分析。较新的表支撑了 v1.1 新增的功能：

* ``knowledge_snapshots`` —— 每次运行每个竞品一行，按归一化的实体键索引，
  使同一竞品可在多次运行间做 diff（创新点 3：知识库演化）。
* ``corrections``        —— 人在回路编辑（创新点 5：主动学习）。
* ``runs``               —— 外置的运行注册表，使状态在重启与多 worker 部署后存活（P1-7）。
* ``run_checkpoints``    —— 每节点的 GraphState 快照，用于续跑（创新点 6）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from ..config import get_settings
from ..observability.tracer import TraceEvent
from ..schema.report import Correction, FinalReport


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
CREATE TABLE IF NOT EXISTS knowledge_snapshots (
    id TEXT PRIMARY KEY,
    entity_key TEXT NOT NULL,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    report_id TEXT,
    captured_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    market TEXT,
    target_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    product TEXT,
    market TEXT,
    status TEXT NOT NULL,
    report_id TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_checkpoints (
    run_id TEXT NOT NULL,
    node TEXT NOT NULL,
    seq INTEGER NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_traces_run_id ON traces(run_id);
CREATE INDEX IF NOT EXISTS idx_reports_market ON reports(market);
CREATE INDEX IF NOT EXISTS idx_ks_entity ON knowledge_snapshots(entity_key);
CREATE INDEX IF NOT EXISTS idx_ks_market ON knowledge_snapshots(market);
CREATE INDEX IF NOT EXISTS idx_corr_report ON corrections(report_id);
CREATE INDEX IF NOT EXISTS idx_corr_market ON corrections(market);
"""


def normalize_entity_key(name: str, market: str) -> str:
    """用于跨运行标识同一竞品的稳定键。

    转小写、去标点 / 空白，并按市场命名空间隔离 —— 一个轻量的实体消歧步骤
    （无需嵌入模型），足以把多次运行中的 "Notion"、"notion"、"Notion " 对齐到一起。
    """
    norm = re.sub(r"\s+", "", (name or "").strip().lower())
    norm = re.sub(r"[^\w一-鿿]", "", norm)
    return f"{market}:{norm}"


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ---- 报告 ----
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

    async def get_recent_reports(self, limit: int = 200) -> List[FinalReport]:
        """完整的报告对象 —— 供元评估器的聚合统计使用。"""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT payload FROM reports ORDER BY generated_at DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
        out: List[FinalReport] = []
        for r in rows:
            try:
                out.append(FinalReport.model_validate_json(r[0]))
            except Exception:
                continue
        return out

    async def delete_report(self, report_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT payload FROM reports WHERE id=?", (report_id,))
            row = await cur.fetchone()
            if not row:
                return False
            try:
                run_id = json.loads(row[0]).get("run_id", "")
            except (ValueError, AttributeError):
                run_id = ""
            if run_id:
                await db.execute("DELETE FROM traces WHERE run_id=?", (run_id,))
                await db.execute("DELETE FROM run_checkpoints WHERE run_id=?", (run_id,))
                await db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            await db.execute("DELETE FROM corrections WHERE report_id=?", (report_id,))
            await db.execute("DELETE FROM reports WHERE id=?", (report_id,))
            await db.commit()
            return True

    # ---- 追踪 ----
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

    # ---- 知识快照（跨运行演化） ----
    async def save_knowledge_snapshot(
        self, *, entity_key: str, market: str, name: str, run_id: str,
        report_id: str, captured_at: str, payload_json: str,
    ) -> None:
        snap_id = f"ks_{run_id}_{entity_key}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO knowledge_snapshots"
                "(id, entity_key, market, name, run_id, report_id, captured_at, payload) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (snap_id, entity_key, market, name, run_id, report_id, captured_at, payload_json),
            )
            await db.commit()

    async def knowledge_history(self, entity_key: str, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT run_id, report_id, captured_at, payload FROM knowledge_snapshots "
                "WHERE entity_key=? ORDER BY captured_at DESC LIMIT ?",
                (entity_key, limit),
            )
            rows = await cur.fetchall()
        return [
            {"run_id": r[0], "report_id": r[1], "captured_at": r[2], "payload": json.loads(r[3])}
            for r in rows
        ]

    async def two_latest_snapshots(self, entity_key: str) -> Tuple[Optional[dict], Optional[dict]]:
        """返回用于 diff 的 (最新, 上一个) 快照字典，或 (最新, None)。"""
        hist = await self.knowledge_history(entity_key, limit=2)
        latest = hist[0] if len(hist) >= 1 else None
        prev = hist[1] if len(hist) >= 2 else None
        return latest, prev

    async def list_entities(self, market: Optional[str] = None) -> List[Dict[str, Any]]:
        """带快照计数的去重后受跟踪竞品（供演化浏览器使用）。"""
        q = (
            "SELECT entity_key, market, name, COUNT(*) as n, MAX(captured_at) as last "
            "FROM knowledge_snapshots {where} GROUP BY entity_key ORDER BY last DESC"
        )
        where = "WHERE market=?" if market else ""
        params: Tuple = (market,) if market else ()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(q.format(where=where), params)
            rows = await cur.fetchall()
        return [
            {"entity_key": r[0], "market": r[1], "name": r[2], "snapshots": r[3], "last_captured_at": r[4]}
            for r in rows
        ]

    # ---- 修正（人在回路） ----
    async def save_correction(self, c: Correction) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO corrections(id, report_id, market, target_path, created_at, payload) "
                "VALUES(?,?,?,?,?,?)",
                (c.id, c.report_id, c.market, c.target_path, c.created_at.isoformat(), c.model_dump_json()),
            )
            await db.commit()

    async def list_corrections(self, *, market: Optional[str] = None, limit: int = 50) -> List[Correction]:
        where = "WHERE market=?" if market else ""
        params: Tuple = (market, limit) if market else (limit,)
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT payload FROM corrections {where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            rows = await cur.fetchall()
        out: List[Correction] = []
        for r in rows:
            try:
                out.append(Correction.model_validate_json(r[0]))
            except Exception:
                continue
        return out

    async def count_corrections_for_report(self, report_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM corrections WHERE report_id=?", (report_id,)
            )
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # ---- 运行注册表（外置） ----
    async def save_run(
        self, *, run_id: str, product: str, market: str, status: str,
        started_at: str, updated_at: str, report_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO runs(run_id, product, market, status, report_id, error, "
                "started_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, product, market, status, report_id, error, started_at, updated_at),
            )
            await db.commit()

    async def update_run(self, run_id: str, *, status: str, updated_at: str,
                         report_id: Optional[str] = None, error: Optional[str] = None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE runs SET status=?, report_id=COALESCE(?, report_id), "
                "error=?, updated_at=? WHERE run_id=?",
                (status, report_id, error, updated_at, run_id),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT run_id, product, market, status, report_id, error, started_at, updated_at "
                "FROM runs WHERE run_id=?", (run_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0], "product": row[1], "market": row[2], "status": row[3],
            "report_id": row[4], "error": row[5], "started_at": row[6], "updated_at": row[7],
        }

    # ---- DAG 检查点（续跑） ----
    async def save_checkpoint(self, *, run_id: str, node: str, seq: int,
                              state_json: str, updated_at: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO run_checkpoints(run_id, node, seq, state, updated_at) "
                "VALUES(?,?,?,?,?)",
                (run_id, node, seq, state_json, updated_at),
            )
            await db.commit()

    async def latest_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT node, seq, state FROM run_checkpoints WHERE run_id=? "
                "ORDER BY seq DESC LIMIT 1", (run_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return {"node": row[0], "seq": row[1], "state": json.loads(row[2])}


@lru_cache(maxsize=1)
def get_store() -> Store:
    settings = get_settings()
    return Store(db_path=str(settings.data_dir / "app.sqlite"))
