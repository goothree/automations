"""
Jira client: fetch issues for the team dashboard.
Uses atlassian-python-api; auth via JIRA_EMAIL + JIRA_API_TOKEN (Jira Cloud).
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

from config import (
    JIRA_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT,
    JIRA_TEAM_JQL,
    JIRA_TEST_SCRIPT_FIELD_ID,
    JIRA_AC_FIELD_ID,
    JIRA_APPROVERS_FIELD_ID,
    TEST_PLAN_SHAREPOINT_FOLDER_URL,
    TEST_PLAN_ONEDRIVE_SYNC_DIR,
    TEST_PLAN_SHAREPOINT_SITE_BASE,
    TEST_PLAN_SHAREPOINT_FOLDER_PATH,
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


def _user_display_name(user):
    if not isinstance(user, dict):
        return ""
    return (user.get("displayName") or user.get("name") or "").strip()


def _extract_approver_names(fields):
    """Read approver display names from the Jira Approvers multi-user field."""
    if not JIRA_APPROVERS_FIELD_ID:
        return ""

    value = (fields or {}).get(JIRA_APPROVERS_FIELD_ID)
    if not isinstance(value, list):
        return ""

    names = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _user_display_name(item)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return ", ".join(names)


def _fetch_jql_issues(client, jql, fields, max_results=None):
    """Fetch issues for a JQL query, paginating through Jira Cloud results."""
    if hasattr(client, "enhanced_jql_get_list_of_tickets"):
        return client.enhanced_jql_get_list_of_tickets(
            jql=jql,
            fields=fields,
            limit=max_results,
        )

    result = client.jql(jql, limit=max_results or 100, fields=fields)
    return result.get("issues") or []


def fetch_issues(max_results=None):
    """
    Fetch issues from Jira for the dashboard.
    Returns list of dicts with: key, summary, status, approvers, priority, due_date, link, type.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}

    jql = (JIRA_TEAM_JQL.strip() if JIRA_TEAM_JQL else _default_jql()).strip()
    if not jql:
        jql = _default_jql()

    fields_request = "summary,status,priority,project,fixVersions"
    if JIRA_APPROVERS_FIELD_ID:
        fields_request += "," + JIRA_APPROVERS_FIELD_ID
    if JIRA_TEST_SCRIPT_FIELD_ID:
        fields_request += "," + JIRA_TEST_SCRIPT_FIELD_ID
    try:
        raw_issues = _fetch_jql_issues(client, jql, fields_request, max_results=max_results)
    except Exception as e:
        err_msg = _error_message(e)
        return {"error": err_msg, "using_team_jql": bool(JIRA_TEAM_JQL and JIRA_TEAM_JQL.strip())}

    total = len(raw_issues)
    try:
        count_result = client.approximate_issue_count(jql)
        if isinstance(count_result, dict) and count_result.get("count") is not None:
            total = int(count_result["count"])
    except Exception:
        pass

    version_release_dates = _fetch_version_release_dates(client)

    out = []
    base_url = JIRA_URL.rstrip("/") + "/browse/"

    for raw in raw_issues:
        key = raw.get("key", "")
        fields = raw.get("fields") or {}
        approvers = _extract_approver_names(fields)
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
            "approvers": approvers,
            "priority": priority.get("name", ""),
            "project": project_key,
            "link": base_url + key,
            "test_script": test_script.strip(),
            "fix_version": fix_version.strip(),
        })
    return {
        "issues": out,
        "total": total,
        "fetched": len(out),
        "using_team_jql": bool(JIRA_TEAM_JQL and JIRA_TEAM_JQL.strip()),
        "jql_length": len(jql),
        "version_release_dates": version_release_dates,
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


def _sharepoint_links_manifest_path():
    return Path(TEST_PLAN_ONEDRIVE_SYNC_DIR) / "_sharepoint_links.json"


def test_plan_sharepoint_file_url(filename):
    """
    Return a SharePoint URL that opens the file in Word Online for editing
    (not a local download). Uses per-file sharing link from manifest if present,
    otherwise builds a direct path URL with ?web=1.
    """
    filename = (filename or "").strip()
    if not filename:
        return ""

    manifest = _sharepoint_links_manifest_path()
    if manifest.exists():
        try:
            links = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(links, dict) and links.get(filename):
                return links[filename].strip()
        except (json.JSONDecodeError, OSError):
            pass

    encoded = quote(filename, safe="")
    return (
        f"{TEST_PLAN_SHAREPOINT_SITE_BASE}/"
        f"{TEST_PLAN_SHAREPOINT_FOLDER_PATH}/{encoded}?web=1"
    )


def _adf_doc(*paragraphs):
    return {"type": "doc", "version": 1, "content": list(paragraphs)}


def _adf_paragraph(*inline_nodes):
    return {"type": "paragraph", "content": list(inline_nodes)}


def _adf_text(text, link_href=None):
    node = {"type": "text", "text": text}
    if link_href:
        node["marks"] = [{"type": "link", "attrs": {"href": link_href}}]
    return node


def add_issue_comment(issue_key, body):
    """
    Add a comment to a Jira issue. body may be plain text (str) or ADF (dict).
    Returns {"success": True, "comment_id": ...} or {"error": "..."}.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    issue_key = issue_key.strip().upper()
    try:
        if isinstance(body, str):
            payload = _adf_doc(_adf_paragraph(_adf_text(body)))
        elif isinstance(body, dict):
            payload = body
        else:
            return {"error": "Comment body must be a string or ADF document."}
        base_url = client.resource_url("issue")
        url = f"{base_url}/{issue_key}/comment"
        result = client.post(url, data={"body": payload})
        comment_id = (result or {}).get("id")
        return {"success": True, "comment_id": comment_id}
    except Exception as e:
        return {"error": _error_message(e)}


def add_test_plan_jira_comment(issue_key, filename):
    """
    Post a Jira comment linking to the test plan .docx in SharePoint.
    Returns {"success": True, "file_url": ...} or {"error": "..."}.
    """
    if not filename or not filename.strip():
        return {"error": "Test plan filename is required."}
    filename = filename.strip()
    file_url = test_plan_sharepoint_file_url(filename)
    body = _adf_doc(
        _adf_paragraph(
            _adf_text("Test plan: "),
            _adf_text(filename, file_url),
        ),
    )
    result = add_issue_comment(issue_key, body)
    if result.get("error"):
        return result
    return {
        "success": True,
        "comment_id": result.get("comment_id"),
        "file_url": file_url,
    }


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


RELEASE_PROJECTS = ("IDA", "RDAR")

RELEASE_STATUS_QA = ("In QA", "In Testing")
RELEASE_STATUS_IN_WORK = (
    "Scheduled / In Progress",
    "In Review",
    "Ready for Development",
    "Review Completed",
    "Re Opened",
    "Reopened",
)
RELEASE_STATUS_BACKLOG = ("Backlog", "Gathering Requirements")
RELEASE_STATUS_BLOCKED = ("Blocked / On-Hold", "BLOCKED", "Blocked")

RELEASE_COUNT_METRICS = (
    ("total", None),
    ("qa", RELEASE_STATUS_QA),
    ("in_work", RELEASE_STATUS_IN_WORK),
    ("backlog", RELEASE_STATUS_BACKLOG),
    ("blocked", RELEASE_STATUS_BLOCKED),
)


def _jql_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _release_count(client, project_key, version_name, statuses=None):
    """Return approximate Jira issue count for a project fix version and optional statuses."""
    jql = f"project = {project_key} AND fixVersion = {_jql_quote(version_name)}"
    if statuses:
        status_list = ", ".join(_jql_quote(status) for status in statuses)
        jql = f"{jql} AND status IN ({status_list})"
    try:
        result = client.approximate_issue_count(jql)
        if isinstance(result, dict) and result.get("count") is not None:
            return int(result["count"])
    except Exception:
        pass
    return None


def _attach_release_counts(client, releases):
    """Add total/qa/in_work/backlog/blocked counts to each release."""
    if not releases:
        return releases

    counts = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(
                _release_count,
                client,
                release["project"],
                release["name"],
                statuses,
            ): (release["project"], release["name"], metric)
            for release in releases
            for metric, statuses in RELEASE_COUNT_METRICS
        }
        for future in as_completed(futures):
            project_key, version_name, metric = futures[future]
            try:
                counts[(project_key, version_name, metric)] = future.result()
            except Exception:
                counts[(project_key, version_name, metric)] = None

    for release in releases:
        key_base = (release["project"], release["name"])
        release["total"] = counts.get((*key_base, "total"))
        release["qa"] = counts.get((*key_base, "qa"))
        release["in_work"] = counts.get((*key_base, "in_work"))
        release["backlog"] = counts.get((*key_base, "backlog"))
        release["blocked"] = counts.get((*key_base, "blocked"))
        # Backwards compatibility for any callers still using issue_count.
        release["issue_count"] = release["total"]
    return releases


def _fetch_version_release_dates(client):
    """Map project-prefixed version key (e.g. IDA-v2026-07) to release date."""
    dates = {}
    for project_key in RELEASE_PROJECTS:
        try:
            versions = client.get_project_versions(project_key) or []
        except Exception:
            continue
        for version in versions:
            if not isinstance(version, dict):
                continue
            name = (version.get("name") or "").strip()
            if not name:
                continue
            dates[f"{project_key}-{name}"] = version.get("releaseDate") or ""
    return dates


def fetch_unreleased_releases():
    """
    Fetch unreleased, non-archived versions from IDA and RDAR.
    Returns releases sorted by release date descending (newest first); undated releases last.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}

    releases = []
    base_url = JIRA_URL.rstrip("/")

    for project_key in RELEASE_PROJECTS:
        try:
            versions = client.get_project_versions(project_key) or []
        except Exception as e:
            return {"error": _error_message(e)}

        for version in versions:
            if not isinstance(version, dict):
                continue
            if version.get("released") or version.get("archived"):
                continue
            version_id = version.get("id")
            name = (version.get("name") or "").strip()
            release_date = version.get("releaseDate") or ""
            link = f"{base_url}/projects/{project_key}/versions/{version_id}" if version_id else ""
            releases.append({
                "project": project_key,
                "name": name or "(unnamed)",
                "release_date": release_date,
                "link": link,
            })

    _attach_release_counts(client, releases)

    releases.sort(
        key=lambda release: (
            release["release_date"] or "",
            release["name"].lower(),
        ),
        reverse=True,
    )
    return {"releases": releases, "total": len(releases)}


def fetch_calendar_releases():
    """
    Fetch non-archived IDA and RDAR versions with a release date for the calendar.
    Includes both released and unreleased versions.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}

    releases = []
    base_url = JIRA_URL.rstrip("/")

    for project_key in RELEASE_PROJECTS:
        try:
            versions = client.get_project_versions(project_key) or []
        except Exception as e:
            return {"error": _error_message(e)}

        for version in versions:
            if not isinstance(version, dict):
                continue
            if version.get("archived"):
                continue
            release_date = (version.get("releaseDate") or "").strip()
            if not release_date:
                continue
            version_id = version.get("id")
            name = (version.get("name") or "").strip() or "(unnamed)"
            link = f"{base_url}/projects/{project_key}/versions/{version_id}" if version_id else ""
            releases.append({
                "id": f"jira-{project_key}-{version_id or name}",
                "source": "jira",
                "project": project_key,
                "title": name,
                "date": release_date,
                "released": bool(version.get("released")),
                "link": link,
            })

    releases.sort(key=lambda release: (release["date"], release["project"], release["title"].lower()))
    return {"releases": releases, "total": len(releases)}
