# Test Plan: IDA-5376

**VM* - retry 401s in-session instead of exiting the monitoring wall**

| | |
|---|---|
| **Ticket** | [IDA-5376](https://careai.atlassian.net/browse/IDA-5376) |
| **Type** | Bug |
| **Component** | careai-web-dashboard |
| **Target version** | v2026-06-GApatch |
| **Labels** | Virtual-Monitoring, auth, patient-safety |
| **Environment** | Lab or staging with VM enabled (e.g. https://lab.care.ai) |

---

## Background

### Problem

During an active monitoring session, any API 401 currently causes the auth interceptor to navigate to `/error` after 3 failed refresh attempts. That destroys `PatientMonitoringBetaComponent` / `PatientMonitoringComponent` (`ngOnDestroy` -> `endPexipCall()`), **dropping every live video stream**.

**Root cause:** Live streams (Pexip/KVS) are independent of the Angular/Auth0 token. A REST 401 does not affect video; only the navigation tears it down.

### Fix

While a monitoring wall is open, never navigate away on a 401. Keep the wall and streams mounted, recover the token in the background (capped backoff), and show a non-blocking reconnecting banner. Off the wall, behavior is unchanged.

### Key files

- `shared/service/monitoring-state.service.ts` - `enterMonitoring()` / `exitMonitoring()` counter, `isMonitoringActive`, `connectionState$`
- `shared/service/auth.interceptor.ts` - monitoring-aware 401 handling, background token-recovery loop, throttled toast
- `patient-monitoring-beta.component.{ts,html,css}` - register wall + reconnect banner
- `patient-monitoring.component.ts` - register the non-beta wall

---

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC-1 | A 401 during an active monitoring session does **not** navigate to `/error`; the wall and all live tiles stay up. |
| AC-2 | The token is refreshed in the background; once it succeeds, subsequent REST calls work again and the banner clears. |
| AC-3 | A non-blocking banner ("Reconnecting your session... monitoring continues") shows while degraded; controls degrade gracefully; video keeps playing. |
| AC-4 | Outside monitoring, a terminal 401 still routes to `/error` as before. |
| AC-5 | Nesting/popout windows are handled (multiple walls do not prematurely clear the active state). |

---

## Prerequisites

Complete these before running test cases.

### PRE-01: Build and environment (P1)

Confirm the build under test includes the IDA-5376 fix (merged branch or deployed artifact). Verify the build version matches the expected release via deployment notes, version footer, or CI artifact.

### PRE-02: Login and access (P1)

Log into the care.ai web dashboard with a user that has Virtual Monitoring permissions (e.g. `https://lab.care.ai/?scope=lab-auth-db`). Confirm you reach Command Center successfully.

### PRE-03: Microphone permission (P1)

Grant browser microphone permission when prompted. This is required to open the monitoring wall.

### PRE-04: Test rooms (P1)

Identify at least one facility with online rooms (green cloud icon) that produce live video tiles. Example: **Vineland Rack Room** with 2+ online slots. Add rooms via the Add Room modal and confirm at least 2 live streams appear on the wall.

### PRE-05: DevTools setup (P1)

Open browser DevTools before testing:

- **Network** tab with **Preserve log** enabled (filter to Fetch/XHR)
- **Application** tab (Local Storage / Session Storage)
- **Console** tab

### PRE-06: Token simulation method (P1)

Pick one method and use it consistently across all cases. Document your choice in the sign-off section.

| Method | How |
|--------|-----|
| **A** | DevTools -> Application -> clear Auth0 / localStorage token keys |
| **B** | Auth0 dashboard -> revoke user session |
| **C** | DevTools -> Network -> block API domain to force 401 |
| **D** | Wait for natural token expiry (if test env allows) |

### PRE-07: Baseline recording (P2, optional)

Before injecting a 401, capture the current URL, a screenshot, and the count of active video elements (`document.querySelectorAll('video').length` in the console). This helps prove streams were not torn down.

---

## Test cases

### TC-01: 401 during beta monitoring wall does not navigate to /error (P1)

**Maps to:** AC-1  
**Preconditions:** PRE-01 through PRE-06; use the Patient Monitoring **beta** wall if available.

1. Navigate to Virtual Monitoring and open the beta monitoring wall with multiple live room tiles (add 2+ online rooms; dismiss the Add Room modal).
   - **Expected:** Monitoring wall visible with playing video on each tile.
   - **Verify:** Visual check + video `readyState`.

2. Let streams stabilize for 30-60 seconds. Note the current URL and active video count.
   - **Expected:** URL contains `virtual-monitoring` (or beta route); videos are playing.
   - **Verify:** URL bar + DevTools.

3. Trigger a REST API 401 mid-session using your chosen simulation method while the wall remains open.
   - **Test data:** Clear/invalidate Auth0 access token, revoke session, or briefly block API.
   - **Expected:** One or more API calls return 401 in the Network tab.
   - **Verify:** Network tab.

4. Continue observing for at least 2 minutes (covers 3+ failed refresh attempts / backoff window).
   - **Test data:** Wait >= 120 seconds.
   - **Expected:** App does **not** navigate to `/error`; URL unchanged.
   - **Verify:** URL bar (pre-fix behavior would route to `/error` and end Pexip calls).

5. Verify the monitoring wall remains mounted and all tiles stay visible.
   - **Expected:** `PatientMonitoringBetaComponent` not destroyed; tile count unchanged.
   - **Verify:** UI layout + video element count.

6. Verify live video continues on all tiles (no black or frozen frames from auth failure).
   - **Expected:** Videos keep playing; `readyState >= 2`; `currentTime` advancing.
   - **Verify:** Visual + DevTools video metrics. Streams (Pexip/KVS) must be independent of REST 401.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-02: 401 during non-beta monitoring wall does not navigate to /error (P1)

**Maps to:** AC-1  
**Preconditions:** PRE-01 through PRE-06; use the standard (non-beta) Patient Monitoring wall. Validates `patient-monitoring.component.ts` registration.

1. Open the standard Virtual Monitoring wall with multiple live room tiles (same room setup as TC-01).
   - **Expected:** Monitoring wall visible with live streams.

2. Trigger token invalidation mid-session (same method as TC-01).
   - **Expected:** 401s observed in Network tab.

3. Observe for >= 2 minutes.
   - **Expected:** No navigation to `/error`; wall and streams remain.
   - **Verify:** URL + video check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-03: Reconnecting banner appears during degraded auth (P1)

**Maps to:** AC-3  
**Preconditions:** Active monitoring session with invalidated token (from TC-01 or TC-02).

1. After the 401 is triggered, confirm a non-blocking banner appears.
   - **Expected:** Banner text includes "Reconnecting your session" and indicates monitoring continues (expected copy: "Reconnecting your session... monitoring continues").
   - **Verify:** Visual inspection.

2. Verify the banner does not block video tiles or cover the primary monitoring UI.
   - **Expected:** All video tiles remain visible and unobstructed.

3. Verify the banner is non-modal (user can still interact with the wall where controls are enabled).
   - **Expected:** No full-screen blocking overlay; wall remains usable for viewing.

4. *(P2)* Verify toast notifications (if any) are throttled and do not spam on repeated 401s.
   - **Test data:** Trigger multiple API calls during degraded state.
   - **Expected:** At most occasional toast; no rapid flood.
   - **Note:** Throttled toast implemented in `auth.interceptor.ts`.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-04: Background token recovery restores REST and clears banner (P1)

**Maps to:** AC-2  
**Preconditions:** Monitoring wall open; token invalidated; banner visible.

1. Restore a valid session **without leaving** the monitoring wall.
   - **Test data:** Re-login in another tab and copy session, undo token clear, wait for silent refresh, or re-auth via Auth0 without closing the wall.
   - **Expected:** Background refresh attempts visible in Network (token endpoint calls with backoff).
   - **Verify:** Network tab.

2. After token recovery, confirm the reconnecting banner clears automatically.
   - **Expected:** Banner disappears without page reload.

3. Trigger a REST action that requires auth (e.g. refresh room list, PTZ command, patient data fetch).
   - **Expected:** API returns 200 (not 401); action succeeds.
   - **Verify:** Network tab + UI response.

4. Confirm video never stopped during the recovery window.
   - **Expected:** Continuous playback throughout.
   - **Verify:** Video element `currentTime`.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-05: Controls degrade gracefully while auth is degraded (P1)

**Maps to:** AC-3  
**Preconditions:** Monitoring wall open; token invalidated; banner showing.

1. Attempt REST-dependent controls (add/remove room, refresh lists, settings that hit the API).
   - **Expected:** Controls are disabled, show an inline error, or fail gracefully without crashing the wall.

2. Attempt local/stream controls that do not require REST (viewing streams, selecting a tile, PTZ if stream-local).
   - **Expected:** Stream viewing / PTZ continues where not API-dependent.

3. Confirm no unhandled errors in the console that destroy the component.
   - **Expected:** No fatal Angular errors; no navigation.
   - **Verify:** Console tab.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-06: 401 outside monitoring wall still routes to /error (P1)

**Maps to:** AC-4 (regression)  
**Preconditions:** User logged in; **not** on the monitoring wall.

1. Navigate to a non-monitoring page (e.g. Command Center, dashboard, settings).
   - **Expected:** Not on the `virtual-monitoring` route.

2. Invalidate the token using the same simulation method as earlier tests.
   - **Expected:** 401 responses in Network tab.

3. Trigger API call(s) and allow the auth interceptor to exhaust refresh retries (3 attempts).
   - **Test data:** Navigate or refresh to cause API calls.
   - **Expected:** After terminal 401, app navigates to `/error`.
   - **Verify:** URL becomes `/error`. Confirms off-wall behavior is unchanged.

4. Verify the error page displays as before the fix.
   - **Expected:** Standard error page shown.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-07: Popout and nested monitoring windows keep active state (P1)

**Maps to:** AC-5  
**Preconditions:** VM feature supports popout or nested wall.

1. Open the monitoring wall in the main window with live streams.
   - **Expected:** Main wall active; `enterMonitoring()` registered.
   - **Verify:** Optional DevTools check of `MonitoringStateService`.

2. Open a second monitoring wall via popout or nested window (per product support).
   - **Expected:** Both walls show streams.

3. Invalidate the token while both walls are open.
   - **Expected:** Neither wall navigates to `/error`.

4. Close one wall; verify monitoring active state persists while the other wall remains open.
   - **Test data:** Close popout or main window (one at a time).
   - **Expected:** Remaining wall still protected from 401 navigation.
   - **Note:** Counter in `monitoring-state.service` must not prematurely hit zero.

5. Close all monitoring walls; then trigger a terminal 401.
   - **Expected:** With no active wall, 401 routes to `/error` again (`exitMonitoring()` on last close).

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-08: Background retry uses capped backoff (P2)

**Preconditions:** Monitoring wall open; token invalidated.

1. Observe the Network tab for token refresh/retry calls over 3+ minutes.
   - **Expected:** Retries spaced with increasing delay; not hammering the server.
   - **Verify:** Network timing waterfall (`auth.interceptor.ts` capped backoff).

2. Confirm retries stop escalating beyond the cap (no unbounded rapid fire).
   - **Expected:** Max interval respected between attempts.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-09: Exit monitoring wall during degraded state (P2)

**Preconditions:** Banner showing; token still invalid.

1. Close the monitoring wall (navigate away or close popout) while the banner is visible.
   - **Expected:** Wall closes cleanly; streams end via normal `ngOnDestroy`.

2. On a non-monitoring page, trigger API 401 again.
   - **Expected:** Standard `/error` navigation occurs (AC-4).

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-10: Re-enter monitoring after recovery (P2)

**Preconditions:** Token recovered after TC-04.

1. Leave and re-enter the Virtual Monitoring wall.
   - **Expected:** New session starts normally; no stale banner.

2. Add rooms and confirm streams and API calls work.
   - **Expected:** Full functionality restored (UI + Network 200s).

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-11: Ticket QA scenario - mid-session token revoke (P1)

**Maps to:** QA note on ticket  
**Preconditions:** Per ticket QA bullet.

1. Start an active monitoring session with multiple live streams (2+ rooms).
   - **Expected:** Streams playing.

2. Revoke or clear the token mid-session.
   - **Expected:** 401 triggered (Network tab).

3. Confirm video continues for >= 60 seconds.
   - **Expected:** Video uninterrupted.

4. Confirm the reconnecting banner shows.

5. Restore the token and confirm recovery.
   - **Expected:** Banner clears; API calls succeed.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

## Sign-off

### SO-01: Test completion (P1)

**Preconditions:** All P1 test cases executed.

Record the overall result and any defects filed. All acceptance criteria should be met, or defects linked to [IDA-5376](https://careai.atlassian.net/browse/IDA-5376).

| Field | Value |
|-------|-------|
| **Overall result** | Pass / Fail |
| **Tester** | |
| **Date** | |
| **Build tested** | |
| **Token simulation method used** | Method A / B / C / D |
| **Defects filed** | |

---

## Quick reference: priority order

Run P1 cases first in this order for minimum coverage:

1. TC-01 or TC-02 (wall stays up on 401)
2. TC-03 (banner)
3. TC-04 (recovery)
4. TC-05 (graceful degradation)
5. TC-06 (regression off-wall)
6. TC-07 (popout/nesting, if supported)
7. TC-11 (ticket QA scenario)

P2 cases (TC-08, TC-09, TC-10) can follow as time allows.
