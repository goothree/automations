"""Load Jira config from environment."""
import os
from pathlib import Path

# Load .env from jira-dashboard dir or project root
_env_dir = Path(__file__).resolve().parent
_dotenv = _env_dir / ".env"
if _dotenv.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv)
    except ImportError:
        pass

JIRA_URL = os.environ.get("JIRA_URL", "").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT = (os.environ.get("JIRA_PROJECT") or "").strip()
JIRA_TEAM_JQL = (os.environ.get("JIRA_TEAM_JQL") or "").strip()
# Default issue list when JIRA_PROJECT and JIRA_TEAM_JQL are empty.
# Each entry is a project key and the JQL condition for that project.
JIRA_DEFAULT_QUEUE = (
    ("IDA", 'status = "In QA"'),
    ("RDAR", 'status = "In Testing"'),
    ("QA", "resolution = Unresolved"),
)
# Custom field ID for "Test Script" (e.g. customfield_10100). Find in Jira Admin → Custom fields.
JIRA_TEST_SCRIPT_FIELD_ID = (os.environ.get("JIRA_TEST_SCRIPT_FIELD_ID") or "").strip()
# Optional: custom field ID for "Acceptance Criteria" (e.g. customfield_10xxx). Used when generating test steps.
JIRA_AC_FIELD_ID = (os.environ.get("JIRA_AC_FIELD_ID") or "").strip()
# Custom field ID for "Approvers" (user picker array). Default for care.ai Jira.
JIRA_APPROVERS_FIELD_ID = (os.environ.get("JIRA_APPROVERS_FIELD_ID") or "customfield_10003").strip()
# Assigned filter lists members of this Atlassian team. Org id is care.ai's Atlassian organization.
JIRA_QA_TEAM_NAME = (os.environ.get("JIRA_QA_TEAM_NAME") or "QA").strip()
JIRA_ORG_ID = (os.environ.get("JIRA_ORG_ID") or "7813343c-4f17-48f6-8239-4455660568b6").strip()

# Testpad API (https://api.testpad.com/api/v1/ or instance-specific). API must be enabled by Testpad Support.
TESTPAD_BASE_URL = (os.environ.get("TESTPAD_BASE_URL") or "https://api.testpad.com/api/v1").rstrip("/")
TESTPAD_API_TOKEN = (os.environ.get("TESTPAD_API_TOKEN") or "").strip()
TESTPAD_PROJECT_ID = (os.environ.get("TESTPAD_PROJECT_ID") or "6").strip()
TESTPAD_FOLDER_ID = (os.environ.get("TESTPAD_FOLDER_ID") or "").strip()
# Script destination by Jira project prefix. IDA and RDAR override TESTPAD_FOLDER_ID.
TESTPAD_FOLDER_BY_PREFIX = {
    "IDA": (os.environ.get("TESTPAD_FOLDER_IDA") or "f197").strip(),
    "RDAR": (os.environ.get("TESTPAD_FOLDER_RDAR") or "f198").strip(),
}
# Upper-level project folders already seen, "id:name" records separated by "|".
# A script run prompts only when Testpad has an upper-level folder that is not in this set.


def _parse_known_upper_folders(raw):
    known = {}
    for part in (raw or "").split("|"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            folder_id, name = part.split(":", 1)
            known[folder_id.strip()] = name.strip()
        else:
            known[part] = ""
    return known


TESTPAD_KNOWN_UPPER_FOLDERS = _parse_known_upper_folders(
    os.environ.get("TESTPAD_KNOWN_UPPER_FOLDERS") or ""
)
# Base URL for Testpad UI links (e.g. https://vuaant.testpad.com)
TESTPAD_UI_BASE_URL = (os.environ.get("TESTPAD_UI_BASE_URL") or "https://vuaant.testpad.com").rstrip("/")
# Optional: exact URL pattern for script links. Open a script in the browser and replace the script id with {script_id}.
# Example: https://vuaant.testpad.com/project/6/folder/12/script/123 -> use .../folder/12/script/{script_id}
# Placeholders: {base}, {project_id}, {folder_id}, {script_id}. If empty, a default pattern is used.
TESTPAD_SCRIPT_URL_TEMPLATE = (os.environ.get("TESTPAD_SCRIPT_URL_TEMPLATE") or "").strip()

# LLM for test generation fallback (OpenAI)
OPENAI_API_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

# SharePoint test plan delivery (OneDrive-synced folder shared with QA team)
TEST_PLAN_SHAREPOINT_FOLDER_URL = (
    os.environ.get("TEST_PLAN_SHAREPOINT_FOLDER_URL")
    or "https://stryker-my.sharepoint.com/:f:/p/michael_guthrie/"
    "IgBAyEORHosITrKk3lSVFca_AePm9AG_nzqGIQvVf7EbPk0"
).strip()
TEST_PLAN_ONEDRIVE_SYNC_DIR = (
    os.environ.get("TEST_PLAN_ONEDRIVE_SYNC_DIR")
    or "/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans"
).strip()
TEST_PLAN_SHAREPOINT_SITE_BASE = (
    os.environ.get("TEST_PLAN_SHAREPOINT_SITE_BASE")
    or "https://stryker-my.sharepoint.com/personal/michael_guthrie_stryker_com"
).rstrip("/")
TEST_PLAN_SHAREPOINT_FOLDER_PATH = (
    os.environ.get("TEST_PLAN_SHAREPOINT_FOLDER_PATH") or "Documents/TestPlans"
).strip("/")


def is_configured():
    return bool(JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN)


def testpad_folder_for_issue(issue_key):
    """Return the Testpad folder id for a Jira key. IDA -> f197, RDAR -> f198."""
    key = (issue_key or "").strip().upper()
    prefix = key.split("-", 1)[0] if "-" in key else ""
    folder = TESTPAD_FOLDER_BY_PREFIX.get(prefix) or ""
    return folder or TESTPAD_FOLDER_ID


def is_testpad_configured():
    has_folder = bool(TESTPAD_FOLDER_ID or any(TESTPAD_FOLDER_BY_PREFIX.values()))
    return bool(TESTPAD_BASE_URL and TESTPAD_API_TOKEN and TESTPAD_PROJECT_ID and has_folder)


def is_jira_to_testpad_configured():
    return (
        is_configured()
        and bool(JIRA_TEST_SCRIPT_FIELD_ID)
        and is_testpad_configured()
        and bool(OPENAI_API_KEY)
    )
