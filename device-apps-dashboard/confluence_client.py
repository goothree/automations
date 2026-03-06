"""
Confluence client: fetch Device Apps page and parse expected apps/versions from tables.
Uses Atlassian Confluence REST API (same credentials as Jira).
"""
import json
from config import (
    CONFLUENCE_URL,
    CONFLUENCE_EMAIL,
    CONFLUENCE_API_TOKEN,
    CONFLUENCE_DEVICE_APPS_PAGE_ID,
    is_confluence_configured,
)


def _tables_from_view_html(html_content):
    """Parse body.view HTML and return tables_content (list of tables, each table = list of rows, row = list of cell texts)."""
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


def get_device_apps_page_tables():
    """
    Fetch the Confluence Device Apps page and return parsed tables.
    Tries get_tables_from_page (body.storage) first; if no tables found, falls back to body.view HTML.
    Returns dict with tables_content (list of list of rows) or error.
    """
    if not is_confluence_configured():
        return {"error": "Confluence not configured. Set CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN (or JIRA_*) in .env"}

    try:
        from atlassian import Confluence
    except ImportError:
        return {"error": "atlassian-python-api required. pip install atlassian-python-api"}

    page_id = int(CONFLUENCE_DEVICE_APPS_PAGE_ID) if CONFLUENCE_DEVICE_APPS_PAGE_ID else None
    if not page_id:
        return {"error": "CONFLUENCE_DEVICE_APPS_PAGE_ID is not set or invalid"}

    try:
        confluence = Confluence(
            url=CONFLUENCE_URL,
            username=CONFLUENCE_EMAIL,
            password=CONFLUENCE_API_TOKEN,
            cloud=True,
        )
        raw = confluence.get_tables_from_page(page_id)
        if isinstance(raw, str):
            raw = json.loads(raw)
        if "No tables found" in str(raw):
            raw = None
        if raw and raw.get("tables_content"):
            return {"tables_content": raw["tables_content"], "page_id": page_id}

        # Fallback: fetch body.view (HTML) and parse tables ourselves (Confluence Cloud often uses different storage)
        try:
            page = confluence.get_page_by_id(page_id, expand="body.view")
            view_body = (page or {}).get("body") or {}
            view_value = (view_body.get("view") or {}).get("value")
            if view_value:
                tables_content = _tables_from_view_html(view_value)
                if tables_content:
                    return {"tables_content": tables_content, "page_id": page_id}
        except Exception:
            pass

        return {"error": "No tables found on Device Apps page (tried storage and view). Check page ID and that the page has at least one table.", "raw": str(raw)[:200]}
    except Exception as e:
        msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            code = getattr(e.response, "status_code", None)
            if code == 404:
                return {"error": f"Confluence page not found (ID {CONFLUENCE_DEVICE_APPS_PAGE_ID}). Check CONFLUENCE_DEVICE_APPS_PAGE_ID."}
            if code == 401:
                return {"error": "Confluence unauthorized. Check CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN."}
            try:
                body = e.response.json()
                msg = body.get("message") or str(body)
            except Exception:
                pass
        return {"error": msg}


def get_confluence_debug():
    """
    Return a short summary of what Confluence returns (for debugging "0 expected apps").
    Does not return full page content.
    """
    if not is_confluence_configured():
        return {"error": "Confluence not configured"}
    page_id = CONFLUENCE_DEVICE_APPS_PAGE_ID
    try:
        page_id = int(page_id)
    except (TypeError, ValueError):
        return {"error": "Invalid CONFLUENCE_DEVICE_APPS_PAGE_ID", "page_id": page_id}
    out = {"page_id": page_id, "table_count": 0, "tables_summary": []}
    try:
        from atlassian import Confluence
        confluence = Confluence(
            url=CONFLUENCE_URL,
            username=CONFLUENCE_EMAIL,
            password=CONFLUENCE_API_TOKEN,
            cloud=True,
        )
        raw = confluence.get_tables_from_page(page_id)
        if isinstance(raw, str):
            raw = json.loads(raw)
        if raw and raw.get("tables_content"):
            tc = raw["tables_content"]
            out["table_count"] = len(tc)
            out["source"] = "storage"
            for i, table in enumerate(tc[:5]):
                rows = table if isinstance(table, list) else []
                out["tables_summary"].append({"table_index": i, "rows": len(rows), "first_row": rows[0] if rows else None})
        else:
            out["source"] = "storage"
            out["no_tables_reason"] = "No tables_content in response" if not (raw and raw.get("tables_content")) else str(raw)[:300]
            # Try view fallback
            page = confluence.get_page_by_id(page_id, expand="body.view")
            view_body = (page or {}).get("body") or {}
            view_obj = view_body.get("view") or {}
            view_html = view_obj.get("value") if isinstance(view_obj, dict) else (view_obj if isinstance(view_obj, str) else None)
            if view_html and isinstance(view_html, str):
                tables_content = _tables_from_view_html(view_html)
                out["view_fallback_table_count"] = len(tables_content)
                if tables_content:
                    out["tables_summary"] = [{"table_index": i, "rows": len(t), "first_row": t[0] if t else None} for i, t in enumerate(tables_content[:5])]
                    out["table_count"] = len(tables_content)
                    out["source"] = "view"
    except Exception as e:
        out["error"] = str(e)
    return out


