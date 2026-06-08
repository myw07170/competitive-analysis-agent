"""Role-targeted rework routing + per-competitor note slicing (P0-1, P1-5)."""
from __future__ import annotations

from app.orchestration.graph import (
    _collector_notes_for,
    _flagged_collector_labels,
    _role_notes,
    _route_after_qc,
)
from app.schema import AgentRole


def _f(agent, severity, path, issue="i", fix="f"):
    return {"target_agent": agent, "severity": severity, "target_path": path,
            "issue": issue, "suggested_fix": fix}


def _qc(decision, findings):
    return {"decision": decision, "findings": findings}


def test_approve_routes_done():
    assert _route_after_qc({"last_qc": _qc("approve", []), "iteration": 0}) == "done"


def test_collector_major_routes_collect():
    st = {"last_qc": _qc("rework", [_f("collector", "major", "competitors[0].sources")]),
          "iteration": 1}
    assert _route_after_qc(st) == "collect"


def test_analyst_only_routes_analyze():
    st = {"last_qc": _qc("rework", [_f("analyst", "major", "competitors[0].swot")]),
          "iteration": 1}
    assert _route_after_qc(st) == "analyze"


def test_writer_only_routes_write():
    st = {"last_qc": _qc("rework", [_f("writer", "major", "report.executive_summary_md")]),
          "iteration": 1}
    assert _route_after_qc(st) == "write"


def test_earliest_stage_wins_when_multiple_agents():
    st = {"last_qc": _qc("rework", [
        _f("writer", "major", "report.sections"),
        _f("collector", "major", "competitors[0].sources"),
    ]), "iteration": 1}
    assert _route_after_qc(st) == "collect"


def test_minor_only_does_not_force_specific_stage_but_still_routes():
    # decision=="rework" implies a severe finding existed; minor-only collector
    # path still resolves to a stage (collector fallback).
    st = {"last_qc": _qc("rework", [_f("collector", "minor", "competitors[0].sources")]),
          "iteration": 1}
    assert _route_after_qc(st) == "collect"


def test_iteration_cap_routes_done():
    st = {"last_qc": _qc("rework", [_f("collector", "major", "x")]), "iteration": 99}
    assert _route_after_qc(st) == "done"


def test_flagged_collector_labels():
    qc = _qc("rework", [
        _f("collector", "major", "competitors[1].pricing.tiers"),
        _f("collector", "minor", "target_product.sources"),
        _f("analyst", "major", "competitors[0].swot"),  # not a collector label
    ])
    labels = _flagged_collector_labels(qc)
    assert labels == {"competitors[1]", "target_product"}


def test_collector_notes_are_sliced_per_competitor():
    qc = _qc("rework", [
        _f("collector", "major", "competitors[0].sources", issue="too few"),
        _f("collector", "major", "competitors[1].pricing", issue="no price"),
    ])
    n0 = _collector_notes_for(qc, "competitors[0]")
    assert "competitors[0].sources" in n0
    assert "competitors[1]" not in n0


def test_role_notes_filters_by_agent():
    qc = _qc("rework", [
        _f("analyst", "major", "competitors[0].swot", issue="missing swot"),
        _f("collector", "major", "competitors[0].sources"),
    ])
    notes = _role_notes(qc, AgentRole.ANALYST)
    assert "missing swot" in notes
    assert "sources" not in notes
