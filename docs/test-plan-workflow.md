# Test Plan Workflow (Jira → Word → Testpad → SharePoint)

Team workflow for creating test plans from Jira tickets. Scripts and Cursor rules live in this repo; SharePoint delivery uses the shared QA TestPlans folder.

## Shared locations (hardcoded defaults)

| Setting | Value |
|---------|--------|
| SharePoint folder | https://stryker-my.sharepoint.com/:f:/p/michael_guthrie/IgBAyEORHosITrKk3lSVFca_AePm9AG_nzqGIQvVf7EbPk0 |
| Local OneDrive sync | `/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans` |
| SharePoint site base | `https://stryker-my.sharepoint.com/personal/michael_guthrie_stryker_com` |
| Folder path on site | `Documents/TestPlans` |
| Link manifest | `/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans/_sharepoint_links.json` |

These defaults are in `jira-dashboard/config.py`. Jira comment links use `?web=1` so files open in Word Online (not a local download).

## One-time setup

1. **Clone** the `care.ai` repo and create a venv:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r jira-dashboard/requirements.txt python-docx
   ```

2. **Jira credentials** — copy `jira-dashboard/.env.example` to `jira-dashboard/.env` and set:

   - `JIRA_URL=https://careai.atlassian.net`
   - `JIRA_EMAIL` — your Atlassian email
   - `JIRA_API_TOKEN` — from [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

3. **OneDrive sync** — in OneDrive, add a shortcut to the SharePoint TestPlans folder (link above). Confirm files appear at:

   `/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans`

4. **Cursor (optional)** — open this repo in Cursor. The rule `.cursor/rules/test-plan-sharepoint.mdc` tells the agent to run the full delivery workflow when you ask for a test plan.

## Creating a test plan

### Option A — Cursor agent

In Cursor, ask:

> Review and create test plan for https://careai.atlassian.net/browse/IDA-XXXX

The agent will generate the plan, deliver to SharePoint, and post a Jira comment.

### Option B — Scripts

1. Write the test plan markdown: `reports/IDA-XXXX_test_plan.md`
2. Convert to Word:

   ```bash
   .venv/bin/python scripts/md_to_docx_test_plan.py reports/IDA-XXXX_test_plan.md
   ```

3. Deliver everything (Testpad txt, SharePoint copy, Jira comment):

   ```bash
   .venv/bin/python scripts/deliver_test_plan.py IDA-XXXX
   ```

   Flags: `--skip-sharepoint`, `--skip-jira`

4. Or generate Testpad text only:

   ```bash
   .venv/bin/python scripts/test_plan_to_testpad.py reports/IDA-XXXX_test_plan.md
   ```

## What gets delivered

For ticket `IDA-XXXX`:

| Output | Local path | SharePoint |
|--------|------------|------------|
| Word test plan | `reports/IDA-XXXX_test_plan.docx` | `TestPlans/IDA-XXXX_test_plan.docx` |
| Testpad import | `reports/IDA-XXXX_testpad.txt` | `TestPlans/IDA-XXXX_testpad.txt` |
| Jira comment | — | Link to `.docx` with `?web=1` |

## Requestly (when relevant)

For test plans that simulate HTTP/auth failures (401, 403, 500, timeouts), include **Requestly** in prerequisites. See `.cursor/rules/test-plan-sharepoint.mdc` for the standard Method E wording.