def _normalize_header(h):
    """Strip and normalize header text for matching (e.g. 'December 2025 **' -> 'december 2025')."""
    return (str(h).strip().lower().rstrip("*").strip() if h else "")


# Section header row: first cell is one of these (case-insensitive). Defines R2C, R2Pro, R2U blocks.
SECTION_NAMES = ("r2c", "r2pro", "r2u", "r2x")


def _is_section_header_row(row):
    """True if row looks like a section title (e.g. first cell is R2C, R2Pro, R2U)."""
    if not row or not isinstance(row, list):
        return False
    first = (str(row[0] or "").strip().lower())
    return first in SECTION_NAMES


def _parse_section(rows, name_headers, version_headers, start_idx):
    """
    From rows starting at start_idx, find header row (application/version columns) and data rows.
    Stops at next section header or end. Returns (header_original, name_col, version_col, data_row_indices) or None.
    """
    header_original = None
    header_normalized = None
    header_row_idx = None
    for idx in range(start_idx, len(rows)):
        row = rows[idx]
        if not row:
            continue
        if _is_section_header_row(row):
            if header_row_idx is not None:
                break
            continue
        cells_norm = [_normalize_header(c) for c in row]
        if any(c in name_headers for c in cells_norm):
            header_row_idx = idx
            header_normalized = cells_norm
            header_original = [str(c).strip() for c in row]
            break
    if header_row_idx is None or not header_original:
        return None
    data_end = len(rows)
    for idx in range(header_row_idx + 1, len(rows)):
        if _is_section_header_row(rows[idx]):
            data_end = idx
            break
    name_col = None
    version_col = None
    for i, h in enumerate(header_normalized):
        if h in name_headers:
            name_col = i
        if h in version_headers:
            version_col = i
    if name_col is None:
        name_col = 0
    if version_col is None:
        version_col = len(header_normalized) - 1 if len(header_normalized) > 1 else 0
    if version_col == name_col and len(header_normalized) > 1:
        version_col = len(header_normalized) - 1
    return (header_original, name_col, version_col, header_row_idx, data_end)


