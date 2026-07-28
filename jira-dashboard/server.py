"""
Jira Team Dashboard – Flask backend.
Fetches issues from Jira and serves a simple dashboard.
Run from project root: ./run_jira_dashboard  or  python jira-dashboard/server.py
"""
import os
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS

from jira_client import (
    fetch_issues,
    fetch_unreleased_releases,
    fetch_calendar_releases,
    get_issue_full,
    get_issue_transitions,
    set_issue_transition,
)
from calendar_store import (
    list_custom_events,
    create_custom_event,
    update_custom_event,
    delete_custom_event,
)
from config import is_configured
STATIC_DIR = DASHBOARD_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
CORS(app)


def _html_response(filename):
    response = make_response(send_from_directory(STATIC_DIR, filename))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/api/status")
def status():
    """Return whether Jira is configured."""
    return jsonify({"configured": is_configured()})


@app.route("/api/issues")
def issues():
    """Return issues from Jira (team / project / default JQL)."""
    result = fetch_issues()
    if "error" in result:
        # Log so it appears in terminal when running the server
        print("Jira API error:", result["error"], file=sys.stderr)
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/issues/<issue_key>")
def issue_detail(issue_key):
    """Return a single issue with summary and description for the dashboard expand."""
    result = get_issue_full(issue_key)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/issues/<issue_key>/transitions")
def issue_transitions(issue_key):
    """Return available workflow transitions for an issue (for status change dropdown)."""
    result = get_issue_transitions(issue_key)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/issues/<issue_key>/transition", methods=["POST"])
def issue_do_transition(issue_key):
    """Execute a workflow transition (e.g. change status). Body: {"transition_id": 123}."""
    data = request.get_json() or {}
    transition_id = data.get("transition_id")
    if transition_id is None:
        return jsonify({"error": "transition_id is required"}), 400
    try:
        transition_id = int(transition_id)
    except (TypeError, ValueError):
        return jsonify({"error": "transition_id must be a number"}), 400
    result = set_issue_transition(issue_key, transition_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/releases")
def releases():
    """Return unreleased versions from IDA and RDAR, newest release date first."""
    result = fetch_unreleased_releases()
    if "error" in result:
        print("Jira releases API error:", result["error"], file=sys.stderr)
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/calendar")
def calendar_data():
    """Return Jira release dates and custom calendar events."""
    releases = fetch_calendar_releases()
    if "error" in releases:
        print("Jira calendar API error:", releases["error"], file=sys.stderr)
        return jsonify(releases), 500
    response = jsonify({
        "releases": releases.get("releases", []),
        "custom": list_custom_events(),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/api/calendar/custom", methods=["POST"])
def calendar_create_custom():
    result = create_custom_event(request.get_json(silent=True) or {})
    if "error" in result:
        return jsonify(result), 400
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response, 201


@app.route("/api/calendar/custom/<event_id>", methods=["PUT"])
def calendar_update_custom(event_id):
    result = update_custom_event(event_id, request.get_json(silent=True) or {})
    if "error" in result:
        status = 404 if result["error"] == "Event not found" else 400
        return jsonify(result), status
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/calendar/custom/<event_id>", methods=["DELETE"])
def calendar_delete_custom(event_id):
    result = delete_custom_event(event_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/releases")
def releases_page():
    return _html_response("releases.html")


@app.route("/calendar")
def calendar_page():
    return _html_response("calendar.html")


@app.route("/")
def index():
    return _html_response("index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5557))
    print(f"Jira Team Dashboard: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
