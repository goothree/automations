#!/usr/bin/env python3
"""
Update the "Today - IDA/Services SCRUM" Confluence page: find Michael's row
and set Assigned Tasks and Current Tasks cells from TODO.md.

TODO.md must contain a "## Add to Today" section with "# Assigned Tasks..."
and "# Current Tasks..." headers; bullets under each (lines starting with -)
are synced to the Confluence table.

Standalone script — run when needed or on a schedule. Loads config from
device-apps-dashboard/.env (same as Device Apps Dashboard), then repo root .env,
then environment variables (CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN;
or JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN).

Usage (from repo root):
  python scripts/update_today.py
  # or: ./run_update_today
"""
import os
import re
import sys
from pathlib import Path

# Repo root: parent of scripts/
_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent
TODO_MD = REPO_ROOT / "TODO.md"

# Load .env: same as device-apps-dashboard first, then repo root
try:
    from dotenv import load_dotenv
    _device_apps_env = REPO_ROOT / "device-apps-dashboard" / ".env"
    if _device_apps_env.exists():
        load_dotenv(_device_apps_env)
    _root_env = REPO_ROOT / ".env"
    if _root_env.exists():
        load_dotenv(_root_env)
except ImportError:
    pass

# Config from environment (no dependency on device-apps-dashboard)
CONFLUENCE_URL = (os.environ.get("CONFLUENCE_URL") or os.environ.get("JIRA_URL", "").replace(".atlassian.net", ".atlassian.net/wiki")).rstrip("/")
if CONFLUENCE_URL and "/wiki" not in CONFLUENCE_URL and "atlassian.net" in CONFLUENCE_URL:
    CONFLUENCE_URL = CONFLUENCE_URL.rstrip("/") + "/wiki"
CONFLUENCE_EMAIL = (os.environ.get("CONFLUENCE_EMAIL") or os.environ.get("JIRA_EMAIL") or "").strip()
CONFLUENCE_API_TOKEN = (os.environ.get("CONFLUENCE_API_TOKEN") or os.environ.get("JIRA_API_TOKEN") or "").strip()


def is_confluence_configured():
    return bool(CONFLUENCE_URL and CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN)


PAGE_SPACE = "SCRUM"
# Try the actual page title first (two spaces around dash) to avoid "Can't find" log
PAGE_TITLE_VARIANTS = [
    "Today  -  IDA/Services SCRUM",
    "Today - IDA/Services SCRUM",
]
MICHAEL_NAME = "Michael"
ASSIGNED_TASKS_HEADER = "assigned tasks"
CURRENT_TASKS_HEADER = "current tasks"


def _tables_from_storage_html(html_content):
    """Parse body.storage HTML into list of tables (each table = list of rows, row = list of cell texts)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    if not html_content or not isinstance(html_content, str):
        return []
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    out = []
    for table in tables:
        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["th", "td"]):
                cells.append((cell.get_text() or "").strip())
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out


def _column_index_for_header(header_row, name):
    """Return 0-based column index where header (normalized) contains name, or None."""
    name = (name or "").strip().lower()
    for i, cell in enumerate(header_row):
        if name in (cell or "").strip().lower():
            return i
    return None


def _find_michael_row_and_columns(tables_content):
    """Find (table_index, row_index, assigned_col, current_col) for Michael's row. Assumes first row of table is header."""
    for ti, table in enumerate(tables_content):
        if not table or len(table) < 2:
            continue
        header = table[0]
        assigned_col = _column_index_for_header(header, ASSIGNED_TASKS_HEADER)
        current_col = _column_index_for_header(header, CURRENT_TASKS_HEADER)
        for ri, row in enumerate(table[1:], start=1):
            if not row:
                continue
            first_cell = (row[0] or "").strip()
            if first_cell == MICHAEL_NAME:
                return (ti, ri, assigned_col, current_col)
    return None


def _bullets_from_todo_section(content, section_header):
    """Return list of bullet text under the given section. Finds '# Assigned Tasks...' or
    '# Current Tasks...' (or any line with # and that key) and collects following lines
    that start with '-' until the next line starting with '#'."""
    lines = content.splitlines()
    key = section_header.replace("...", "").strip().lower()
    bullets = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and key in stripped.lower():
            in_section = True
            continue
        if in_section:
            if stripped.startswith("#"):
                break
            if stripped.startswith("---"):
                break
            if stripped[0:1] == "-" or stripped[0:1] == "–" or stripped[0:1] == "•":
                text = stripped[1:].strip()
                bullets.append(text)
    return bullets


def get_todo_sections():
    """Read TODO.md and return assigned_tasks and current_tasks bullet lists (text only)."""
    if not TODO_MD.exists():
        return [], []
    content = TODO_MD.read_text(encoding="utf-8", errors="replace")
    assigned = _bullets_from_todo_section(content, "Assigned Tasks")
    current = _bullets_from_todo_section(content, "Current Tasks")
    return assigned, current


