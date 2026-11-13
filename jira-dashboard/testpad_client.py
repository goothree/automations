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
    TESTPAD_KNOWN_UPPER_FOLDERS,
    testpad_folder_for_issue,
)


def list_upper_level_folders():
    """Return the project's top-level folders as {"folders": [{"id", "name"}, ...]}."""
    if not TESTPAD_API_TOKEN:
        return {"error": "Testpad not configured (TESTPAD_API_TOKEN)."}
    url = f"{TESTPAD_BASE_URL}/projects/{TESTPAD_PROJECT_ID}/folders"
    headers = {"Authorization": f"apikey {TESTPAD_API_TOKEN}", "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if not r.ok:
            return {"error": f"Testpad API error: {r.status_code} {r.text[:300]}"}
        data = r.json() if r.content else {}
        items = data.get("folders") if isinstance(data, dict) else data
        folders = []
        for item in items or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            folders.append({"id": str(item.get("id")), "name": item.get("name") or ""})
        return {"folders": folders}
    except requests.exceptions.RequestException as e:
        err = e.response.text if getattr(e, "response", None) is not None else str(e)
        return {"error": f"Testpad API error: {err}"}
    except Exception as e:
        return {"error": str(e)}


def new_upper_level_folders():
    """Upper-level folders whose ids are not in TESTPAD_KNOWN_UPPER_FOLDERS."""
    listed = list_upper_level_folders()
    if "error" in listed:
        return listed
    known = set(TESTPAD_KNOWN_UPPER_FOLDERS)
    new_folders = [folder for folder in listed["folders"] if folder["id"] not in known]
    return {"new_folders": new_folders, "folders": listed["folders"]}


def create_script(name, test_steps, folder_id=None, issue_key=None, skip_new_folder_check=False):
    """
    Create a new script in Testpad with the given name and test steps.
    test_steps: list of strings (each string is one test step).
    folder_id overrides the folder chosen from issue_key (IDA -> f197, RDAR -> f198).
    Refuses to create when Testpad has a new upper-level folder, so the caller can ask
    which folders to use. Pass skip_new_folder_check only after that choice is saved.
    Returns {"script_url": "https://...", "script_id": ..., "folder_id": ...} or {"error": "..."}.
    """
    if not skip_new_folder_check:
        found = new_upper_level_folders()
        new_folders = found.get("new_folders") or []
        if new_folders:
            labels = ", ".join(
                f"{folder['name']} ({folder['id']})" if folder.get("name") else folder["id"]
                for folder in new_folders
            )
            return {
                "error": (
                    "New upper-level Testpad folder found: "
                    f"{labels}. Ask which folders to use before creating scripts."
                ),
                "needs_folder_prompt": True,
                "new_folders": new_folders,
            }
    folder = (folder_id or testpad_folder_for_issue(issue_key) or TESTPAD_FOLDER_ID or "").strip()
    if not TESTPAD_API_TOKEN or not folder:
        return {"error": "Testpad not configured (TESTPAD_API_TOKEN and a folder id)."}
    url = f"{TESTPAD_BASE_URL}/projects/{TESTPAD_PROJECT_ID}/folders/{folder}/scripts"
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
            script_url = build_script_url(script_id, folder_id=folder)
        if not script_url:
            # Include response snippet so we can see what Testpad returned
            snippet = str(data)[:200] if data else (r.text[:200] if r.text else "empty")
            return {"error": f"Testpad did not return a script URL or script id. Response: {snippet}"}
        return {"script_url": script_url, "script_id": script_id, "folder_id": folder}
    except requests.exceptions.RequestException as e:
        err = e.response.text if getattr(e, "response", None) is not None else str(e)
        return {"error": f"Testpad API error: {err}"}
    except Exception as e:
        return {"error": str(e)}


def build_script_url(script_id, folder_id=None):
    """Build the Testpad UI URL for a script. Uses TESTPAD_SCRIPT_URL_TEMPLATE if set."""
    if script_id is None or script_id == "":
        return ""
    folder = (folder_id or TESTPAD_FOLDER_ID or "").strip()
    if TESTPAD_SCRIPT_URL_TEMPLATE:
        return (
            TESTPAD_SCRIPT_URL_TEMPLATE.replace("{base}", TESTPAD_UI_BASE_URL or "")
            .replace("{project_id}", TESTPAD_PROJECT_ID or "")
            .replace("{folder_id}", folder)
            .replace("{script_id}", str(script_id))
        )
    # Default: vuaant.testpad.com and similar use /script/{id} (no project/folder in path)
    base = (TESTPAD_UI_BASE_URL or "").rstrip("/")
    return f"{base}/script/{script_id}"
