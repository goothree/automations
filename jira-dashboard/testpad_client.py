"""
Testpad API client: create scripts and build script URLs.
Uses TESTPAD_BASE_URL, TESTPAD_API_TOKEN, TESTPAD_PROJECT_ID, TESTPAD_FOLDER_ID, TESTPAD_UI_BASE_URL.
"""
import requests

from config import (
    TESTPAD_BASE_URL,
    TESTPAD_API_TOKEN,
    TESTPAD_PROJECT_ID,
    TESTPAD_FOLDER_ID,
    TESTPAD_UI_BASE_URL,
    TESTPAD_SCRIPT_URL_TEMPLATE,
)


def create_script(name, test_steps):
    """
    Create a new script in Testpad with the given name and test steps.
    test_steps: list of strings (each string is one test step).
    Returns {"script_url": "https://...", "script_id": ...} or {"error": "..."}.
    """
    if not TESTPAD_API_TOKEN or not TESTPAD_FOLDER_ID:
        return {"error": "Testpad not configured (TESTPAD_API_TOKEN, TESTPAD_FOLDER_ID)."}
    url = f"{TESTPAD_BASE_URL}/projects/{TESTPAD_PROJECT_ID}/folders/{TESTPAD_FOLDER_ID}/scripts"
    headers = {
        "Authorization": f"apikey {TESTPAD_API_TOKEN}",
        "Content-Type": "application/json",
    }
    # Testpad API: tests can be "list of strings" or "list of objects with text" (see Supplying Test Text).
    script_name = (name or "Untitled script").strip() or "Untitled script"
    steps = [str(s).strip() or "Step" for s in (test_steps or []) if str(s).strip()]
    if not steps:
        steps = ["Verify the issue requirements and acceptance criteria."]
    body = {
        "name": script_name,
        "tests": steps,
    }

    try:
        r = requests.post(url, json=body, headers=headers, timeout=30)
        # If 500 with list of strings, retry with list of objects (API may expect { "text": "..." } per test)
        if r.status_code == 500 and body.get("tests"):
            body_alt = {
                "name": script_name,
                "tests": [{"text": s} for s in body["tests"]],
            }
            r2 = requests.post(url, json=body_alt, headers=headers, timeout=30)
            if r2.ok:
                r = r2
            # else: keep original r so we surface the real error below
        if not r.ok:
            try:
                err_detail = r.json()
            except Exception:
                err_detail = r.text or str(r.status_code)
            hint = ""
            if r.status_code == 500:
                hint = " (Check TESTPAD_PROJECT_ID and TESTPAD_FOLDER_ID in .env; 500 often means wrong folder or unsupported request body.)"
            return {"error": f"Testpad API error: {err_detail}{hint}"}
        data = r.json() if r.content else {}
        # Script ID may be at top level or nested (e.g. script.id, script_id, id)
        script_id = (
            data.get("id")
            or data.get("script_id")
            or (data.get("script") or {}).get("id")
            or (data.get("script") or {}).get("script_id")
        )
        # Response may include a direct URL, or API may return it in Location header
        script_url = (
            (data.get("url") or data.get("href") or data.get("link") or "")
            or ((data.get("script") or {}).get("url") or (data.get("script") or {}).get("href") or (data.get("script") or {}).get("link") or "")
        )
        if not script_url and r.headers.get("Location"):
            script_url = r.headers["Location"].strip()
            if script_url.startswith("/"):
                script_url = (TESTPAD_UI_BASE_URL or "").rstrip("/") + script_url
        if not script_url and script_id is not None:
            script_url = build_script_url(script_id)
        if not script_url:
            # Include response snippet so we can see what Testpad returned
            snippet = str(data)[:200] if data else (r.text[:200] if r.text else "empty")
            return {"error": f"Testpad did not return a script URL or script id. Response: {snippet}"}
        return {"script_url": script_url, "script_id": script_id}
    except requests.exceptions.RequestException as e:
        err = e.response.text if getattr(e, "response", None) is not None else str(e)
        return {"error": f"Testpad API error: {err}"}
    except Exception as e:
        return {"error": str(e)}


def build_script_url(script_id):
    """Build the Testpad UI URL for a script. Uses TESTPAD_SCRIPT_URL_TEMPLATE if set."""
    if script_id is None or script_id == "":
        return ""
    if TESTPAD_SCRIPT_URL_TEMPLATE:
        return (
            TESTPAD_SCRIPT_URL_TEMPLATE.replace("{base}", TESTPAD_UI_BASE_URL or "")
            .replace("{project_id}", TESTPAD_PROJECT_ID or "")
            .replace("{folder_id}", TESTPAD_FOLDER_ID or "")
            .replace("{script_id}", str(script_id))
        )
    # Default: vuaant.testpad.com and similar use /script/{id} (no project/folder in path)
    base = (TESTPAD_UI_BASE_URL or "").rstrip("/")
    return f"{base}/script/{script_id}"
