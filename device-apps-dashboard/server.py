"""
Device Apps Dashboard – Flask backend.
Compares device apps from Esper with expected apps/versions from Confluence Device Apps page.
Run from project root: python device-apps-dashboard/server.py
"""
import os
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from esper_client import get_device_apps, get_device_search_debug
from confluence_client import (
    get_device_apps_page_tables,
    parse_tables_for_expected_apps,
    expected_apps_for_version,
    get_confluence_debug,
)
from config import is_esper_configured, is_confluence_configured, get_allowlist_for_section

STATIC_DIR = DASHBOARD_DIR / "static"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
CORS(app)


def _normalize_name_for_match(name):
    """Lowercase and strip for comparison."""
    return (name or "").strip().lower()


def _app_in_allowlist(app_name, allowlist):
    """True if app_name (after normalizing) matches an allowlisted name."""
    if not allowlist:
        return True
    raw = (app_name or "").strip()
    norm = _normalize_name_for_match(raw)
    for allowed in allowlist:
        if _normalize_name_for_match(allowed) == norm:
            return True
    return False


def compare_apps(esper_apps, expected_apps, allowlist=None):
    """
    Compare Esper device apps with Confluence expected apps.
    If allowlist is set, only include apps whose name is in the allowlist.
    Returns: comparison list with app_name, package_name, esper_version, expected_version, status.
    """
    use_allowlist = allowlist if allowlist is not None else get_allowlist_for_section(None)
    expected_apps = [e for e in (expected_apps or []) if not use_allowlist or _app_in_allowlist(e.get("app_name"), use_allowlist)]

    esper_by_name = {_normalize_name_for_match(a.get("app_name")): a for a in (esper_apps or [])}
    esper_by_package = {_normalize_name_for_match(a.get("package_name")): a for a in (esper_apps or [])}
    expected_by_name = {}
    for e in expected_apps:
        n = _normalize_name_for_match(e.get("app_name"))
        if n and n not in expected_by_name:
            expected_by_name[n] = e

    comparison = []
    matched_names = set()

    for exp in expected_apps:
        exp_name = (exp.get("app_name") or "").strip()
        exp_ver = (exp.get("version") or "").strip()
        exp_name_norm = _normalize_name_for_match(exp_name)
        on_device = esper_by_name.get(exp_name_norm) or esper_by_package.get(exp_name_norm)
        if on_device:
            matched_names.add(exp_name_norm)
            dev_ver = (on_device.get("version_name") or on_device.get("version_code") or "").strip()
            status = "match" if (exp_ver and dev_ver and exp_ver in dev_ver) or (not exp_ver) else "version_mismatch"
            comparison.append({
                "app_name": exp_name,
                "package_name": on_device.get("package_name") or "",
                "esper_version": dev_ver,
                "expected_version": exp_ver,
                "status": status,
            })
        else:
            comparison.append({
                "app_name": exp_name,
                "package_name": "",
                "esper_version": "",
                "expected_version": exp_ver,
                "status": "only_expected",
            })

    for dev in esper_apps or []:
        name_norm = _normalize_name_for_match(dev.get("app_name"))
        pkg_norm = _normalize_name_for_match(dev.get("package_name"))
        if name_norm in matched_names or pkg_norm in matched_names:
            continue
        app_name = dev.get("app_name") or dev.get("package_name") or ""
        if use_allowlist and not _app_in_allowlist(app_name, use_allowlist):
            continue
        comparison.append({
            "app_name": app_name,
            "package_name": dev.get("package_name") or "",
            "esper_version": (dev.get("version_name") or dev.get("version_code") or "").strip(),
            "expected_version": "",
            "status": "only_on_device",
        })

    return {
        "esper_apps": esper_apps or [],
        "expected_apps": expected_apps,
        "comparison": comparison,
    }


@app.route("/api/status")
def status():
    return jsonify({
        "esper_configured": is_esper_configured(),
        "confluence_configured": is_confluence_configured(),
    })


@app.route("/api/confluence-meta")
def confluence_meta():
    """GET /api/confluence-meta – sections and version columns for dropdowns (no device). Load on page init."""
    tables_result = get_device_apps_page_tables()
    if "error" in tables_result:
        return jsonify({"error": tables_result["error"], "sections": []}), 200
    tables = tables_result.get("tables_content") or []
    parsed = parse_tables_for_expected_apps(tables)
    sections = parsed.get("sections") or []
    out = {
        "sections": [
            {"name": s.get("name"), "version_columns": s.get("version_columns") or []}
            for s in sections
        ],
    }
    return jsonify(out)


@app.route("/api/debug-confluence")
def debug_confluence():
    """Return Confluence table fetch summary (table count, first row per table) to debug '0 expected apps'."""
    return jsonify(get_confluence_debug())


@app.route("/api/debug-device-search")
def debug_device_search():
    """Return device list API status/counts for a query (e.g. ?q=CAI250222284) to debug 'device not found'."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "Missing query param: ?q=CAI250222284"}), 400
    return jsonify(get_device_search_debug(q))


@app.route("/api/compare")
def compare():
    """GET /api/compare?device_id=<uuid> – fetch Esper device apps, Confluence expected apps, and compare."""
    device_id = (request.args.get("device_id") or "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    # Fetch from Esper
    esper_result = get_device_apps(device_id)
    if "error" in esper_result:
        return jsonify(esper_result), 500
    esper_apps = esper_result.get("apps") or []

    # Fetch from Confluence
    tables_result = get_device_apps_page_tables()
    if "error" in tables_result:
        return jsonify({
            "error": tables_result["error"],
            "esper_apps": esper_apps,
            "expected_apps": [],
            "comparison": [],
            "sections": [],
            "version_columns": [],
        }), 200
    tables = tables_result.get("tables_content") or []
    parsed = parse_tables_for_expected_apps(tables)
    section = (request.args.get("section") or "").strip()
    version_column = (request.args.get("version_column") or "").strip()
    expected_apps = expected_apps_for_version(parsed, version_column or None, section or None)

    # Section list for dropdown; pick active section's version_columns
    sections = parsed.get("sections") or []
    active_section = None
    if section and sections:
        for s in sections:
            if (s.get("name") or "").strip() == section:
                active_section = s
                break
    if not active_section and sections:
        active_section = sections[0]
    version_columns = (active_section or {}).get("version_columns") or parsed.get("version_columns") or []
    allowlist = get_allowlist_for_section(section or (active_section.get("name") if active_section else None))
    out = compare_apps(esper_apps, expected_apps, allowlist=allowlist)
    out["device_id"] = device_id
    out["esper_apps_count"] = len(esper_apps)
    out["expected_apps_count"] = len(expected_apps)
    out["sections"] = [{"name": s.get("name")} for s in sections]
    out["section"] = section or (active_section.get("name") if active_section else "")
    out["version_columns"] = version_columns
    out["version_column"] = version_column or (version_columns[-1] if version_columns else "")
    return jsonify(out)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    os.chdir(DASHBOARD_DIR)
    port = int(os.environ.get("PORT", 5558))
    print(f"Device Apps Dashboard: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
