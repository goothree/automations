"""
Esper API client: fetch apps installed on a device by device ID, serial, or name.
Resolves serial/name to device UUID via device list search when needed.
"""
import re
import requests
from config import (
    ESPER_BASE_URL,
    ESPER_API_KEY,
    ESPER_ENTERPRISE_ID,
    ESPER_AUTH_TYPE,
    is_esper_configured,
)


def _headers():
    auth_type = (ESPER_AUTH_TYPE or "Bearer").strip().lower()
    headers = {"Content-Type": "application/json"}
    if auth_type == "x-api-key":
        headers["X-Api-Key"] = ESPER_API_KEY
    elif auth_type == "apikey":
        headers["Authorization"] = f"ApiKey {ESPER_API_KEY}"
    else:
        # Bearer (default) — most Esper tenant APIs expect this
        headers["Authorization"] = f"Bearer {ESPER_API_KEY}"
    return headers


# UUID-like: 8-4-4-4-12 hex with optional hyphens
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")


def _device_serial(dev):
    """Extract serial from device list item (top-level or hardwareInfo)."""
    s = (dev.get("serial") or "").strip()
    if s:
        return s
    hw = dev.get("hardwareInfo") or {}
    if isinstance(hw, dict):
        return (hw.get("serial") or hw.get("serial_number") or "").strip()
    return ""


def _device_name(dev):
    """Extract display name from device list item (v2 uses 'name', enterprise uses 'device_name')."""
    return (dev.get("name") or dev.get("device_name") or "").strip()


def _base_urls():
    """Return base URLs to try: config value and, if different, with /api appended (Esper tenant API often at /api)."""
    base = (ESPER_BASE_URL or "").rstrip("/")
    if not base:
        return []
    out = [base]
    if "/api" not in base:
        out.append(base + "/api")
    return out


def _fetch_device_lists(raw):
    """
    Fetch device lists from both v2 and enterprise APIs. Returns (results_list, error_hint).
    Tries ESPER_BASE_URL and ESPER_BASE_URL/api when one returns 404 (tenant API often under /api).
    """
    out = []
    hint = None
    bases = _base_urls()

    for base in bases:
        v2_url = f"{base}/v2/devices/"
        for params in [{"search": raw, "limit": 20}, {"serial": raw, "limit": 10}]:
            try:
                r = requests.get(v2_url, headers=_headers(), params=params, timeout=30)
            except requests.RequestException as e:
                hint = str(e)
                continue
        if r.status_code == 401:
            return [], "API key invalid or unauthorized (401). Try ESPER_AUTH_TYPE=ApiKey or ESPER_AUTH_TYPE=X-Api-Key in .env"
            if r.status_code == 403:
                return [], "Forbidden (403)"
            if r.status_code == 404:
                hint = f"v2 list returned 404 (try ESPER_BASE_URL with /api, e.g. https://careai-api.esper.cloud/api)"
                continue
            if r.status_code != 200:
                hint = f"v2 list returned {r.status_code}"
                continue
            data = r.json() or {}
            content = data.get("content")
            results = (content if isinstance(content, dict) else {}).get("results") or data.get("results") or []
            if results:
                out.extend(results)
                break
        if out:
            break
    else:
        hint = hint or "v2 list returned 404 (try ESPER_BASE_URL with /api, e.g. https://careai-api.esper.cloud/api)"

    # 2) Enterprise Android device list if v2 gave nothing
    if not out:
        for base in bases:
            ent_url = f"{base}/enterprise/{ESPER_ENTERPRISE_ID}/device/"
            for params in [{"search": raw, "limit": 20}, {"serial": raw, "limit": 5}, {"name": raw, "limit": 5}]:
                try:
                    r = requests.get(ent_url, headers=_headers(), params=params, timeout=30)
                except requests.RequestException:
                    continue
                if r.status_code == 401:
                    return [], "API key invalid or unauthorized (401). Try ESPER_AUTH_TYPE=ApiKey or ESPER_AUTH_TYPE=X-Api-Key in .env"
                if r.status_code == 403:
                    return [], "Forbidden (403)"
                if r.status_code != 200:
                    continue
                results = (r.json() or {}).get("results") or []
                if results:
                    out.extend(results)
                    break
            if out:
                break

    # 3) Fallback: fetch one page of all devices and match by serial/name in memory
    if not out:
        for base in bases:
            for url, key in [
                (f"{base}/v2/devices/", "content"),
                (f"{base}/enterprise/{ESPER_ENTERPRISE_ID}/device/", "results"),
            ]:
                try:
                    r = requests.get(url, headers=_headers(), params={"limit": 100}, timeout=30)
                except requests.RequestException:
                    continue
                if r.status_code != 200:
                    continue
                data = r.json() or {}
                if key == "content":
                    content = data.get("content")
                    results = (content if isinstance(content, dict) else {}).get("results") or []
                else:
                    results = data.get("results") or []
                raw_lower = raw.lower()
                for dev in results:
                    if raw_lower in (_device_name(dev).lower() or ""):
                        out.append(dev)
                    if raw_lower in (_device_serial(dev).lower() or ""):
                        out.append(dev)
                if out:
                    return out, None
    return out, hint


def _resolve_device_id(device_id_or_serial):
    """
    If input looks like a UUID, return it. Otherwise search devices (v2 then enterprise)
    and return the first match's id, or None if not found.
    """
    if not device_id_or_serial or not is_esper_configured():
        return None, None, None
    raw = (device_id_or_serial or "").strip()
    if _UUID_RE.match(raw):
        return raw, None, None
    results, hint = _fetch_device_lists(raw)
    if not results:
        return None, None, hint or "No devices returned for search/serial"
    # Prefer exact name or serial match
    for dev in results:
        if _device_name(dev) == raw:
            return dev.get("id"), dev, None
        if _device_serial(dev) == raw:
            return dev.get("id"), dev, None
    return results[0].get("id"), results[0], None