def parse_tables_for_expected_apps(tables_content):
    """
    Parse list of tables into sections (R2C, R2Pro, R2U) with version columns and apps per section.
    Returns: {"sections": [{"name": "R2C", "version_columns": [...], "apps": [...]}, ...]}
    If no section headers found, treats the whole table as one section "R2C" for backward compatibility.
    """
    if not tables_content:
        return {"sections": [], "version_columns": [], "apps": []}

    name_headers = ("app", "application", "name", "app name", "package", "package name")
    version_headers = ("version", "version name", "version name/code", "ver")
    sections = []

    for table in tables_content:
        if not table or not isinstance(table, list):
            continue
        rows = [r if isinstance(r, list) else [] for r in table]
        if not rows:
            continue

        idx = 0
        while idx < len(rows):
            row = rows[idx]
            if _is_section_header_row(row):
                section_name = (str(row[0] or "").strip().upper() if row else "")
                if section_name == "R2PRO":
                    section_name = "R2Pro"
                elif section_name == "R2C":
                    section_name = "R2C"
                elif section_name == "R2U":
                    section_name = "R2U"
                parsed = _parse_section(rows, name_headers, version_headers, idx + 1)
                idx = idx + 1
                if not parsed:
                    continue
                header_original, name_col, version_col, header_row_idx, data_end = parsed
                version_columns = [
                    (header_original[i] or "").strip()
                    for i in range(len(header_original))
                    if i != name_col and (header_original[i] or "").strip()
                ]
                if not version_columns and len(header_original) > 1:
                    version_columns = [header_original[i] for i in range(1, len(header_original))]
                apps = []
                for r in range(header_row_idx + 1, data_end):
                    row = rows[r]
                    if not row or not isinstance(row, list):
                        continue
                    while len(row) < len(header_original):
                        row = list(row) + [""]
                    name = str(row[name_col] or "").strip()
                    if not name or name.lower() in ("application", "app", "name", "package") or name.isdigit():
                        continue
                    versions = {}
                    for i in range(len(header_original)):
                        if i != name_col and i < len(row):
                            col_label = (header_original[i] or "").strip()
                            if col_label:
                                versions[col_label] = str(row[i] or "").strip()
                    apps.append({"app_name": name or "(no name)", "versions": versions})
                sections.append({"name": section_name, "version_columns": version_columns, "apps": apps})
                idx = data_end
                continue
            # No section header at this row; try to parse as single table (backward compat)
            parsed = _parse_section(rows, name_headers, version_headers, idx)
            if parsed:
                header_original, name_col, version_col, header_row_idx, data_end = parsed
                version_columns = [
                    (header_original[i] or "").strip()
                    for i in range(len(header_original))
                    if i != name_col and (header_original[i] or "").strip()
                ]
                if not version_columns and len(header_original) > 1:
                    version_columns = [header_original[i] for i in range(1, len(header_original))]
                apps = []
                for r in range(header_row_idx + 1, data_end):
                    row = rows[r]
                    if not row or not isinstance(row, list):
                        continue
                    while len(row) < len(header_original):
                        row = list(row) + [""]
                    name = str(row[name_col] or "").strip()
                    if not name or name.lower() in ("application", "app", "name", "package") or name.isdigit():
                        continue
                    versions = {}
                    for i in range(len(header_original)):
                        if i != name_col and i < len(row):
                            col_label = (header_original[i] or "").strip()
                            if col_label:
                                versions[col_label] = str(row[i] or "").strip()
                    apps.append({"app_name": name or "(no name)", "versions": versions})
                sections.append({"name": "R2C", "version_columns": version_columns, "apps": apps})
            break
        if sections:
            break

    # Flatten for backward compat: first section's version_columns and all apps from first section
    version_columns = []
    apps = []
    if sections:
        version_columns = sections[0].get("version_columns") or []
        apps = sections[0].get("apps") or []
    return {"sections": sections, "version_columns": version_columns, "apps": apps}


def _get_section(parsed, section_name=None):
    """Return the section dict to use (by name). If section_name is None, return first section."""
    sections = parsed.get("sections") or []
    if not sections:
        return parsed
    if section_name:
        sn = (section_name or "").strip()
        for s in sections:
            if (s.get("name") or "").strip() == sn:
                return s
    return sections[0] if sections else parsed


def expected_apps_for_version(parsed, version_column=None, section=None):
    """
    Given result of parse_tables_for_expected_apps, optional section name (R2C, R2Pro, R2U),
    and optional version column name, return list of {app_name, version}.
    """
    sec = _get_section(parsed, section)
    apps = sec.get("apps") or []
    if not apps:
        return []
    cols = sec.get("version_columns") or []
    chosen = (version_column or "").strip() if version_column else None
    if not chosen and cols:
        chosen = cols[-1]
    result = []
    for a in apps:
        versions = a.get("versions") or {}
        version = versions.get(chosen, "") if chosen else ""
        result.append({"app_name": a["app_name"], "version": version})
    return result


def parse_expected_apps_from_tables(tables_content, version_column=None, section=None):
    """
    Parse tables and return list of {app_name, version} for the given section and version column.
    """
    parsed = parse_tables_for_expected_apps(tables_content)
    return expected_apps_for_version(parsed, version_column, section)
