"""Load config from environment for Device Apps Dashboard (Esper + Confluence)."""
import os
from pathlib import Path

_env_dir = Path(__file__).resolve().parent
_dotenv = _env_dir / ".env"
if _dotenv.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv)
    except ImportError:
        pass

# Esper (https://careai.esper.cloud — API at careai-api.esper.cloud/api)
ESPER_BASE_URL = (os.environ.get("ESPER_BASE_URL") or "https://careai-api.esper.cloud/api").rstrip("/")
ESPER_API_KEY = (os.environ.get("ESPER_API_KEY") or "").strip()
ESPER_ENTERPRISE_ID = (os.environ.get("ESPER_ENTERPRISE_ID") or "").strip()
# Auth: "Bearer" (default), "ApiKey", or "X-Api-Key" — change if you get 401
ESPER_AUTH_TYPE = (os.environ.get("ESPER_AUTH_TYPE") or "Bearer").strip()

# Confluence — Device Apps page (same Atlassian account as Jira)
CONFLUENCE_URL = (os.environ.get("CONFLUENCE_URL") or os.environ.get("JIRA_URL", "").replace(".atlassian.net", ".atlassian.net/wiki")).rstrip("/")
if CONFLUENCE_URL and "/wiki" not in CONFLUENCE_URL and "atlassian.net" in CONFLUENCE_URL:
    CONFLUENCE_URL = CONFLUENCE_URL.rstrip("/") + "/wiki"
CONFLUENCE_EMAIL = (os.environ.get("CONFLUENCE_EMAIL") or os.environ.get("JIRA_EMAIL") or "").strip()
CONFLUENCE_API_TOKEN = (os.environ.get("CONFLUENCE_API_TOKEN") or os.environ.get("JIRA_API_TOKEN") or "").strip()
# Confluence page ID for "Device Apps" (from URL .../pages/2097741847/Device+Apps)
CONFLUENCE_DEVICE_APPS_PAGE_ID = (os.environ.get("CONFLUENCE_DEVICE_APPS_PAGE_ID") or "2097741847").strip()

# Apps included in the comparison (Confluence + device). Upgrade app depends on section.
ALLOWLIST_APP_NAMES_BASE = frozenset({
    "Ambient Monitoring", "IPM", "NLP", "Registration",
    "Sensors Service", "TV Control", "Virtual Care", "Firmware",
})
# Section → upgrade app name (replaces "R2C_Upgrade" when section is R2U, R2Pro, or R2X).
SECTION_UPGRADE_APP = {
    "R2C": "R2C_Upgrade",
    "R2U": "R2U_Upgrade",
    "R2Pro": "R2OB_S1_Combined_Upgrade",
    "R2X": "R2X_Upgrade",
}


def get_allowlist_for_section(section):
    """Return frozenset of app names to include for the given section (R2C, R2Pro, R2U)."""
    upgrade = SECTION_UPGRADE_APP.get((section or "").strip()) or SECTION_UPGRADE_APP.get("R2C")
    return ALLOWLIST_APP_NAMES_BASE | {upgrade}


def is_esper_configured():
    return bool(ESPER_BASE_URL and ESPER_API_KEY and ESPER_ENTERPRISE_ID)


def is_confluence_configured():
    return bool(CONFLUENCE_URL and CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN)
