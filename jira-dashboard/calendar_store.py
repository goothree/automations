"""Persist custom calendar events for the dashboard calendar page."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
EVENTS_FILE = DATA_DIR / "calendar_events.json"
ALLOWED_PRIORITIES = frozenset({"High", "Medium", "Low"})
ALLOWED_PROJECTS = frozenset({"IDA", "RDAR"})


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text(json.dumps({"events": []}, indent=2) + "\n", encoding="utf-8")


def _load_raw():
    _ensure_store()
    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"events": []}
    if not isinstance(data, dict):
        data = {"events": []}
    events = data.get("events")
    if not isinstance(events, list):
        events = []
    return events


def _save(events):
    _ensure_store()
    EVENTS_FILE.write_text(
        json.dumps({"events": events}, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_priority(value):
    if value is None:
        return None
    priority = str(value).strip()
    if not priority:
        return None
    if priority not in ALLOWED_PRIORITIES:
        return None
    return priority


def _normalize_project(value):
    if value is None:
        return None
    project = str(value).strip().upper()
    if not project:
        return None
    if project not in ALLOWED_PROJECTS:
        return None
    return project


def _normalize_event(event):
    if not isinstance(event, dict):
        return None
    title = (event.get("title") or "").strip()
    date = (event.get("date") or "").strip()
    if not title or not date:
        return None
    end_date = (event.get("end_date") or "").strip() or None
    notes = (event.get("notes") or "").strip()
    priority = _normalize_priority(event.get("priority"))
    project = _normalize_project(event.get("project"))
    return {
        "id": (event.get("id") or str(uuid.uuid4())).strip(),
        "title": title,
        "date": date,
        "end_date": end_date,
        "notes": notes,
        "priority": priority,
        "project": project,
        "created_at": event.get("created_at") or _now_iso(),
        "updated_at": event.get("updated_at") or _now_iso(),
    }


def list_custom_events():
    events = []
    for raw in _load_raw():
        normalized = _normalize_event(raw)
        if normalized:
            events.append(normalized)
    events.sort(key=lambda item: (item["date"], item["title"].lower()))
    return events


def create_custom_event(payload):
    event = _normalize_event(payload or {})
    if not event:
        return {"error": "title and date are required"}
    now = _now_iso()
    event["created_at"] = now
    event["updated_at"] = now
    raw_events = _load_raw()
    raw_events.append(event)
    _save(raw_events)
    return {"event": event}


def update_custom_event(event_id, payload):
    raw_events = _load_raw()
    target = None
    for index, event in enumerate(raw_events):
        if isinstance(event, dict) and event.get("id") == event_id:
            target = index
            break
    if target is None:
        return {"error": "Event not found"}

    merged = {**raw_events[target], **(payload or {})}
    merged["id"] = event_id
    merged["created_at"] = raw_events[target].get("created_at")
    normalized = _normalize_event(merged)
    if not normalized:
        return {"error": "title and date are required"}
    normalized["updated_at"] = _now_iso()
    raw_events[target] = normalized
    _save(raw_events)
    return {"event": normalized}


def delete_custom_event(event_id):
    raw_events = _load_raw()
    remaining = [
        event for event in raw_events
        if not (isinstance(event, dict) and event.get("id") == event_id)
    ]
    if len(remaining) == len(raw_events):
        return {"error": "Event not found"}
    _save(remaining)
    return {"success": True}