def fetch_page_and_find_michael(confluence):
    """Fetch SCRUM page by title, get body.storage, parse tables, return (page_id, title, storage_value, table_idx, row_idx, assigned_col, current_col)."""
    page = None
    for title in PAGE_TITLE_VARIANTS:
        try:
            page = confluence.get_page_by_title(PAGE_SPACE, title, expand="body.storage")
            if page:
                break
        except Exception:
            continue
    if not page:
        raise FileNotFoundError(f"Confluence page not found: space={PAGE_SPACE}, tried titles: {PAGE_TITLE_VARIANTS}")

    page_id = page["id"]
    title = page["title"]
    storage_value = (page.get("body") or {}).get("storage") or {}
    body_html = (storage_value.get("value") or "")

    tables_content = _tables_from_storage_html(body_html)
    found = _find_michael_row_and_columns(tables_content)
    if not found:
        raise ValueError("Michael row or Assigned Tasks/Current Tasks columns not found on page")
    ti, ri, assigned_col, current_col = found
    if assigned_col is None or current_col is None:
        raise ValueError("Assigned Tasks or Current Tasks column not found in table header")

    version_num = (page.get("version") or {}).get("number")
    return page_id, title, body_html, ti, ri, assigned_col, current_col, version_num


def _bullets_to_wiki_markup(bullets):
    """Convert bullet list to Confluence wiki list markup (raw text; convert API will escape)."""
    return "\n".join("* " + (b or "") for b in bullets) or ""


def _convert_wiki_to_storage(confluence, wiki_markup):
    """Use Confluence REST API to convert wiki markup to storage format. Returns storage HTML string or None on failure."""
    try:
        resp = confluence.convert_wiki_to_storage(wiki_markup)
        if resp is None:
            return None
        if isinstance(resp, dict) and "value" in resp:
            return resp["value"]
        if hasattr(resp, "get") and resp.get("value"):
            return resp["value"]
        # Some APIs return the string directly
        if isinstance(resp, str) and resp.strip().startswith("<"):
            return resp
        return None
    except Exception:
        return None


def _find_cell_inner_bounds(html, table_index, data_row_index, col_index):
    """Find (start, end) character positions of the inner content of the nth cell by scanning tags."""
    import re
    table_count = -1
    in_table = False
    row_count = -1
    cell_count = -1
    i = 0
    while i < len(html):
        if html[i:i + 1] == "<":
            tag_match = re.match(r"<\s*(table|tr|td|th)(?:\s|>|/)", html[i:], re.IGNORECASE)
            if tag_match:
                tag = tag_match.group(1).lower()
                # Skip to end of this opening tag
                close_bracket = html.find(">", i)
                if close_bracket == -1:
                    i += 1
                    continue
                if tag == "table":
                    table_count += 1
                    if table_count == table_index:
                        in_table = True
                        row_count = -1
                    else:
                        in_table = False
                elif in_table and tag == "tr":
                    row_count += 1
                    if row_count == data_row_index:
                        cell_count = -1
                    else:
                        cell_count = -2
                elif in_table and row_count == data_row_index and tag in ("td", "th"):
                    cell_count += 1
                    if cell_count == col_index:
                        content_start = close_bracket + 1
                        depth = 1
                        j = content_start
                        while j < len(html):
                            if html[j:j + 1] == "<":
                                end_tag = re.match(r"</\s*(table|tr|td|th)\s*>", html[j:], re.IGNORECASE)
                                if end_tag and end_tag.group(1).lower() in ("td", "th"):
                                    depth -= 1
                                    if depth == 0:
                                        return content_start, j
                                    j += len(end_tag.group(0))
                                    continue
                                open_tag = re.match(r"<\s*(td|th)(?:\s|>|/)", html[j:], re.IGNORECASE)
                                if open_tag:
                                    depth += 1
                            j += 1
                        return None, None
                i = close_bracket + 1
                continue
        i += 1
    return None, None


def replace_table_cells_in_storage(html, table_index, data_row_index, col_index, cell_storage_html):
    """Replace the content of one table cell. Prefer string replacement to avoid altering rest of document."""
    new_inner = (cell_storage_html or "").strip() or "<p></p>"
    start, end = _find_cell_inner_bounds(html, table_index, data_row_index, col_index)
    if start is not None and end is not None:
        return html[:start] + new_inner + html[end:]
    # Fallback: parse and modify (may change formatting/namespaces)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if table_index >= len(tables):
        return html
    table = tables[table_index]
    rows = table.find_all("tr")
    if data_row_index + 1 > len(rows):
        return html
    row = rows[data_row_index]
    cells = row.find_all(["td", "th"])
    if col_index >= len(cells):
        return html
    cell = cells[col_index]
    cell.clear()
    if new_inner != "<p></p>":
        frag = BeautifulSoup(new_inner, "html.parser")
        for child in list(frag.children):
            cell.append(child)
    else:
        cell.append(soup.new_tag("p"))
    return str(soup)


