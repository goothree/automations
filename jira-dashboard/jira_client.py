"""
Jira client: fetch issues for the team dashboard.
Uses atlassian-python-api; auth via JIRA_EMAIL + JIRA_API_TOKEN (Jira Cloud).
"""
from config import (
    JIRA_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT,
    JIRA_TEAM_JQL,
    JIRA_TEST_SCRIPT_FIELD_ID,
    JIRA_AC_FIELD_ID,
    is_configured,
)


def _error_message(e):
    """Extract a clear error message from a Jira/requests exception."""
    msg = str(e).strip()
    if hasattr(e, "response") and e.response is not None:
        try:
            body = e.response.json()
            if isinstance(body, dict):
                # Jira API returns errorMessages or errors
                msgs = body.get("errorMessages") or []
                if msgs:
                    return "; ".join(str(m) for m in msgs)
                errs = body.get("errors")
                if errs:
                    return str(errs)
        except Exception:
            pass
        text = getattr(e.response, "text", None)
        if text and isinstance(text, str) and text.strip():
            return text.strip()[:600]
        code = getattr(e.response, "status_code", None)
        if code == 401:
            return "Unauthorized: check JIRA_EMAIL and JIRA_API_TOKEN in .env"
        if code == 403:
            return "Forbidden: your account may not have permission to search issues"
        if code == 400:
            return "Bad request (invalid JQL?): " + (msg or "Check your JIRA_TEAM_JQL syntax")
    return msg or "Request failed"


def _get_client():
    if not is_configured():
        return None
    from atlassian import Jira
    # Jira Cloud: Basic Auth with email + API token. Use API v3 (v2 search was removed by Atlassian).
    return Jira(
        url=JIRA_URL,
        username=JIRA_EMAIL,
        password=JIRA_API_TOKEN,
        cloud=True,
        api_version="3",
    )


def _default_jql():
    """Default JQL: open issues, optionally scoped to project."""
    base = "resolution = Unresolved ORDER BY updated DESC"
    if JIRA_PROJECT:
        return f"project = {JIRA_PROJECT} AND {base}"
    return base


def fetch_issues(max_results=100):
    """
    Fetch issues from Jira for the dashboard.
    Returns list of dicts with: key, summary, status, assignee, priority, due_date, link, type.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}

    jql = (JIRA_TEAM_JQL.strip() if JIRA_TEAM_JQL else _default_jql()).strip()
    if not jql:
        jql = _default_jql()

    fields_request = "summary,status,assignee,priority,project,fixVersions"
    if JIRA_TEST_SCRIPT_FIELD_ID:
        fields_request += "," + JIRA_TEST_SCRIPT_FIELD_ID
    try:
        result = client.jql(jql, limit=max_results, fields=fields_request)
    except Exception as e:
        err_msg = _error_message(e)
        return {"error": err_msg, "using_team_jql": bool(JIRA_TEAM_JQL and JIRA_TEAM_JQL.strip())}

    raw_issues = result.get("issues") or []
    out = []
    base_url = JIRA_URL.rstrip("/") + "/browse/"

    for raw in raw_issues:
        key = raw.get("key", "")
        fields = raw.get("fields") or {}
        assignee = fields.get("assignee")
        assignee_name = assignee.get("displayName", "") if assignee else "Unassigned"
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}
        project = fields.get("project") or {}
        project_key = project.get("key", "")
        test_script = fields.get(JIRA_TEST_SCRIPT_FIELD_ID) or ""
        if not isinstance(test_script, str):
            test_script = str(test_script)
        fix_versions = fields.get("fixVersions") or []
        fix_version = ", ".join((v.get("name") or "") for v in fix_versions if isinstance(v, dict))
        out.append({
            "key": key,
            "summary": fields.get("summary", ""),
            "status": status.get("name", ""),
            "assignee": assignee_name,
            "priority": priority.get("name", ""),
            "project": project_key,
            "link": base_url + key,
            "test_script": test_script.strip(),
            "fix_version": fix_version.strip(),
        })
    return {
        "issues": out,
        "total": result.get("total", len(out)),
        "using_team_jql": bool(JIRA_TEAM_JQL and JIRA_TEAM_JQL.strip()),
        "jql_length": len(jql),
    }


def get_issue_full(issue_key):
    """
    Fetch a single Jira issue with full fields for test generation.
    Returns dict with key, summary, description (plain text), subtasks (list of summary strings),
    and optionally acceptance_criteria if present in a common custom field.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    issue_key = issue_key.strip().upper()
    try:
        raw = client.issue(issue_key, fields="*all")
        if not raw or "fields" not in raw:
            return {"error": f"Issue {issue_key} not found."}
        fields = raw.get("fields") or {}
        summary = fields.get("summary") or ""
        desc = fields.get("description")
        if desc and isinstance(desc, dict):
            description = _description_to_plain(desc)
        else:
            description = (desc or "") if isinstance(desc, str) else ""
        # Subtasks: list of summary strings for use in test generation
        subtasks = _extract_subtask_summaries(fields.get("subtasks"))
        # Acceptance criteria: try common custom field names (some Jira setups use these)
        acceptance_criteria = _extract_acceptance_criteria(fields)
        return {
            "key": raw.get("key", issue_key),
            "summary": summary,
            "description": description,
            "subtasks": subtasks,
            "acceptance_criteria": acceptance_criteria,
        }
    except Exception as e:
        return {"error": str(e)}


