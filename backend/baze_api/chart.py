"""The flow document and the medical record. Hermes proposes them. This module stores them."""

from __future__ import annotations

import json
import logging
import re

from baze_api.db import apps
from baze_api.http import new_id, now_ms
from baze_api.settings import Settings

log = logging.getLogger("baze.chart")

FLOW_KINDS = {"person", "page", "store", "file", "outside"}
ENTRY_KINDS = {"changed", "containment", "decision"}
_NODE_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
CHART_ASK = (
    "Reply with one JSON object and nothing else. "
    "Keys are flow and entries. "
    "flow.nodes is a list of objects with id, label, and kind. "
    "kind is one of person, page, store, file, outside. "
    "flow.edges is a list of objects with from and to. "
    "entries is a list of new lines only, each with kind and summary. "
    "kind is changed or containment. "
    "Describe what the app does now and where it keeps things. "
    "Add a containment line only when something reached outside the box or a package should not be trusted. "
    "Do not change any files."
)


def note_created(settings: Settings, app_id: str, summary: str) -> None:
    document = apps(settings).find_one({"_id": app_id}, {"createdAt": 1, "chart.record": 1})
    if document is None:
        return
    record = (document.get("chart") or {}).get("record") or []
    if any(entry.get("kind") == "created" for entry in record):
        return
    at = document.get("createdAt")
    apps(settings).update_one(
        {"_id": app_id},
        {
            "$push": {
                "chart.record": {
                    "id": new_id(),
                    "kind": "created",
                    "summary": _summary(summary) or "The app was created.",
                    "at": at if isinstance(at, int) else now_ms(),
                }
            }
        },
    )


def parse_chart(text: str) -> dict | None:
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value


def apply_chart(settings: Settings, app_id: str, proposal: dict) -> None:
    """Save a valid flow in one replacement, and append valid record lines."""
    if not isinstance(proposal, dict) or apps(settings).find_one({"_id": app_id}, {"_id": 1}) is None:
        return
    if "flow" in proposal:
        flow = _clean_flow(proposal.get("flow"))
        if flow is not None:
            apps(settings).update_one({"_id": app_id}, {"$set": {"chart.flow": flow}})
    entries = _clean_entries(proposal.get("entries"))
    if entries:
        apps(settings).update_one({"_id": app_id}, {"$push": {"chart.record": {"$each": entries}}})


def ask_chart(settings: Settings, app_id: str, hermes, *, base_url: str, api_key: str, session_id: str | None) -> None:
    """Ask the harness for the chart. A bad reply leaves the stored chart alone."""
    try:
        reply, session = hermes.complete(
            base_url=base_url,
            api_key=api_key,
            content=CHART_ASK,
            session_id=session_id,
        )
    except Exception:
        log.info("Chart was not written for %s", app_id)
        return
    if session:
        apps(settings).update_one({"_id": app_id}, {"$set": {"chat.hermesSessionId": session}})
    proposal = parse_chart(reply)
    if proposal is None:
        return
    proposal.pop("entries", None)
    apply_chart(settings, app_id, proposal)


def public_chart(document: dict) -> tuple[dict, list[dict]]:
    chart = document.get("chart") or {}
    flow = chart.get("flow") if isinstance(chart.get("flow"), dict) else {}
    nodes = flow.get("nodes") if isinstance(flow.get("nodes"), list) else []
    edges = flow.get("edges") if isinstance(flow.get("edges"), list) else []
    record = chart.get("record") if isinstance(chart.get("record"), list) else []
    lines = []
    for entry in record:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        summary = entry.get("summary")
        if kind not in {"created", "changed", "containment", "decision"} or not isinstance(summary, str):
            continue
        line = {
            "id": entry.get("id") or "",
            "kind": kind,
            "summary": summary,
            "at": entry.get("at") if isinstance(entry.get("at"), int) else 0,
        }
        detail = entry.get("detail")
        if isinstance(detail, str) and detail.strip():
            line["detail"] = detail.strip()
        lines.append(line)
    lines.sort(key=lambda entry: entry["at"])
    return {"nodes": nodes, "edges": edges}, lines


def _clean_flow(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    nodes_in = value.get("nodes")
    edges_in = value.get("edges")
    if not isinstance(nodes_in, list) or not isinstance(edges_in, list) or not nodes_in:
        return None
    nodes = []
    seen: set[str] = set()
    for node in nodes_in[:12]:
        if not isinstance(node, dict):
            return None
        node_id = node.get("id")
        label = _label(node.get("label"))
        kind = node.get("kind")
        if not isinstance(node_id, str) or _NODE_ID.match(node_id) is None or not label or kind not in FLOW_KINDS:
            return None
        if node_id in seen:
            return None
        seen.add(node_id)
        nodes.append({"id": node_id, "label": label, "kind": kind})
    edges = []
    for edge in edges_in[:16]:
        if not isinstance(edge, dict):
            return None
        source = edge.get("from")
        target = edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str) or source not in seen or target not in seen:
            return None
        edges.append({"from": source, "to": target})
    return {"nodes": nodes, "edges": edges}


def _clean_entries(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    stamp = now_ms()
    cleaned = []
    for index, entry in enumerate(value[:8]):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        summary = _summary(entry.get("summary"))
        if kind not in ENTRY_KINDS or not summary:
            continue
        cleaned.append({"id": new_id(), "kind": kind, "summary": summary, "at": stamp + index})
        detail = entry.get("detail")
        if kind == "decision" and isinstance(detail, str) and detail.strip():
            cleaned[-1]["detail"] = detail.strip()[:2000]
    return cleaned


def _label(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:80]


def _summary(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:240]
