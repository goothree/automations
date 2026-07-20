# Jira Team Dashboard

A small Flask app that fetches issues from Jira and shows them in a simple dashboard so your team can see what needs to be done.

## Setup

1. **Create a `.env` file** in `jira-dashboard/` (copy from `.env.example`):

   ```bash
   cp jira-dashboard/.env.example jira-dashboard/.env
   ```

2. **Set your Jira credentials** in `jira-dashboard/.env`:

   - **JIRA_URL** – Your Jira base URL, e.g. `https://your-company.atlassian.net`
   - **JIRA_EMAIL** – Your Atlassian account email
   - **JIRA_API_TOKEN** – Create one at [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

3. **Install dependencies** (from project root):

   ```bash
   pip install -r jira-dashboard/requirements.txt
   ```

   Or use the run script (it will try to install if needed):

   ```bash
   ./run_jira_dashboard
   ```

## Running the dashboard

From the **project root**:

```bash
./run_jira_dashboard
```

Or manually:

```bash
python jira-dashboard/server.py
```

By default the app runs on **port 5557** (the Test Runner dashboard uses 5556). Open http://127.0.0.1:5557 in your browser.

## Configuration

| Variable        | Required | Description |
|----------------|----------|-------------|
| `JIRA_URL`     | Yes      | Jira base URL (e.g. `https://your.atlassian.net`) |
| `JIRA_EMAIL`   | Yes      | Your Atlassian email |
| `JIRA_API_TOKEN` | Yes   | API token from id.atlassian.com |
| `JIRA_PROJECT` | No       | Restrict to one project key (e.g. `MYPROJ`) |
| `JIRA_TEAM_JQL`| No       | Custom JQL (overrides default query). Default: unresolved issues, ordered by updated. |

## Default query

If `JIRA_TEAM_JQL` is not set, the app uses:

- **JQL:** `resolution = Unresolved ORDER BY updated DESC`
- If `JIRA_PROJECT` is set, it adds `project = <key> AND` in front.

To show only issues assigned to specific people or a team, set `JIRA_TEAM_JQL` in `.env`, for example:

```env
JIRA_TEAM_JQL=assignee in (alice, bob) AND resolution = Unresolved ORDER BY duedate ASC, updated DESC
```

## API

- **GET /api/status** – Returns `{ "configured": true/false }`.
- **GET /api/issues** – Returns `{ "issues": [...], "total": N }`. Each issue has `key`, `summary`, `status`, `assignee`, `priority`, `due_date`, `type`, `link`.

## Test plan delivery

See **[docs/test-plan-workflow.md](../docs/test-plan-workflow.md)** for team setup (Cursor-only).

Teammates ask in Cursor chat:

> Review and create test plan for https://careai.atlassian.net/browse/IDA-XXXX

SharePoint sync folder (hardcoded default): `/Users/michael.guthrie/Library/CloudStorage/OneDrive-Stryker/TestPlans`
