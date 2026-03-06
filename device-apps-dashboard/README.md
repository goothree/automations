# Device Apps Dashboard

Compare apps installed on an Esper device with the expected app list from the Confluence **Device Apps** page.

- **Esper:** [careai.esper.cloud](https://careai.esper.cloud/groups) – apps on device by device ID
- **Confluence:** [Device Apps](https://careai.atlassian.net/wiki/spaces/~712020f8cb7a01208a478ca0225f24c07734f8/pages/2097741847/Device+Apps) – expected apps and versions

## Setup

1. Copy `.env.example` to `.env` and fill in:

   - **Esper:** Get `ESPER_API_KEY` and `ESPER_ENTERPRISE_ID` from Esper Console → API Management. Base URL for your tenant is usually `https://<tenant>-api.esper.cloud` (e.g. `https://careai-api.esper.cloud`).
   - **Confluence:** Use the same Atlassian email and API token as Jira (or set `CONFLUENCE_EMAIL` and `CONFLUENCE_API_TOKEN`). Confluence URL is typically `https://careai.atlassian.net/wiki`. The Device Apps page ID is in the URL (`2097741847`).

2. Install dependencies (from repo root or this directory):

   ```bash
   pip install -r device-apps-dashboard/requirements.txt
   ```

3. Run the server (from repo root):

   ```bash
   ./run_device_apps_dashboard
   ```
   Or: `python device-apps-dashboard/server.py`

   Dashboard: **http://127.0.0.1:5558**

## Usage

1. Get a **device ID** (UUID) from Esper (e.g. from device details in the console).
2. Enter it in the dashboard and click **Compare**.
3. The table shows each app side by side: name, package, version on device (Esper), expected version (Confluence), and status:
   - **Match** – app present with matching version
   - **Version mismatch** – app present but version differs
   - **Only on device** – installed but not in Confluence list
   - **Only in expected** – in Confluence list but not on device

## API

- `GET /api/status` – whether Esper and Confluence are configured
- `GET /api/compare?device_id=<uuid>` – returns Esper device apps, Confluence expected apps, and a comparison list

## Confluence page format

The dashboard parses **tables** on the Confluence Device Apps page. The first row is treated as the header; it looks for columns named “App”, “Name”, “Application”, or “Package” for the app name and “Version” for the version. If your page uses different column names, the parser may need to be adjusted in `confluence_client.py` (`parse_expected_apps_from_tables`).
