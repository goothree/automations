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

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from jira_client import fetch_issues, get_issue_full, get_issue_transitions, set_issue_transition
from config import is_configured, is_jira_to_testpad_configured
from jira_to_testpad import run as run_jira_to_testpad
STATIC_DIR = DASHBOARD_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
CORS(app)


@app.route("/api/status")
def status():
    """Return whether Jira and Jira→Testpad are configured."""
    return jsonify({
        "configured": is_configured(),
        "jira_to_testpad_configured": is_jira_to_testpad_configured(),
    })


@app.route("/api/issues")
def issues():
    """Return issues from Jira (team / project / default JQL)."""
    result = fetch_issues(max_results=200)
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


@app.route("/api/jira-to-testpad", methods=["POST"])
def jira_to_testpad():
    """Create Testpad script from selected Jira issue and set Test Script field."""
    if not is_jira_to_testpad_configured():
        return jsonify({"success": False, "error": "Jira→Testpad not configured. Set JIRA_TEST_SCRIPT_FIELD_ID, Testpad, and OPENAI_API_KEY in .env"}), 400
    data = request.get_json() or {}
    issue_key = (data.get("issue_key") or "").strip()
    if not issue_key:
        return jsonify({"success": False, "error": "issue_key is required"}), 400
    result = run_jira_to_testpad(issue_key)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    os.chdir(DASHBOARD_DIR)
    port = int(os.environ.get("PORT", 5557))
    print(f"Jira Team Dashboard: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
