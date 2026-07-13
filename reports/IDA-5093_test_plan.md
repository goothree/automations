# Test Plan: IDA-5093

**VC - Task status ribbon**

| | |
|---|---|
| **Ticket** | [IDA-5093](https://careai.atlassian.net/browse/IDA-5093) |
| **Type** | Story |
| **Related** | [OPD-157](https://careai.atlassian.net/browse/OPD-157) (admin toggle: "Show in VC Task Ribbon?") |
| **Assignee** | Ryan Smith |
| **Priority** | High |
| **Target version** | v2026-07 |
| **Environment** | Lab (deployed per ticket comment 2026-07-08); staging as available |

---

## Background

### Problem

Virtual nurses need a quick view of how many tasks are in each status (Ready, In Progress, Scheduled, etc.) without manually counting rows in the task queue. Today they must scan and count the list themselves.

### Solution

A **task status ribbon** at the top of the Virtual Care (VC) task queue shows live counts per status. Virtual nurses can see workload distribution at a glance and (when implemented) click a tile to filter the list.

### Implementation notes (from dev QA handoff)

- Ribbon renders **above the task list** inside the VC task queue.
- Which statuses appear is driven per-tenant by the `showStatusOnRibbon` flag on each task status (from `/task-statuses`).
- If **no** status is enabled for a tenant, the ribbon falls back to the **default 5**: Queued, Overdue, Chart Review, Incomplete, Ready.
- Counts respect the user's **location / date / task-type** filters.
- Counts are **standalone** — every configured ribbon tile shows its full count even when the task list is filtered by status (including when a ribbon tile is active).
- **Click a tile** to filter the list by that status; click the same active tile again to clear the filter.
- Counts update on the **30s auto-refresh** and on **Firebase** task-status events.
- Tenant ribbon configuration is managed in **Ops/Admin Dashboard → Configure Tasks → Task Status** via the **"Show in VC Task Ribbon?"** toggle ([OPD-157](https://careai.atlassian.net/browse/OPD-157)).
- Up to **8** statuses can be enabled per tenant; attempting a 9th shows a validation/error message.
- **Cache note:** after changing ribbon toggles in admin, the VC ribbon reflects the change only after the tenant's `/task-statuses` cache refreshes, or immediately if the cache is cleared. This is expected backend behavior, not a UI defect.
- **Naming note:** the `/task-statuses` API uses internal IDs (e.g. `OVERDUE`) with `displayName` values that may differ from ribbon labels (e.g. `OVERDUE` → display name "Queued"). Verify the ribbon shows the correct **display names**, not raw IDs.

### Scope clarification vs. original ticket

The original ticket description included a criterion (since struck through in Jira) that ribbon counts should ignore status filters. The **shipped behavior** matches the developer handoff: ribbon counts ignore **status** filters but still honor **location / date / task-type** filters. Test against shipped behavior.

---

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC-1 | A ribbon at the top of the VC task queue shows the number of tasks in each configured status. |
| AC-2 | By default (no tenant ribbon config), the ribbon shows counts for: **Queued**, **Overdue**, **Chart Review**, **Incomplete**, **Ready**. |
| AC-3 | Statuses shown in the ribbon are configurable per tenant (via `showStatusOnRibbon` / admin toggle), up to the configured maximum (8). |
| AC-4 | Ribbon counts reflect the user's **filtered preferences** for location, date, and task type. |
| AC-5 | Ribbon counts remain accurate for **all** configured statuses even when the user filters the task list by status. |
| AC-6 *(implemented)* | Clicking a ribbon tile applies a status filter to the task list; clicking the active tile again clears it. |
| AC-7 *(implemented)* | Counts update automatically on the 30s refresh cycle and when Firebase publishes task status changes. |

---

## Prerequisites

Complete these before running test cases.

### PRE-01: Build and environment (P1)

Confirm the build under test includes the IDA-5093 fix (lab deployment noted 2026-07-08). Verify build/version via deployment notes or app footer.

**Environment:** `https://lab.care.ai` (or equivalent lab/staging with VC enabled).

### PRE-02: Login and access (P1)

Log into the care.ai web dashboard with a user that has **Virtual Care / Virtual Nursing** permissions and access to the VC task queue.

### PRE-03: Test tenants (P1)

Identify or provision tenants for the scenarios below. Document tenant names in the sign-off section.

| Tenant profile | Purpose |
|----------------|---------|
| **Tenant A** | No ribbon statuses enabled (`showStatusOnRibbon` false for all) — tests default 5 fallback |
| **Tenant B** | Custom ribbon config (3–8 statuses enabled) — tests tenant configuration |
| **Tenant C** *(optional)* | Tenant with many task statuses (10+) — tests max-limit validation in admin |

### PRE-04: Task data (P1)

Ensure each test tenant has tasks spread across multiple statuses (at minimum: Queued/OVERDUE, Ready, Chart Review, Incomplete, and at least one other). Record baseline counts per status for manual cross-check.

Suggested approach:

- Use the VC task queue with filters cleared (or note active filters).
- Manually count tasks per status in the list, or query via API if available.
- Note tasks across **multiple locations** and **task types** for filter testing.

### PRE-05: Admin dashboard access (P1)

Obtain credentials for the **Ops/Admin Dashboard** with permission to edit **Configure Tasks → Task Status** (required for OPD-157 / tenant config cases). Coordinate with ops if cache must be cleared after config changes.

### PRE-06: DevTools setup (P2, recommended)

Open browser DevTools before live-update cases:

- **Network** tab with **Preserve log** (filter to Fetch/XHR; watch `/task-statuses` and task list API calls)
- **Console** tab (watch for errors during ribbon interactions)

### PRE-07: Second client / session (P2, for Firebase cases)

Have a second browser tab, user session, or API path available to change a task's status while the VC queue remains open in the primary session.

---

## Test cases

### TC-01: Ribbon visible at top of VC task queue (P1)

**Maps to:** AC-1  
**Preconditions:** PRE-01, PRE-02; user on VC task queue with tasks present.

1. Navigate to Virtual Care and open the **task queue**.
   - **Expected:** Task list loads with tasks visible.
   - **Verify:** Visual check.

2. Confirm a **status ribbon** appears at the top of the task queue, above the task list.
   - **Expected:** Horizontal ribbon with one tile per configured/default status; each tile shows a **label** and a **numeric count**.
   - **Verify:** Visual inspection; ribbon is not hidden behind other UI.

3. Confirm ribbon tiles use human-readable status names (display names), not raw API IDs.
   - **Expected:** Labels such as "Queued", "Ready" — not "OVERDUE", "READY", etc.
   - **Verify:** Visual inspection; optional Network → `/task-statuses` response cross-check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-02: Default five statuses when tenant has no ribbon config (P1)

**Maps to:** AC-2  
**Preconditions:** PRE-03 Tenant A (no `showStatusOnRibbon` enabled); PRE-04.

1. Log into **Tenant A** and open the VC task queue.
   - **Expected:** Ribbon visible.

2. Count the ribbon tiles and read each label.
   - **Expected:** Exactly **5** tiles labeled **Queued**, **Overdue**, **Chart Review**, **Incomplete**, **Ready** (in the product's configured order).
   - **Verify:** Visual inspection.

3. Cross-check each tile count against tasks in the queue (with location/date/task-type filters at default / cleared).
   - **Expected:** Each count matches the number of tasks in that status for the current non-status filters.
   - **Verify:** Manual count or API tally; document any tenant-specific display-name mapping (e.g. OVERDUE → "Queued").

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-03: Tenant-configured ribbon statuses (P1)

**Maps to:** AC-3  
**Preconditions:** PRE-03 Tenant B; PRE-05; ribbon statuses pre-enabled in admin (or enable during test).

1. In **Admin Dashboard → Configure Tasks → Task Status**, enable **"Show in VC Task Ribbon?"** for a specific set of statuses (e.g. 4 statuses). Save.
   - **Test data:** e.g. Ready, Scheduled, In Progress, Chart Review.
   - **Expected:** Toggles persist after save.
   - **Verify:** Admin UI.

2. Wait for `/task-statuses` cache refresh **or** request cache clear for the tenant (per PRE-05).
   - **Expected:** Updated config available to VC app.
   - **Verify:** Network → `/task-statuses` includes `showStatusOnRibbon: true` for enabled statuses.

3. Open the VC task queue for **Tenant B**.
   - **Expected:** Ribbon shows **only** the enabled statuses (not the default 5 unless those are the ones enabled).
   - **Verify:** Tile labels and count match enabled set.

4. Disable one ribbon status in admin; after cache refresh, reload VC queue.
   - **Expected:** That status tile disappears from the ribbon.
   - **Verify:** Visual + `/task-statuses`.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-04: Maximum ribbon status limit enforced in admin (P1)

**Maps to:** AC-3  
**Preconditions:** PRE-05; tenant with enough statuses to exceed limit (Tenant B or C).

1. In admin, enable **"Show in VC Task Ribbon?"** for **8** statuses. Save.
   - **Expected:** Save succeeds; all 8 enabled.
   - **Verify:** Admin UI + `/task-statuses`.

2. Attempt to enable a **9th** status for the ribbon.
   - **Expected:** Validation/error message; 9th toggle does not save (or reverts).
   - **Verify:** Admin UI error message text.

3. Open VC task queue.
   - **Expected:** Ribbon shows at most **8** tiles.
   - **Verify:** Visual count of tiles.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-05: Ribbon counts respect location filter (P1)

**Maps to:** AC-4  
**Preconditions:** PRE-04; tasks exist in **multiple locations**; baseline counts recorded.

1. Open VC task queue with all locations selected (or default broad filter). Note ribbon counts for at least two statuses.
   - **Expected:** Baseline counts recorded.

2. Apply a **location** filter narrowing to a single facility/unit with known tasks.
   - **Expected:** Ribbon counts **decrease or change** to reflect only tasks in that location.
   - **Verify:** Manual count of filtered tasks per status vs. ribbon tiles.

3. Clear the location filter.
   - **Expected:** Ribbon counts return to baseline.
   - **Verify:** Visual comparison to step 1.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-06: Ribbon counts respect date filter (P1)

**Maps to:** AC-4  
**Preconditions:** PRE-04; tasks exist on **multiple dates**.

1. Note ribbon counts with default/broad date filter.

2. Apply a **date** filter (e.g. today only, or a narrow date range with known task volume).
   - **Expected:** Ribbon counts update to match tasks within that date range only.
   - **Verify:** Manual count vs. ribbon.

3. Change date filter to a range with **zero** tasks for a given status.
   - **Expected:** That status tile shows **0**.
   - **Verify:** Visual check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-07: Ribbon counts respect task-type filter (P1)

**Maps to:** AC-4  
**Preconditions:** PRE-04; tasks of **multiple task types** exist.

1. Note ribbon counts with all task types selected.

2. Apply a **task-type** filter to a single type with known distribution.
   - **Expected:** Ribbon counts reflect only tasks of that type.
   - **Verify:** Manual count vs. ribbon.

3. Combine location + task-type filters.
   - **Expected:** Counts reflect the **intersection** of active non-status filters.
   - **Verify:** Manual count.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-08: Ribbon counts unchanged when task list filtered by status (P1)

**Maps to:** AC-5  
**Preconditions:** PRE-04; multiple statuses with non-zero counts.

1. With filters cleared (except defaults), record ribbon counts for **all** tiles.

2. Apply a **status filter** via the standard task-queue filter UI (not the ribbon) to a single status (e.g. Ready).
   - **Expected:** Task **list** shows only Ready tasks.
   - **Verify:** List row count.

3. Compare ribbon tile counts to step 1.
   - **Expected:** **All** ribbon tiles still show the **same counts** as before the status filter (standalone counts).
   - **Verify:** Side-by-side or screenshot comparison. Non-filtered statuses must **not** drop to 0.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-09: Click ribbon tile to filter task list (P1)

**Maps to:** AC-6  
**Preconditions:** PRE-04; ribbon tile with count > 0.

1. Click a ribbon tile (e.g. **Ready**).
   - **Expected:** Task list filters to tasks in that status only; tile appears **selected/active**.
   - **Verify:** List contents + visual active state on tile.

2. Confirm the active tile count still matches the full standalone count (not just visible rows if pagination exists).
   - **Expected:** Tile count unchanged from TC-08 behavior.
   - **Verify:** Ribbon number vs. total tasks in that status (API or count across pages).

3. Click the **same active tile** again.
   - **Expected:** Status filter **clears**; full task list returns; tile no longer highlighted.
   - **Verify:** List + ribbon state.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-10: Click different ribbon tiles to switch status filter (P2)

**Maps to:** AC-6  
**Preconditions:** PRE-04; at least two statuses with tasks.

1. Click tile A (e.g. Ready). Confirm list filtered to A.
2. Click tile B (e.g. Chart Review) without clearing first.
   - **Expected:** Filter switches to B; tile B active, tile A inactive; list shows B tasks only.
   - **Verify:** List + ribbon highlight.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-11: Ribbon updates on 30s auto-refresh (P1)

**Maps to:** AC-7  
**Preconditions:** PRE-07; VC task queue open; known baseline counts.

1. Leave the VC task queue open. Note a ribbon tile count and timestamp.
2. From a **second client**, create a new task (or transition a task **into** a ribbon status) that matches current location/date/task-type filters.
3. Wait up to **35 seconds** without manually refreshing the page.
   - **Expected:** Relevant ribbon tile count **increments** automatically.
   - **Verify:** Visual watch; optional Network tab for polling request.

4. From the second client, transition a task **out of** that status (or void/cancel).
5. Wait up to **35 seconds**.
   - **Expected:** Tile count **decrements** accordingly.
   - **Verify:** Visual watch.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-12: Ribbon updates on Firebase task-status event (P1)

**Maps to:** AC-7  
**Preconditions:** PRE-07; VC task queue open.

1. Note current counts on two adjacent status tiles (source status S1 → target status S2).
2. From a **second client**, transition a task from **S1** to **S2** (matching active non-status filters).
   - **Expected:** S1 count decreases and S2 count increases **promptly** (typically before next 30s poll).
   - **Verify:** Visual watch (< 30s); Console free of errors.

3. Repeat with void/cancel of a task in a ribbon status.
   - **Expected:** Corresponding tile decrements without full page reload.
   - **Verify:** Visual check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-13: Zero-count tiles display correctly (P2)

**Maps to:** AC-1, AC-2  
**Preconditions:** Apply filters or use tenant data so at least one ribbon status has **0** tasks.

1. Confirm the ribbon still shows the status tile with count **0**.
   - **Expected:** Tile visible with "0"; layout does not collapse or misalign.
   - **Verify:** Visual inspection.

2. Click a zero-count tile.
   - **Expected:** List shows empty state (no tasks); no JS errors.
   - **Verify:** List + Console.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-14: Ribbon + status filter + other filters combined (P2)

**Maps to:** AC-4, AC-5  
**Preconditions:** PRE-04.

1. Apply location and date filters. Record ribbon counts.
2. Click a ribbon tile to filter by status.
   - **Expected:** List shows intersection of **all** filters; ribbon counts for **all** tiles remain standalone totals for location/date/task-type (ignoring status filter).
   - **Verify:** Manual reasoning: e.g. Ready tile count = all Ready tasks in filtered location/date/type, not just visible page.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-15: Admin config cache delay (P2)

**Maps to:** AC-3  
**Preconditions:** PRE-05.

1. Change ribbon toggle for one status in admin and save.
2. Immediately reload VC task queue (**without** cache clear).
   - **Expected:** Ribbon may still show **previous** configuration (known cache behavior).
   - **Verify:** Compare to old config; document delay if observed.

3. After cache refresh or explicit cache clear, reload VC queue.
   - **Expected:** Ribbon reflects new configuration.
   - **Verify:** Visual check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-16: Regression — VC task queue without ribbon breakage (P1)

**Maps to:** Regression  
**Preconditions:** PRE-01, PRE-02.

1. Open VC task queue and perform standard workflows:
   - Sort / scroll the task list
   - Open a task detail / start a session (if applicable)
   - Apply and clear filters via existing filter UI
   - Paginate or load more tasks (if applicable)
   - **Expected:** All pre-existing task queue behavior works; no layout overlap with ribbon; no console errors.
   - **Verify:** Functional smoke + Console.

2. Navigate away from VC and return.
   - **Expected:** Ribbon re-renders with current counts.
   - **Verify:** Visual check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-17: Regression — task list filter UI still works independently (P1)

**Maps to:** Regression  
**Preconditions:** PRE-04.

1. Apply status filter using the **standard filter control** (not ribbon).
   - **Expected:** List filters correctly; ribbon remains visible with standalone counts.

2. Clear filter using standard control while a ribbon tile is **not** active.
   - **Expected:** Full list restored.

3. Apply filter via ribbon, then clear via **standard filter control**.
   - **Expected:** List and ribbon active state stay **in sync** (no stale highlight on ribbon tile).
   - **Verify:** Visual sync between ribbon and filter UI.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-18: Display name vs. API ID mapping (P2)

**Maps to:** AC-2 (edge case from dev discussion)  
**Preconditions:** Tenant where `/task-statuses` includes `OVERDUE` with `displayName` "Queued".

1. Fetch or inspect `/task-statuses` for the tenant.
2. Compare API `displayName` / `_id` to ribbon labels.
   - **Expected:** Ribbon shows **"Queued"** for the OVERDUE status (per API display name), and a separate **"Overdue"** tile if that status exists distinctly in defaults/config.
   - **Verify:** No duplicate/confusing labels; counts align with correct status bucket.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-19: Ticket QA checklist — end-to-end smoke (P1)

**Maps to:** Dev QA handoff checklist  
**Preconditions:** PRE-01 through PRE-05.

Execute the developer verification checklist as a single smoke pass:

1. Tenant with no ribbon statuses → default 5 shown.
2. Enable/disable statuses in admin → ribbon matches after cache refresh (≤ 8).
3. Attempt 9th enable → error message.
4. Apply location / date / task-type filters → counts change accordingly.
5. Apply status filter or click ribbon tile → list narrows; **all** ribbon tiles keep standalone counts.
6. Click ribbon tile → filter; click again → clear.
7. Wait ~30s or change status from another client → counts update without manual refresh.
8. Void/cancel and create tasks → counts decrement/increment.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

## Sign-off

### SO-01: Test completion (P1)

**Preconditions:** All P1 test cases executed.

Record the overall result and any defects filed. All acceptance criteria should be met, or defects linked to [IDA-5093](https://careai.atlassian.net/browse/IDA-5093) / [OPD-157](https://careai.atlassian.net/browse/OPD-157).

| Field | Value |
|-------|-------|
| **Overall result** | Pass / Fail |
| **Tester** | |
| **Date** | |
| **Build tested** | |
| **Tenants used** | Tenant A: / Tenant B: / Tenant C: |
| **Cache clear required?** | Yes / No |
| **Defects filed** | |

---

## Quick reference: priority order

Run P1 cases first in this order for minimum coverage:

1. TC-01 (ribbon visible)
2. TC-02 (default 5)
3. TC-05, TC-06, TC-07 (non-status filters)
4. TC-08 (standalone counts vs. status filter)
5. TC-09 (click-to-filter)
6. TC-11, TC-12 (live updates)
7. TC-03, TC-04 (tenant config + limit)
8. TC-16, TC-17 (regression)
9. TC-19 (dev QA smoke checklist)

P2 cases (TC-10, TC-13, TC-14, TC-15, TC-18) can follow as time allows.