def get_device_search_debug(query):
    """
    Call device list APIs with the given search/serial and return status codes and result counts
    (for debugging "device not found" without exposing full responses). Tries both base and base/api.
    """
    if not is_esper_configured():
        return {"error": "Esper not configured"}
    raw = (query or "").strip()
    info = {"bases_tried": _base_urls()}
    for i, base in enumerate(_base_urls()):
        prefix = f"base{i}_" if len(_base_urls()) > 1 else ""
        # v2
        try:
            r = requests.get(
                f"{base}/v2/devices/",
                headers=_headers(),
                params={"search": raw, "limit": 5},
                timeout=15,
            )
            data = r.json() or {}
            content = data.get("content")
            results = (content if isinstance(content, dict) else {}).get("results") or data.get("results") or []
            info[f"{prefix}v2_status"] = r.status_code
            info[f"{prefix}v2_count"] = len(results)
            if results:
                info[f"{prefix}v2_first_id"] = results[0].get("id")
                info[f"{prefix}v2_first_name"] = _device_name(results[0])
                info[f"{prefix}v2_first_serial"] = _device_serial(results[0])
        except Exception as e:
            info[f"{prefix}v2_error"] = str(e)
        # enterprise
        try:
            r2 = requests.get(
                f"{base}/enterprise/{ESPER_ENTERPRISE_ID}/device/",
                headers=_headers(),
                params={"search": raw, "limit": 5},
                timeout=15,
            )
            data2 = r2.json() or {}
            results2 = data2.get("results") or []
            info[f"{prefix}enterprise_status"] = r2.status_code
            info[f"{prefix}enterprise_count"] = len(results2)
            if results2:
                info[f"{prefix}enterprise_first_id"] = results2[0].get("id")
                info[f"{prefix}enterprise_first_name"] = _device_name(results2[0])
        except Exception as e:
            info[f"{prefix}enterprise_error"] = str(e)
    return info


def get_device_apps(device_id):
    """
    Fetch all apps installed on the given device from Esper.
    device_id can be the Esper device UUID or a serial/name (e.g. CAI250222284); we resolve via search if needed.
    Returns list of dicts with: app_name, package_name, version_name, version_code, state, etc.
    """
    if not is_esper_configured():
        return {"error": "Esper not configured. Set ESPER_BASE_URL, ESPER_API_KEY, ESPER_ENTERPRISE_ID in .env"}

    resolved_id, device_info, resolve_hint = _resolve_device_id(device_id)
    if not resolved_id:
        msg = f"Device not found: {device_id}."
        if resolve_hint:
            msg += f" ({resolve_hint})"
        else:
            msg += " Try the device serial or name as shown in Esper (e.g. CAI250222284), or the device UUID."
        return {"error": msg}
    device_id = resolved_id

    # Try each base URL (e.g. with and without /api) so app list works when list used base/api
    working_base = None
    for base in _base_urls():
        url = f"{base}/enterprise/{ESPER_ENTERPRISE_ID}/device/{device_id}/app/"
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
        except requests.RequestException as e:
            continue
        if r.status_code == 200:
            working_base = base
            break
        if r.status_code == 401:
            return {"error": "Esper API key invalid or unauthorized. Try ESPER_AUTH_TYPE=ApiKey or ESPER_AUTH_TYPE=X-Api-Key in .env"}
        if r.status_code == 404:
            continue
        try:
            body = r.json()
            msg = body.get("message") or body.get("errors") or r.text[:200]
        except Exception:
            msg = r.text[:200]
        return {"error": f"Esper API error ({r.status_code}): {msg}"}
    if not working_base:
        return {"error": f"Device apps endpoint returned 404 for device {device_id}. Check ESPER_BASE_URL (try .../api)."}

    all_results = []
    next_url = f"{working_base}/enterprise/{ESPER_ENTERPRISE_ID}/device/{device_id}/app/"

    while next_url:
        try:
            r = requests.get(next_url, headers=_headers(), timeout=30)
        except requests.RequestException as e:
            return {"error": str(e)}

        if r.status_code == 401:
            return {"error": "Esper API key invalid or unauthorized. Try ESPER_AUTH_TYPE=ApiKey or ESPER_AUTH_TYPE=X-Api-Key in .env"}
        if r.status_code == 404:
            return {"error": f"Device not found: {device_id}"}
        if r.status_code != 200:
            try:
                body = r.json()
                msg = body.get("message") or body.get("errors") or r.text[:200]
            except Exception:
                msg = r.text[:200]
            return {"error": f"Esper API error ({r.status_code}): {msg}"}

        data = r.json() or {}
        # Handle both { "results": [...] } and { "content": { "results": [...] } } (tenant API sometimes wraps)
        content = data.get("content")
        results = (content if isinstance(content, dict) else {}).get("results") or data.get("results") or []
        all_results.extend(results)
        next_url = (content if isinstance(content, dict) else {}).get("next") or data.get("next")
        if next_url and not next_url.startswith("http"):
            next_url = f"{working_base.rstrip('/')}{next_url}" if next_url.startswith("/") else None

    return {
        "apps": [
            {
                "app_name": app.get("app_name") or "",
                "package_name": app.get("package_name") or "",
                "version_name": app.get("version_name") or "",
                "version_code": str(app.get("version_code") or "") if app.get("version_code") is not None else "",
                "state": app.get("state") or "",
            }
            for app in all_results
        ],
    }
