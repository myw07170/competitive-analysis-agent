"""Cross-run knowledge diff (Innovation-3)."""
from __future__ import annotations

from app.knowledge import compute_diff


def _snap(payload, run_id="r", t="2026-01-01T00:00:00"):
    return {"run_id": run_id, "captured_at": t, "payload": payload}


def test_first_snapshot_has_no_diff():
    latest = _snap({"name": "X"})
    d = compute_diff(entity_key="us:x", name="X", market="us", latest=latest, previous=None)
    assert d.summary == "first_snapshot"
    assert d.changes == []


def test_pricing_change_detected():
    prev = _snap({"name": "X", "pricing": {"tiers": [
        {"name": "Pro", "monthly_price": 10, "currency": "USD"}]}}, run_id="r1")
    latest = _snap({"name": "X", "pricing": {"tiers": [
        {"name": "Pro", "monthly_price": 12, "currency": "USD"}]}}, run_id="r2")
    d = compute_diff(entity_key="us:x", name="X", market="us", latest=latest, previous=prev)
    assert any(c.change == "changed" and "Pro" in c.path for c in d.changes)


def test_added_and_removed_capabilities():
    prev = _snap({"name": "X", "function_tree": {"root_name": "r", "nodes": [
        {"name": "Docs"}, {"name": "Legacy"}]}}, run_id="r1")
    latest = _snap({"name": "X", "function_tree": {"root_name": "r", "nodes": [
        {"name": "Docs"}, {"name": "AI"}]}}, run_id="r2")
    d = compute_diff(entity_key="us:x", name="X", market="us", latest=latest, previous=prev)
    changes = {(c.change, c.path) for c in d.changes}
    assert ("added", "function.AI") in changes
    assert ("removed", "function.Legacy") in changes


def test_market_position_change():
    prev = _snap({"name": "X", "market_position": "SMB"}, run_id="r1")
    latest = _snap({"name": "X", "market_position": "Enterprise"}, run_id="r2")
    d = compute_diff(entity_key="us:x", name="X", market="us", latest=latest, previous=prev)
    assert any(c.path == "market_position" and c.after == "Enterprise" for c in d.changes)
