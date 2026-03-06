"""
Orchestrate: fetch Jira issue → generate test steps → create Testpad script → set Jira Test Script field.
"""
from jira_client import get_issue_full, set_test_script_url
from testpad_client import create_script
from test_generator import generate_test_steps


def run(issue_key):
    """
    For the given Jira issue key:
    1. Fetch issue (summary, description)
    2. Generate test steps (hybrid: structured + LLM)
    3. Create Testpad script with those steps
    4. Update Jira Test Script field with script URL

    Returns {"success": True, "script_url": "...", "issue_key": "..."} or {"success": False, "error": "..."}.
    """
    issue_key = (issue_key or "").strip().upper()
    if not issue_key:
        return {"success": False, "error": "Issue key is required."}

    issue = get_issue_full(issue_key)
    if "error" in issue:
        return {"success": False, "error": issue["error"]}

    summary = issue.get("summary") or ""
    steps = generate_test_steps(issue=issue)
    script_name = f"[{issue_key}] {summary[:60]}" if summary else f"[{issue_key}] Test script"

    result = create_script(script_name, steps)
    if "error" in result:
        return {"success": False, "error": result["error"]}

    script_url = result.get("script_url") or ""
    if not script_url:
        return {"success": False, "error": "Testpad did not return a script URL."}

    update = set_test_script_url(issue_key, script_url)
    if "error" in update:
        return {"success": False, "error": f"Script created but Jira update failed: {update['error']}"}

    return {"success": True, "script_url": script_url, "issue_key": issue_key}