def update_confluence_today_page():
    """Main: fetch page, get Michael row and columns, read TODO.md, update two cells, push to Confluence."""
    if not is_confluence_configured():
        raise RuntimeError(
            "Confluence not configured. Set CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN "
            "(or JIRA_*) in device-apps-dashboard/.env, repo root .env, or environment"
        )

    from atlassian import Confluence
    confluence = Confluence(
        url=CONFLUENCE_URL,
        username=CONFLUENCE_EMAIL,
        password=CONFLUENCE_API_TOKEN,
        cloud=True,
    )

    assigned_bullets, current_bullets = get_todo_sections()

    page_id, title, body_html, ti, ri, assigned_col, current_col, version_num = fetch_page_and_find_michael(confluence)
    if version_num is None:
        try:
            history = confluence.history(page_id)
            version_num = (history or {}).get("lastUpdated", {}).get("number")
        except Exception:
            pass
    if version_num is None:
        raise RuntimeError("Could not get page version (required for update)")

    # Use Confluence convert API so cell content is valid storage format; fallback to simple ul/li
    def storage_for_bullets(bullets):
        wiki = _bullets_to_wiki_markup(bullets)
        storage = _convert_wiki_to_storage(confluence, wiki) if wiki else None
        if storage:
            return storage
        if not bullets:
            return ""
        from bs4 import BeautifulSoup
        ul = "<ul>"
        for b in bullets:
            escaped = (b or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            ul += f"<li><p>{escaped}</p></li>"
        ul += "</ul>"
        return ul

    assigned_html = storage_for_bullets(assigned_bullets)
    current_html = storage_for_bullets(current_bullets)

    new_body = replace_table_cells_in_storage(body_html, ti, ri, assigned_col, assigned_html)
    new_body = replace_table_cells_in_storage(new_body, ti, ri, current_col, current_html)

    debug = os.environ.get("DEBUG_UPDATE_TODAY", "").strip().lower() in ("1", "true", "yes")
    if debug:
        debug_dir = REPO_ROOT / "scripts"
        (debug_dir / "update_today_body_before.txt").write_text(body_html[:15000], encoding="utf-8", errors="replace")
        (debug_dir / "update_today_body_after.txt").write_text(new_body[:15000], encoding="utf-8", errors="replace")
        (debug_dir / "update_today_assigned_bullets.txt").write_text(repr(assigned_bullets), encoding="utf-8")
        (debug_dir / "update_today_current_bullets.txt").write_text(repr(current_bullets), encoding="utf-8")
        print(f"Debug: wrote body and bullets to scripts/update_today_*.txt", file=sys.stderr)

    # Use REST API directly so we can verify request/response
    import json
    import requests
    base_url = CONFLUENCE_URL.rstrip("/")
    put_url = f"{base_url}/rest/api/content/{page_id}"
    auth = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
    payload = {
        "id": str(page_id),
        "type": "page",
        "title": title,
        "version": {"number": version_num + 1, "minorEdit": True},
        "body": {"storage": {"value": new_body, "representation": "storage"}},
    }
    resp = requests.put(
        put_url,
        auth=auth,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        timeout=60,
    )
    if debug or resp.status_code != 200:
        print(f"PUT {put_url} -> {resp.status_code}", file=sys.stderr)
        if resp.text:
            print(resp.text[:2000], file=sys.stderr)
    resp.raise_for_status()

    # Verify: re-fetch page and check Michael's row has our content
    updated = confluence.get_page_by_id(page_id, expand="body.storage")
    updated_body = (updated.get("body") or {}).get("storage") or {}
    updated_html = (updated_body.get("value") or "")
    tables = _tables_from_storage_html(updated_html)
    found = _find_michael_row_and_columns(tables)
    if found:
        _ti, _ri, a_col, c_col = found
        if a_col is not None and c_col is not None and tables and _ti < len(tables):
            row = tables[_ti][_ri]
            assigned_text = (row[a_col] if a_col < len(row) else "").strip()
            current_text = (row[c_col] if c_col < len(row) else "").strip()
            expected_assigned = " ".join(b for b in assigned_bullets if b).strip()[:80]
            expected_current = " ".join(b for b in current_bullets if b).strip()[:80]
            if expected_assigned and expected_assigned not in assigned_text:
                print(f"Warning: Assigned Tasks cell may not have updated (expected snippet: {expected_assigned!r})", file=sys.stderr)
            if expected_current and expected_current not in current_text:
                print(f"Warning: Current Tasks cell may not have updated (expected snippet: {expected_current!r})", file=sys.stderr)

    return page_id, title


if __name__ == "__main__":
    try:
        page_id, title = update_confluence_today_page()
        print(f"Updated Confluence page: {title} (id={page_id})")
        print(f"URL: https://careai.atlassian.net/wiki/spaces/SCRUM/pages/{page_id}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
