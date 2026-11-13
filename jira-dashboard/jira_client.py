"""
Jira client: fetch issues for the team dashboard.
Uses atlassian-python-api; auth via JIRA_EMAIL + JIRA_API_TOKEN (Jira Cloud).
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote

from config import (
    JIRA_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT,
    JIRA_DEFAULT_QUEUE,
    JIRA_TEAM_JQL,
    JIRA_TEST_SCRIPT_FIELD_ID,
    JIRA_AC_FIELD_ID,
    JIRA_APPROVERS_FIELD_ID,
    JIRA_ORG_ID,
    JIRA_QA_TEAM_NAME,
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
    """QA queue: IDA in QA, RDAR in testing, and open issues in the QA project."""
    if JIRA_PROJECT:
        return f"project = {JIRA_PROJECT} AND resolution = Unresolved ORDER BY updated DESC"
    parts = [f"(project = {key} AND {condition})" for key, condition in JIRA_DEFAULT_QUEUE]
    return f"({' OR '.join(parts)}) ORDER BY updated DESC"


def _user_display_name(user):
    if not isinstance(user, dict):
        return ""
    return (user.get("displayName") or user.get("name") or "").strip()


def _user_brief(user):
    """Return {accountId, name} for a Jira user, or None."""
    if not isinstance(user, dict):
        return None
    account_id = (user.get("accountId") or "").strip()
    name = _user_display_name(user)
    if not account_id or not name or user.get("active") is False:
        return None
    return {"accountId": account_id, "name": name}


# RDAR and QA do not use Approvers. Show the Jira assignee for those projects.
_ASSIGNEE_PROJECTS = {"RDAR", "QA"}


def _assignment_mode(project_key):
    """RDAR and QA edit the assignee. Other projects edit Approvers."""
    if (project_key or "").upper() in _ASSIGNEE_PROJECTS:
        return "assignee"
    return "approvers"


def _assigned_users(project_key, fields):
    """People currently shown in the Assigned column, with Jira account ids."""
    fields = fields or {}
    if _assignment_mode(project_key) == "assignee":
        user = _user_brief(fields.get("assignee"))
        return [user] if user else []

    users = []
    seen = set()
    for item in fields.get(JIRA_APPROVERS_FIELD_ID) or []:
        user = _user_brief(item)
        if not user or user["accountId"] in seen:
            continue
        seen.add(user["accountId"])
        users.append(user)
    return users


def _fetch_jql_issues(client, jql, fields, max_results=None):
    """Fetch one bounded page of Jira issues.

    Omitting a limit makes the Cloud client walk every page. The default queue
    is about a hundred issues; the cap stays above that so a wider custom JQL
    cannot stall the page.
    """
    limit = 500 if max_results is None else max_results
    if hasattr(client, "enhanced_jql_get_list_of_tickets"):
        return client.enhanced_jql_get_list_of_tickets(
            jql=jql,
            fields=fields,
            limit=limit,
        )

    result = client.jql(jql, limit=limit, fields=fields)
    return result.get("issues") or []


def _site_id(client):
    info = client.get("_edge/tenant_info")
    if isinstance(info, dict):
        return (info.get("cloudId") or "").strip()
    return ""


def _qa_team_id(client, site_id):
    """Return the Atlassian team id whose display name matches JIRA_QA_TEAM_NAME."""
    target = JIRA_QA_TEAM_NAME.casefold()
    if not target or not JIRA_ORG_ID or not site_id:
        return ""
    cursor = None
    seen_cursors = set()
    while True:
        params = {"siteId": site_id}
        if cursor:
            params["cursor"] = cursor
        page = client.get(f"gateway/api/public/teams/v1/org/{JIRA_ORG_ID}/teams", params=params)
        if not isinstance(page, dict):
            return ""
        for team in page.get("entities") or []:
            name = (team.get("displayName") or "").strip()
            if name.casefold() == target:
                return (team.get("teamId") or "").strip()
        cursor = page.get("cursor")
        if not cursor or cursor in seen_cursors:
            return ""
        seen_cursors.add(cursor)


def _qa_team_account_ids(client, site_id, team_id):
    path = f"gateway/api/public/teams/v1/org/{JIRA_ORG_ID}/teams/{team_id}/members"
    response = client.request(
        "POST",
        path,
        params={"siteId": site_id},
        data={},
    )
    page = json.loads(response.text or "{}")
    account_ids = []
    for member in page.get("results") or []:
        account_id = (member.get("accountId") or "").strip()
        if account_id:
            account_ids.append(account_id)
    return account_ids


def _users_by_account_ids(client, account_ids):
    users = []
    for start in range(0, len(account_ids), 10):
        chunk = account_ids[start:start + 10]
        result = client.get(
            "rest/api/3/user/bulk",
            params=[("accountId", account_id) for account_id in chunk],
        )
        for user in (result or {}).get("values") or []:
            brief = _user_brief(user)
            if brief:
                users.append(brief)
    users.sort(key=lambda user: user["name"].casefold())
    return users


def fetch_qa_team_members(client):
    """Active members of the Atlassian team used by the Assigned filter."""
    site_id = _site_id(client)
    team_id = _qa_team_id(client, site_id)
    if not team_id:
        return []
    return _users_by_account_ids(client, _qa_team_account_ids(client, site_id, team_id))


def fetch_issues(max_results=500):
    """
    Fetch issues from Jira for the dashboard.
    Returns list of dicts with: key, summary, status, assigned, priority, due_date, link, type.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}

    jql = (JIRA_TEAM_JQL.strip() if JIRA_TEAM_JQL else _default_jql()).strip()
    if not jql:
        jql = _default_jql()

    fields_request = "summary,status,assignee,priority,project,fixVersions"
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
    try:
        qa_team = fetch_qa_team_members(client)
    except Exception as e:
        print("QA team lookup failed:", _error_message(e), file=sys.stderr)
        qa_team = []

    out = []
    base_url = JIRA_URL.rstrip("/") + "/browse/"

    for raw in raw_issues:
        key = raw.get("key", "")
        fields = raw.get("fields") or {}
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}
        project = fields.get("project") or {}
        project_key = project.get("key", "")
        assigned_users = _assigned_users(project_key, fields)
        assigned = ", ".join(user["name"] for user in assigned_users)
        test_script = fields.get(JIRA_TEST_SCRIPT_FIELD_ID) or ""
        if not isinstance(test_script, str):
            test_script = str(test_script)
        fix_versions = fields.get("fixVersions") or []
        fix_version = ", ".join(_visible_fix_version_names(project_key, fix_versions))
        out.append({
            "key": key,
            "summary": fields.get("summary", ""),
            "status": status.get("name", ""),
            "assigned": assigned,
            "assigned_users": assigned_users,
            "assignment": _assignment_mode(project_key),
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
        "qa_team": qa_team,
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
        attachments = _attachment_summaries(fields.get("attachment"))
        _store_attachments(issue_key, attachments)
        images = {item["filename"].casefold(): item for item in attachments if item.get("filename")}
        try:
            comments = _fetch_comments(client, issue_key, images)
        except Exception as e:
            print("Jira comment lookup failed:", _error_message(e), file=sys.stderr)
            comments = []
        return {
            "key": raw.get("key", issue_key),
            "summary": summary,
            "description": description,
            "subtasks": subtasks,
            "acceptance_criteria": acceptance_criteria,
            "attachments": attachments,
            "comments": comments,
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


_ATTACHMENT_CACHE = {}
_ATTACHMENT_CACHE_TTL = 600


def _attachment_kind(mime_type):
    mime = (mime_type or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    return "file"


def _attachment_summaries(raw_attachments):
    summaries = []
    for item in raw_attachments or []:
        if not isinstance(item, dict):
            continue
        attachment_id = str(item.get("id") or "").strip()
        if not attachment_id:
            continue
        mime_type = (item.get("mimeType") or "").strip()
        summaries.append({
            "id": attachment_id,
            "filename": (item.get("filename") or "attachment").strip(),
            "mime_type": mime_type,
            "size": item.get("size") or 0,
            "kind": _attachment_kind(mime_type),
        })
    return summaries


def _store_attachments(issue_key, attachments):
    _ATTACHMENT_CACHE[issue_key] = (
        time.monotonic() + _ATTACHMENT_CACHE_TTL,
        {item["id"]: item for item in attachments},
    )


def _attachments_by_id(client, issue_key):
    cached = _ATTACHMENT_CACHE.get(issue_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    raw = client.issue(issue_key, fields="attachment")
    attachments = _attachment_summaries((raw.get("fields") or {}).get("attachment") if isinstance(raw, dict) else None)
    _store_attachments(issue_key, attachments)
    return _ATTACHMENT_CACHE[issue_key][1]


def open_issue_attachment(issue_key, attachment_id, range_header=None):
    """
    Stream one attachment that belongs to the issue.
    Returns {"response": requests.Response, "meta": {...}} or {"error": "..."}.
    The caller closes the response.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    issue_key = (issue_key or "").strip().upper()
    attachment_id = str(attachment_id or "").strip()
    if not issue_key or not attachment_id.isdigit():
        return {"error": "Attachment not found."}
    try:
        known = _attachments_by_id(client, issue_key)
        if attachment_id not in known:
            _ATTACHMENT_CACHE.pop(issue_key, None)
            known = _attachments_by_id(client, issue_key)
    except Exception as e:
        return {"error": _error_message(e)}
    meta = known.get(attachment_id)
    if not meta:
        return {"error": "Attachment not found."}
    headers = {}
    if range_header:
        headers["Range"] = range_header
    url = f"{JIRA_URL}/rest/api/3/attachment/content/{attachment_id}"
    try:
        response = client._session.get(url, headers=headers, stream=True, timeout=(10, 120))
    except Exception as e:
        return {"error": _error_message(e)}
    if response.status_code >= 400:
        response.close()
        return {"error": "Could not download attachment."}
    return {"response": response, "meta": meta}


def _safe_href(href):
    value = (href or "").strip()
    lowered = value.lower()
    if lowered.startswith("https://") or lowered.startswith("http://") or lowered.startswith("mailto:"):
        return value
    return ""


def _render_link(href, label_html):
    safe = _safe_href(href)
    if not safe:
        return label_html
    return (
        f'<a href="{html_escape(safe, quote=True)}" target="_blank" rel="noopener">{label_html}</a>'
    )


def _render_text(node):
    text = html_escape(node.get("text") or "")
    for mark in node.get("marks") or []:
        if not isinstance(mark, dict):
            continue
        mark_type = mark.get("type")
        if mark_type == "strong":
            text = f"<strong>{text}</strong>"
        elif mark_type == "em":
            text = f"<em>{text}</em>"
        elif mark_type == "code":
            text = f"<code>{text}</code>"
        elif mark_type == "strike":
            text = f"<s>{text}</s>"
        elif mark_type == "underline":
            text = f"<u>{text}</u>"
        elif mark_type == "link":
            text = _render_link((mark.get("attrs") or {}).get("href"), text)
    return text


def _render_media(attrs, issue_key, images):
    alt = (attrs.get("alt") or "attachment").strip() or "attachment"
    item = images.get(alt.casefold())
    label = html_escape(alt)
    if not item:
        return f'<p class="attachment-missing">{label}</p>'
    url = f"/api/issues/{quote(issue_key)}/attachments/{quote(item['id'])}"
    if item["kind"] == "image":
        return f'<img src="{url}" alt="{label}">'
    if item["kind"] == "video":
        return f'<video controls preload="none" src="{url}"></video>'
    return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'


def _render_adf(node, issue_key, images):
    """Turn a Jira ADF node into HTML. Text is escaped; media uses the local attachment proxy."""
    if isinstance(node, str):
        return html_escape(node)
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    attrs = node.get("attrs") or {}
    if kind == "text":
        return _render_text(node)
    if kind == "hardBreak":
        return "<br>"
    if kind == "mention":
        return html_escape(attrs.get("text") or "")
    if kind == "emoji":
        return html_escape(attrs.get("text") or attrs.get("shortName") or "")
    if kind == "media":
        return _render_media(attrs, issue_key, images)
    if kind in ("inlineCard", "blockCard"):
        url = attrs.get("url") or ""
        return _render_link(url, html_escape(url))
    children = "".join(
        _render_adf(child, issue_key, images) for child in (node.get("content") or [])
    )
    if kind == "paragraph":
        if not children.strip():
            return ""
        return f"<p>{children}</p>"
    if kind == "heading":
        level = attrs.get("level") if attrs.get("level") in (1, 2, 3, 4, 5, 6) else 3
        return f"<h{level}>{children}</h{level}>"
    if kind == "bulletList":
        return f"<ul>{children}</ul>"
    if kind == "orderedList":
        return f"<ol>{children}</ol>"
    if kind == "listItem":
        return f"<li>{children}</li>"
    if kind == "codeBlock":
        return f"<pre><code>{children}</code></pre>"
    if kind == "blockquote":
        return f"<blockquote>{children}</blockquote>"
    if kind == "rule":
        return "<hr>"
    if kind == "panel":
        return f'<div class="adf-panel">{children}</div>'
    if kind == "table":
        return f"<table>{children}</table>"
    if kind == "tableRow":
        return f"<tr>{children}</tr>"
    if kind == "tableHeader":
        return f"<th>{children}</th>"
    if kind == "tableCell":
        return f"<td>{children}</td>"
    return children


def _fetch_comments(client, issue_key, images):
    comments = []
    start = 0
    while len(comments) < 200:
        page = client.get(
            f"rest/api/3/issue/{issue_key}/comment",
            params={"startAt": start, "maxResults": 50, "orderBy": "created"},
        )
        if not isinstance(page, dict):
            break
        batch = page.get("comments") or []
        for item in batch:
            if not isinstance(item, dict):
                continue
            author = item.get("author") or {}
            comments.append({
                "id": str(item.get("id") or ""),
                "author": (author.get("displayName") or "").strip() or "Unknown",
                "created": item.get("created") or "",
                "html": _render_adf(item.get("body") or {}, issue_key, images),
            })
        start += len(batch)
        total = page.get("total") or 0
        if not batch or start >= total:
            break
    return comments


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


def search_issue_users(issue_key, query):
    """Search people who can be placed on this issue. Requires at least two characters."""
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    text = (query or "").strip()
    if len(text) < 2:
        return {"users": []}
    try:
        raw = client.get(
            client.resource_url("user/assignable/search"),
            params={"issueKey": issue_key.strip(), "query": text, "maxResults": 20},
        )
    except Exception as e:
        return {"error": _error_message(e)}

    users = []
    seen = set()
    for item in raw or []:
        user = _user_brief(item)
        if not user or user["accountId"] in seen:
            continue
        seen.add(user["accountId"])
        users.append(user)
    return {"users": users}


def set_issue_assignment(issue_key, account_ids):
    """
    Set the Assigned column for an issue.
    RDAR and QA update the assignee. Other projects update Approvers.
    An empty account id list clears the field.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured."}
    if not issue_key or not issue_key.strip():
        return {"error": "Issue key is required."}
    issue_key = issue_key.strip()

    ids = []
    seen = set()
    for account_id in account_ids or []:
        account_id = str(account_id or "").strip()
        if not account_id or account_id in seen:
            continue
        seen.add(account_id)
        ids.append(account_id)

    try:
        raw = client.issue(issue_key, fields="project")
        project_key = (((raw or {}).get("fields") or {}).get("project") or {}).get("key") or ""
        if _assignment_mode(project_key) == "assignee":
            client.assign_issue(issue_key, ids[0] if ids else None)
        else:
            if not JIRA_APPROVERS_FIELD_ID:
                return {"error": "Approvers field is not configured."}
            client.issue_update(
                issue_key,
                {JIRA_APPROVERS_FIELD_ID: [{"accountId": account_id} for account_id in ids]},
            )
    except Exception as e:
        return {"error": _error_message(e)}
    return {"success": True}


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

# v2026-11, v2026-10-GA, CAL v2026-02. Month is the first YYYY-MM in the name.
_YEAR_MONTH_IN_NAME = re.compile(r"(20\d{2})-(\d{2})")
# VM Beta 07-2025. Used when the name has no YYYY-MM.
_MONTH_YEAR_IN_NAME = re.compile(r"(?<!\d)(\d{2})-(20\d{2})(?!\d)")
_YEAR_IN_NAME = re.compile(r"20\d{2}")


def _version_year_month(name):
    """Return (year, month) from a version name, or None when it has no month."""
    text = name or ""
    match = _YEAR_MONTH_IN_NAME.search(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return year, month
    match = _MONTH_YEAR_IN_NAME.search(text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return year, month
    return None


def _version_is_current(project_key, name, today=None):
    """Keep a fix version that is still in the working window.

    Monthly names such as v2026-11 stay for this month and later. RDAR stays
    for the current year and later. Names with no date stay.
    """
    today = today or date.today()
    if (project_key or "").upper() == "RDAR":
        years = [int(year) for year in _YEAR_IN_NAME.findall(name or "")]
        if not years:
            return True
        return max(years) >= today.year
    year_month = _version_year_month(name)
    if year_month is None:
        return True
    return year_month >= (today.year, today.month)


def _visible_fix_version_names(project_key, fix_versions):
    names = []
    for version in fix_versions or []:
        if not isinstance(version, dict):
            continue
        name = (version.get("name") or "").strip()
        if name and _version_is_current(project_key, name):
            names.append(name)
    return names

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
            if not name or not _version_is_current(project_key, name):
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
            if name and not _version_is_current(project_key, name):
                continue
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
            if not version.get("released") and not _version_is_current(project_key, name):
                continue
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


# IDA's step out of QA is Ready For Deployment. RDAR and the QA project use Done.
_QA_COMPLETION_RULES = (
    ("IDA", "In QA", "Ready For Deployment"),
    ("RDAR", "In Testing", "DONE"),
    ("QA", None, "DONE"),
)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _same_status(actual, expected):
    if expected is None:
        return True
    return (actual or "").strip().casefold() == expected.strip().casefold()


def _changelog_local_date(created):
    """Calendar day for a Jira changelog timestamp, in the machine's local time."""
    if created is None or created == "":
        return ""
    if isinstance(created, (int, float)) or (isinstance(created, str) and str(created).isdigit()):
        moment = datetime.fromtimestamp(float(created) / 1000.0)
        return moment.date().isoformat()
    text = str(created).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if moment.tzinfo is None:
        return moment.date().isoformat()
    return moment.astimezone().date().isoformat()


def _bulk_status_histories(client, issue_ids):
    """Status changelog entries keyed by Jira issue id."""
    histories = {str(issue_id): [] for issue_id in issue_ids}
    ids = [str(issue_id) for issue_id in issue_ids]
    for offset in range(0, len(ids), 100):
        chunk = ids[offset:offset + 100]
        token = None
        while True:
            body = {"issueIdsOrKeys": chunk, "fieldIds": ["status"], "maxResults": 1000}
            if token:
                body["nextPageToken"] = token
            data = client.post(client.resource_url("changelog/bulkfetch"), data=body) or {}
            for log in data.get("issueChangeLogs") or []:
                issue_id = str(log.get("issueId") or "")
                histories.setdefault(issue_id, []).extend(log.get("changeHistories") or [])
            token = data.get("nextPageToken")
            if not token:
                break
    return histories


def fetch_qa_completion_counts(start_date, end_date):
    """
    Count tickets that finished QA on each day.
    IDA: In QA -> Ready For Deployment. RDAR: In Testing -> Done. QA project: moved to Done.
    A ticket is counted once per day.
    """
    client = _get_client()
    if not client:
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"}
    start_date = (start_date or "").strip()
    end_date = (end_date or "").strip()
    if not _ISO_DATE.match(start_date) or not _ISO_DATE.match(end_date) or start_date > end_date:
        return {"error": "start and end must be YYYY-MM-DD, with start on or before end."}

    during = f'DURING ("{start_date}", "{end_date}")'
    jql = " OR ".join([
        f'(project = IDA AND status changed FROM "In QA" TO "Ready For Deployment" {during})',
        f'(project = RDAR AND status changed FROM "In Testing" TO "DONE" {during})',
        f'(project = QA AND status changed TO "DONE" {during})',
    ])
    try:
        raw_issues = _fetch_jql_issues(client, jql, "summary", max_results=1000)
        histories = _bulk_status_histories(
            client,
            [issue.get("id") for issue in raw_issues if issue.get("id")],
        )
    except Exception as e:
        return {"error": _error_message(e)}

    rules = {project: (from_status, to_status) for project, from_status, to_status in _QA_COMPLETION_RULES}
    by_day = {}
    for issue in raw_issues:
        issue_id = str(issue.get("id") or "")
        key = issue.get("key") or ""
        project = key.split("-", 1)[0]
        rule = rules.get(project)
        if not issue_id or not rule:
            continue
        from_status, to_status = rule
        counted_days = set()
        for history in histories.get(issue_id) or []:
            day = _changelog_local_date(history.get("created"))
            if not day or day < start_date or day > end_date or day in counted_days:
                continue
            matched = False
            for item in history.get("items") or []:
                field = (item.get("field") or item.get("fieldId") or "").lower()
                if field != "status":
                    continue
                if _same_status(item.get("fromString"), from_status) and _same_status(item.get("toString"), to_status):
                    matched = True
                    break
            if not matched:
                continue
            counted_days.add(day)
            by_day.setdefault(day, {}).setdefault(project, set()).add(key)

    return {
        "counts": {
            day: {project: len(keys) for project, keys in projects.items()}
            for day, projects in by_day.items()
        }
    }