def _extract_subtask_summaries(subtasks_field):
    """Return list of subtask summary strings from Jira subtasks field."""
    out = []
    for item in (subtasks_field or []):
        if not isinstance(item, dict):
            continue
        f = item.get("fields") or {}
        s = (f.get("summary") or "").strip()
        if s:
            out.append(s)
    return out


def _extract_acceptance_criteria(fields):
    """Extract acceptance criteria from configured custom field or description. Returns plain text or ''."""
    if JIRA_AC_FIELD_ID:
        value = (fields or {}).get(JIRA_AC_FIELD_ID)
        if value is not None and value != "":
            if isinstance(value, dict):
                return _description_to_plain(value).strip()
            if isinstance(value, str):
                return value.strip()
    for key, value in (fields or {}).items():
        if not key or not value:
            continue
        key_lower = key.lower()
        if "acceptance" in key_lower and "criteria" in key_lower:
            if isinstance(value, dict):
                return _description_to_plain(value).strip()
            if isinstance(value, str):
                return value.strip()
    return ""


def _description_to_plain(node):
    """Recursively convert Jira ADF description to plain text."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text" and "text" in node:
        return node["text"]
    content = node.get("content") or []
    parts = [_description_to_plain(c) for c in content]
    # Add newline after block nodes (paragraph, heading, listItem) for readability
    block_types = {"paragraph", "heading", "listItem", "bulletList", "orderedList"}
    if node.get("type") in block_types and parts:
        return "".join(parts) + "\n"
    return "".join(parts)


def set_test_script_url(issue_key, script_url):
    """
    Set the Test Script custom field on a Jira issue to the given URL.
    Returns {"success": True} or {"error": "..."}.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not JIRA_TEST_SCRIPT_FIELD_ID:
        return {"error": "JIRA_TEST_SCRIPT_FIELD_ID is not set."}
    if not issue_key or not script_url:
        return {"error": "Issue key and script URL are required."}
    try:
        client.issue_update(issue_key.strip(), {JIRA_TEST_SCRIPT_FIELD_ID: script_url})
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


def get_issue_transitions(issue_key):
    """
    Get available workflow transitions for an issue (e.g. for status change dropdown).
    Returns {"transitions": [{"id": 21, "name": "In Progress", "to": "In Progress"}, ...]} or {"error": "..."}.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    try:
        raw = client.get_issue_transitions(issue_key.strip())
        transitions = [
            {"id": t["id"], "name": t["name"], "to": t["to"]}
            for t in (raw or [])
        ]
        return {"transitions": transitions}
    except Exception as e:
        return {"error": _error_message(e)}


def set_issue_transition(issue_key, transition_id):
    """
    Execute a workflow transition on an issue (e.g. change status).
    Returns {"success": True, "to": "Done"} or {"error": "..."}.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    try:
        client.set_issue_status_by_transition_id(issue_key.strip(), transition_id)
        return {"success": True}
    except Exception as e:
        return {"error": _error_message(e)}
