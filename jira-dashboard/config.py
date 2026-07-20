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
# Custom field ID for "Test Script" (e.g. customfield_10100). Find in Jira Admin → Custom fields.
JIRA_TEST_SCRIPT_FIELD_ID = (os.environ.get("JIRA_TEST_SCRIPT_FIELD_ID") or "").strip()
# Optional: custom field ID for "Acceptance Criteria" (e.g. customfield_10xxx). Used when generating test steps.
JIRA_AC_FIELD_ID = (os.environ.get("JIRA_AC_FIELD_ID") or "").strip()
# Custom field ID for "Approvers" (user picker array). Default for care.ai Jira.
JIRA_APPROVERS_FIELD_ID = (os.environ.get("JIRA_APPROVERS_FIELD_ID") or "customfield_10003").strip()

# Testpad API (https://api.testpad.com/api/v1/ or instance-specific). API must be enabled by Testpad Support.
TESTPAD_BASE_URL = (os.environ.get("TESTPAD_BASE_URL") or "https://api.testpad.com/api/v1").rstrip("/")
TESTPAD_API_TOKEN = (os.environ.get("TESTPAD_API_TOKEN") or "").strip()
TESTPAD_PROJECT_ID = (os.environ.get("TESTPAD_PROJECT_ID") or "6").strip()
TESTPAD_FOLDER_ID = (os.environ.get("TESTPAD_FOLDER_ID") or "").strip()
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


def is_testpad_configured():
    return bool(TESTPAD_BASE_URL and TESTPAD_API_TOKEN and TESTPAD_PROJECT_ID and TESTPAD_FOLDER_ID)


def is_jira_to_testpad_configured():
    return (
        is_configured()
        and bool(JIRA_TEST_SCRIPT_FIELD_ID)
        and is_testpad_configured()
        and bool(OPENAI_API_KEY)
    )
