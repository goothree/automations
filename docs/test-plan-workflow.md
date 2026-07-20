# Test Plan Workflow (Cursor)

Create test plans from Jira tickets using **Cursor** in the `care.ai` repo. The agent generates the Word doc, Testpad import file, copies both to SharePoint, and posts a Jira comment automatically.

## What you need before starting

Ask Michael to:

1. Grant you **git access** to the `care.ai` repo [send Michael the email / account you use for git]
2. **Share** the TestPlans SharePoint folder (Edit access):  This is done.
   https://stryker-my.sharepoint.com/:f:/p/michael_guthrie/IgBAyEORHosITrKk3lSVFca_AePm9AG_nzqGIQvVf7EbPk0

You also need:

- **Cursor** installed — https://cursor.com
- **Jira already connected in Cursor** (Atlassian integration — same setup you use for other Jira work in Cursor)

No separate Jira API token or `jira-dashboard/.env` setup is required for the team.

## One-time setup

### 1. Clone the repo and install dependencies

The agent runs Python scripts in the background; you need a venv once:

```bash
git clone <care.ai-repo-url>
cd care.ai
git pull origin main

python3 -m venv .venv
.venv/bin/pip install -r jira-dashboard/requirements.txt
```

### 2. Sync the TestPlans folder in OneDrive

1. Open the SharePoint folder link (above)
2. Click **Sync** or **Add shortcut to OneDrive**
3. Wait until files appear locally

**Default local path (Michael’s Mac):**

`/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans`

If your Mac username is different, OneDrive will sync under your user folder instead, e.g.:

`/Users/<your-name>/Library/CloudStorage/OneDrive-Stryker/TestPlans`

Tell the agent your local path the first time you create a test plan, or add only this line to `jira-dashboard/.env`:

```env
TEST_PLAN_ONEDRIVE_SYNC_DIR=/Users/<your-name>/Library/CloudStorage/OneDrive-Stryker/TestPlans
```

Confirm the folder exists and contains test plans:

```bash
ls "/Users/<your-name>/Library/CloudStorage/OneDrive-Stryker/TestPlans"
```

### 3. Open the repo in Cursor

1. **File → Open Folder** → select the `care.ai` directory
2. Confirm **Atlassian / Jira** is connected in Cursor (Settings → MCP / Integrations)
3. The workflow rule `.cursor/rules/test-plan-sharepoint.mdc` is already in the repo — no other Cursor setup needed

## Creating a test plan

In **Cursor chat**, ask:

> Review and create test plan for https://careai.atlassian.net/browse/IDA-XXXX

Replace `IDA-XXXX` with the ticket key or paste the full Jira URL.

The agent will:

1. Read the Jira ticket (via Cursor’s Jira integration)
2. Generate `reports/IDA-XXXX_test_plan.docx`
3. Generate `reports/IDA-XXXX_testpad.txt` (for Testpad paste)
4. Copy both files to the OneDrive TestPlans folder (SharePoint sync)
5. Post a Jira comment with a link to the Word doc

You do **not** need to run scripts manually.

## Confirm it worked

| Check | Expected |
|-------|----------|
| Cursor response | Links to the `.docx`, confirms Jira comment posted |
| SharePoint / OneDrive | `IDA-XXXX_test_plan.docx` and `IDA-XXXX_testpad.txt` in TestPlans |
| Jira ticket | New comment: `Test plan: IDA-XXXX_test_plan.docx` |
| Click the link | Opens in **Word Online** in the browser |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Agent skips SharePoint or Jira | Ask it to complete delivery per the test plan workflow |
| Agent can’t read Jira ticket | Reconnect Atlassian/Jira in Cursor settings |
| Copy to TestPlans fails | OneDrive not synced, or tell the agent your `TEST_PLAN_ONEDRIVE_SYNC_DIR` |
| Jira comment fails | Confirm you can comment on the ticket in Jira; check Cursor Jira connection |
| SharePoint link downloads instead of opening online | Tell the agent to re-run delivery; links should use `?web=1` |

## Shared locations (reference)

| Setting | Value |
|---------|--------|
| SharePoint folder | https://stryker-my.sharepoint.com/:f:/p/michael_guthrie/IgBAyEORHosITrKk3lSVFca_AePm9AG_nzqGIQvVf7EbPk0 |
| Local OneDrive sync (default) | `/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans` |

## Maintainer notes

Scripts (`scripts/deliver_test_plan.py`, etc.) exist for automation and agent use. Teammates should use Cursor only. Optional `jira-dashboard/.env` with `JIRA_*` vars is only needed if running deliver scripts outside Cursor.
