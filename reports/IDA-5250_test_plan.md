# Test Plan: IDA-5250

**VC - Privacy Mode**

| | |
|---|---|
| **Ticket** | [IDA-5250](https://careai.atlassian.net/browse/IDA-5250) |
| **Type** | Task |
| **Related** | [IDA-4078](https://careai.atlassian.net/browse/IDA-4078) (dependency — must be deployed with IDA-5250) |
| **Assignee** | Vijaya Durga Pantham |
| **Priority** | Medium |
| **Status** | In QA |
| **Target version** | v2026-07 |
| **Environment** | Lab (deployed per ticket comment); staging as available |

---

## Background

### Problem

When a sitter in VM/VM* enables privacy mode during a concurrent Virtual Care (VC) video session, the VC user also sees the obscured video feed. There is no way for the VC user to turn privacy mode off, which blocks their ability to see the patient and complete their task.

### Solution

Add a **privacy view on/off control** in VC so virtual nurses can disable privacy mode when needed. VC user actions **override** VM/VM* user actions when both users toggle privacy at the same time. VM/VM* users are notified when a VC user changes privacy mode (toast + activity feed). VC activity feed records privacy changes initiated by the VC user.

### Implementation notes (from dev / QA handoff)

- Privacy control appears in the **right-side panel** during an active VC session — in a **new row** below night vision, focus, and PIP controls (or utility bar if layout differs).
- **No privacy timer in VC** — confirmed with product (Ramya / Irene). Timer remains a VM/VM* concern only ([IDA-4078](https://careai.atlassian.net/browse/IDA-4078) addresses timer visibility for concurrent VM users).
- **Tenant config:** `otherWebSettings.showPrivacyToggleInVc` (default `true`). When `false`, the VC privacy control is hidden.
- **Toast behavior:** Show toast to the **other** user only — the user who toggled privacy should **not** see their own toast. Toast in VM/VM* should include **unit and area name** (per QA feedback).
- **Activity feed labels:** VC and VM/CC activities use **"Privacy Mode On"** / **"Privacy Mode Off"** (not generic On/Off).
- **VC activities scope:** VC activity list is **task-based** — privacy changes made by a VM user while VC is in session may **not** appear in VC activities (expected per dev). VM activities **do** show VC-initiated privacy changes.
- **VC ↔ VM toggle sync:** When one user toggles privacy, the other user's toggle icon/state should update to match (fixed in follow-up deployment).
- **Duplicate toast:** Addressed in follow-up fix — verify no duplicate toasts when VC toggles.
- **Incognito caveat:** Testing in **Incognito/private browsing** may prevent toast messages and toggle state sync from appearing. Use normal browser sessions for QA.
- **Deployment dependency:** [IDA-4078](https://careai.atlassian.net/browse/IDA-4078) must be deployed alongside IDA-5250.
- **Production config:** Add `VIRTUALVISIT_PRIVACY_MODE_ON` and `VIRTUALVISIT_PRIVACY_MODE_OFF` to `AMBIENT_MONITORING_EVENT_CODES` and `AREA_EVENT_CODES` enumerators.

### Scope clarification vs. original ticket

The original ticket mentioned VM/VM* activity feed for VC-initiated changes; this was implemented. VM-initiated privacy changes do not currently generate VM activity events (pre-existing behavior); a separate ticket may be created if needed. Test against **shipped behavior** described above.

---

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC-1 | VC users see a privacy view on/off control in the right-side session panel when tenant config `showPrivacyToggleInVc` is enabled (default). |
| AC-2 | VC user can turn privacy mode **off** when a VM/VM* sitter has enabled it during a concurrent VC session; video feed becomes unobscured for VC. |
| AC-3 | VC user can turn privacy mode **on** from VC during a concurrent session. |
| AC-4 | When VC and VM/VM* users toggle privacy simultaneously, the **VC user's action wins**. |
| AC-5 | VM/VM* user receives a **toast** (with unit + area name) when a VC user changes privacy mode — but **not** when they change it themselves. |
| AC-6 | VC activity feed records **"Privacy Mode On"** / **"Privacy Mode Off"** when the **VC user** toggles privacy. |
| AC-7 | VM/CC activity feed records privacy mode on/off events when applicable (VC-initiated changes visible in VM). |
| AC-8 | Privacy toggle state stays **in sync** between VC and VM/VM* when either user changes privacy mode. |
| AC-9 | Tenant config `showPrivacyToggleInVc = false` hides the VC privacy control. |
| AC-10 | **No** privacy timer is displayed in VC during privacy mode. |
| AC-11 | Multi-sitter scenarios work correctly (multiple VM users monitoring the same room). |

---

## Prerequisites

Complete these before running test cases.

### PRE-01: Build and environment (P1)

Confirm the build under test includes **IDA-5250** and **IDA-4078** (lab deployment noted in ticket). Verify build/version via deployment notes or app footer.

**Environment:** `https://lab.care.ai` (or equivalent lab/staging with VC and VM enabled).

**Do not use Incognito/private browsing** — toast and toggle sync may not work (per dev handoff).

### PRE-02: Login and access (P1)

Obtain two user accounts:

| User | Role | Purpose |
|------|------|---------|
| **User 1 (VM)** | Virtual Monitoring sitter | Enables/disables privacy from VM/VM* wall |
| **User 2 (VC)** | Virtual Care nurse | Joins concurrent VC session; uses new privacy control |

Both users need access to the **same room/area** with a live device.

### PRE-03: Test rooms and devices (P1)

Identify at least one room with:

- Online device / live video in VM
- Ability to start a VC session to the same room (concurrent VM + VC)
- Known **unit name** and **area/room name** for toast verification

Record room, unit, and area identifiers in the sign-off section.

### PRE-04: Multi-sitter setup (P1)

For multi-sitter cases, identify a room that supports **2+ concurrent VM sitters** (or provision a second VM user — **User 3**).

### PRE-05: Tenant configuration access (P1)

Obtain access to tenant settings (Careai admin) to toggle `otherWebSettings.showPrivacyToggleInVc`.

| Tenant profile | Config | Purpose |
|----------------|--------|---------|
| **Tenant A** | `showPrivacyToggleInVc: true` (default) | Primary functional testing |
| **Tenant B** | `showPrivacyToggleInVc: false` | Control hidden when disabled |

### PRE-06: DevTools setup (P2, recommended)

Open browser DevTools in both sessions before live-sync cases:

- **Console** tab (watch for errors during privacy toggles)
- **Network** tab with **Preserve log** (optional: watch privacy-related API/events)

### PRE-07: Baseline privacy behavior (P1)

Confirm standard VM privacy mode works before VC override testing:

1. VM user enables privacy → video darkens for all VM viewers.
2. Privacy timer visible in VM (per IDA-4078 fix).
3. Document baseline so VC override cases have a known starting point.

---

## Test cases

### TC-01: VC privacy control visible when tenant config enabled (P1)

**Maps to:** AC-1, AC-9  
**Preconditions:** PRE-01, PRE-02, PRE-03, PRE-05 Tenant A.

1. Log in as **User 2 (VC)** on **Tenant A** and start a VC video session to the test room.
   - **Expected:** VC session UI loads with right-side control panel.
   - **Verify:** Visual check.

2. Locate the **privacy view on/off** control in the right panel (new row below night vision / focus / PIP, or utility bar).
   - **Expected:** Privacy toggle visible and labeled clearly (on/off or equivalent icon + state).
   - **Verify:** Visual inspection; compare to dev screenshot in ticket comments if needed.

3. Confirm **no privacy timer** overlay appears in the VC video area.
   - **Expected:** No countdown/timer UI in VC view.
   - **Verify:** Visual check throughout session.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-02: VC privacy control hidden when tenant config disabled (P1)

**Maps to:** AC-9  
**Preconditions:** PRE-05 Tenant B; active VC session.

1. Set `showPrivacyToggleInVc = false` for **Tenant B** and save tenant config.
2. Start a VC session on **Tenant B**.
   - **Expected:** Privacy control **not** visible in VC session panel.
   - **Verify:** Visual inspection of right panel and utility bar.

3. Re-enable `showPrivacyToggleInVc = true`; reload VC session.
   - **Expected:** Privacy control reappears.
   - **Verify:** Visual check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-03: VC user turns privacy OFF when VM sitter enabled it (P1)

**Maps to:** AC-2  
**Preconditions:** PRE-01 through PRE-03; VM and VC concurrent on same room.

1. **User 1 (VM)** connects to the test room and enables **privacy mode** (Privacy View → Patient Privacy).
   - **Expected:** Video darkens/obscures for VM user; privacy toggle shows ON in VM.
   - **Verify:** Visual check in VM.

2. **User 2 (VC)** joins the same room via VC video session.
   - **Expected:** VC user sees obscured video; VC privacy toggle reflects ON state.
   - **Verify:** Visual check in VC.

3. **User 2 (VC)** toggles privacy **OFF** using the new VC control.
   - **Expected:** Video feed unobscured for VC user; patient visible.
   - **Verify:** Visual check — video no longer darkened.

4. Confirm VM user's view updates to match (privacy off).
   - **Expected:** VM video unobscured; VM privacy toggle shows OFF.
   - **Verify:** Visual check in VM session.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-04: VC user turns privacy ON during concurrent session (P1)

**Maps to:** AC-3  
**Preconditions:** PRE-01 through PRE-03; privacy mode currently OFF.

1. **User 1 (VM)** and **User 2 (VC)** both connected to the same room (privacy OFF).
2. **User 2 (VC)** toggles privacy **ON**.
   - **Expected:** Video obscured for VC user.
   - **Verify:** Visual check.

3. Confirm VM user's view and toggle sync to ON.
   - **Expected:** VM video darkened; VM privacy toggle ON.
   - **Verify:** Visual check in VM.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-05: VC action overrides VM when both toggle simultaneously (P1)

**Maps to:** AC-4  
**Preconditions:** PRE-01 through PRE-03; two browsers ready.

1. Start with privacy **OFF**; both users connected (VM + VC).
2. At approximately the same time:
   - **User 1 (VM)** toggles privacy **ON**
   - **User 2 (VC)** toggles privacy **OFF** (or opposite directions)
   - **Expected:** Final state matches **VC user's action** (VC wins).
   - **Verify:** Observe final video state and toggle positions in both UIs after sync settles (< 5s).

3. Repeat with reversed intent: VM tries OFF, VC tries ON (or hold VM ON while VC toggles OFF).
   - **Expected:** VC action prevails in all cases.
   - **Verify:** Final state in both sessions.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-06: VM toast when VC changes privacy — content and recipient (P1)

**Maps to:** AC-5  
**Preconditions:** PRE-01 through PRE-03; known unit and area names.

1. **User 1 (VM)** monitoring room; **User 2 (VC)** in active VC session. Privacy OFF.
2. **User 2 (VC)** toggles privacy **ON**.
   - **Expected (VC):** VC user does **not** see a toast for their own action.
   - **Expected (VM):** **User 1 (VM)** sees a toast notifying privacy was enabled; toast includes **unit name** and **area/room name**.
   - **Verify:** Watch both screens; capture toast text.

3. **User 2 (VC)** toggles privacy **OFF**.
   - **Expected (VM):** Toast to VM user only (not VC user); includes unit + area name.
   - **Verify:** Toast text and recipient.

4. **User 1 (VM)** toggles privacy ON, then OFF themselves.
   - **Expected:** VM user does **not** receive a toast for their own toggles.
   - **Verify:** No self-notification toast.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-07: No duplicate toast when VC toggles privacy (P1)

**Maps to:** AC-5 (regression for known defect)  
**Preconditions:** PRE-01 through PRE-03.

1. **User 1 (VM)** monitoring; **User 2 (VC)** in session.
2. **User 2 (VC)** toggles privacy ON, then OFF, then ON again (with ~2s between toggles).
   - **Expected:** VM user sees **exactly one** toast per VC-initiated change — no duplicate/stacked toasts.
   - **Verify:** Count toast appearances in VM.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-08: VC activity feed — VC-initiated privacy events (P1)

**Maps to:** AC-6  
**Preconditions:** PRE-01 through PRE-03; VC session with activity panel accessible.

1. Note current VC activity feed entries.
2. **User 2 (VC)** toggles privacy **ON**.
   - **Expected:** New activity entry: **"Privacy Mode On"** (or equivalent approved label).
   - **Verify:** VC activity list text.

3. **User 2 (VC)** toggles privacy **OFF**.
   - **Expected:** New activity entry: **"Privacy Mode Off"**.
   - **Verify:** VC activity list.

4. Confirm entries are **not** generic "On"/"Off" labels.
   - **Expected:** Full "Privacy Mode On/Off" wording per product request.
   - **Verify:** Text inspection.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-09: VM/CC activity feed — VC-initiated privacy events (P1)

**Maps to:** AC-7  
**Preconditions:** PRE-01 through PRE-03; VM activity feed accessible.

1. **User 2 (VC)** toggles privacy ON while **User 1 (VM)** monitors.
   - **Expected:** VM/CC activity feed shows privacy mode on event.
   - **Verify:** VM activity list.

2. **User 2 (VC)** toggles privacy OFF.
   - **Expected:** VM/CC activity feed shows privacy mode off event.
   - **Verify:** VM activity list.

3. Confirm no **duplicate** "Privacy Mode Off" entries when VM subsequently disables privacy after VC already turned it off.
   - **Expected:** Single off event per actual state change (regression for Nadire's duplicate-activity finding).
   - **Verify:** Activity list chronology.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-10: Toggle state sync — VM changes reflect in VC (P1)

**Maps to:** AC-8  
**Preconditions:** PRE-01 through PRE-03; normal (non-Incognito) browsers.

1. **User 1 (VM)** and **User 2 (VC)** both connected; privacy OFF.
2. **User 1 (VM)** toggles privacy **ON** (VC does not act).
   - **Expected:** VC privacy toggle updates to **ON** without VC user action.
   - **Expected:** VC video obscured.
   - **Verify:** VC toggle state + video.

3. **User 1 (VM)** toggles privacy **OFF**.
   - **Expected:** VC toggle updates to **OFF**; video unobscured in VC.
   - **Verify:** VC UI sync.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-11: Toggle state sync — VC changes reflect in VM (P1)

**Maps to:** AC-8  
**Preconditions:** PRE-01 through PRE-03.

1. Both users connected; privacy OFF.
2. **User 2 (VC)** toggles privacy ON.
   - **Expected:** VM privacy toggle/icon shows ON; VM video obscured.
   - **Verify:** VM UI.

3. **User 2 (VC)** toggles privacy OFF.
   - **Expected:** VM toggle shows OFF; VM video unobscured.
   - **Verify:** VM UI.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-12: VM-initiated privacy — VC activities behavior (P2)

**Maps to:** Scope clarification  
**Preconditions:** PRE-01 through PRE-03.

1. **User 2 (VC)** in active VC session with activity panel open.
2. **User 1 (VM)** toggles privacy ON, then OFF (VC does not toggle).
   - **Expected (per dev):** VC activity list may **not** show VM-initiated privacy events (task-based scope).
   - **Expected:** VC toggle state and video **do** still sync.
   - **Verify:** VC activities vs. toggle/video state.

Document observed behavior — defect only if product expects VM-initiated events in VC activities.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-13: VM privacy timer not shown in VC (P1)

**Maps to:** AC-10  
**Preconditions:** PRE-01 through PRE-03, PRE-07.

1. **User 1 (VM)** enables privacy mode.
2. **User 2 (VC)** joins concurrent session while privacy is ON.
   - **Expected:** No privacy countdown/timer in VC video overlay or panel.
   - **Verify:** Visual inspection for entire privacy-on duration.

3. **User 2 (VC)** toggles privacy off and on again.
   - **Expected:** Still no timer in VC at any point.
   - **Verify:** Visual check.

4. Confirm VM users **do** see the privacy timer (IDA-4078 regression).
   - **Expected:** Timer visible in VM for activating user and concurrent VM viewers.
   - **Verify:** VM UI.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-14: Multi-sitter — two VM users + one VC session (P1)

**Maps to:** AC-11, ticket testing coverage note  
**Preconditions:** PRE-04; **User 3 (VM)** available.

1. **User 1 (VM)** and **User 3 (VM)** both monitor the same room.
2. **User 2 (VC)** joins concurrent VC session.
3. **User 1 (VM)** enables privacy mode.
   - **Expected:** All three users (User 1, User 3, User 2 VC) see obscured video; toggles synced.
   - **Verify:** All three sessions.

4. **User 2 (VC)** disables privacy mode.
   - **Expected:** Video unobscured for all; VM users receive toast (not VC user); toggles OFF everywhere.
   - **Verify:** Video + toasts + toggle states.

5. **User 3 (VM)** enables privacy; **User 2 (VC)** overrides OFF.
   - **Expected:** VC override wins; both VM sitters see updated state.
   - **Verify:** All sessions.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-15: VC joins after VM already in privacy mode (P2)

**Maps to:** AC-2, AC-8  
**Preconditions:** PRE-01 through PRE-03.

1. **User 1 (VM)** enables privacy mode **before** VC joins.
2. **User 2 (VC)** starts VC session to the same room.
   - **Expected:** VC sees obscured video immediately; VC toggle shows ON.
   - **Verify:** VC initial state.

3. **User 2 (VC)** toggles privacy OFF.
   - **Expected:** VC can disable privacy even though VM enabled it first.
   - **Verify:** Video unobscured; VM notified.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-16: Regression — existing VC session controls unaffected (P1)

**Maps to:** Regression  
**Preconditions:** PRE-01, PRE-02; active VC session.

1. Verify night vision, focus, and PIP controls still work with privacy control present.
   - **Expected:** All pre-existing right-panel controls functional; no layout overlap.
   - **Verify:** Functional smoke on each control.

2. Toggle privacy on/off multiple times while using other controls.
   - **Expected:** No console errors; controls remain responsive.
   - **Verify:** Console + functional check.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-17: Regression — VM privacy mode without VC session (P1)

**Maps to:** Regression, IDA-4078  
**Preconditions:** PRE-07.

1. With **no** active VC session, **User 1 (VM)** enables and disables privacy mode.
   - **Expected:** Standard VM privacy behavior unchanged; timer visible; no errors.
   - **Verify:** VM-only workflow.

2. Second VM user joins same room (no VC).
   - **Expected:** Second VM user sees timer and privacy state (IDA-4078).
   - **Verify:** VM UI for User 3.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

### TC-18: Ticket QA smoke — end-to-end concurrent flow (P1)

**Maps to:** Dev QA handoff  
**Preconditions:** PRE-01 through PRE-05 Tenant A.

Execute as a single smoke pass:

1. VM sitter enables privacy during active VC call → VC sees obscured feed.
2. VC user disables privacy via new control → patient visible in VC.
3. VC toggle syncs to VM; VM toast shows with unit + area (VM user only).
4. VC activity shows "Privacy Mode On/Off" for VC-initiated changes.
5. VM activity shows corresponding events.
6. Simultaneous toggle → VC wins.
7. Multi-sitter room → all users stay in sync.
8. No timer in VC; no duplicate toasts.
9. `showPrivacyToggleInVc = false` → control hidden.

| Result | Tester | Date | Notes |
|--------|--------|------|-------|
| | | | |

---

## Sign-off

### SO-01: Test completion (P1)

**Preconditions:** All P1 test cases executed.

Record the overall result and any defects filed. All acceptance criteria should be met, or defects linked to [IDA-5250](https://careai.atlassian.net/browse/IDA-5250) / [IDA-4078](https://careai.atlassian.net/browse/IDA-4078).

| Field | Value |
|-------|-------|
| **Overall result** | Pass / Fail |
| **Tester** | |
| **Date** | |
| **Build tested** | |
| **IDA-4078 included?** | Yes / No |
| **Tenants used** | Tenant A: / Tenant B: |
| **Room / unit / area tested** | |
| **Browsers used** | (confirm non-Incognito) |
| **Defects filed** | |

---

## Quick reference: priority order

Run P1 cases first in this order for minimum coverage:

1. TC-01 (control visible)
2. TC-03 (VC turns privacy off — core scenario)
3. TC-04 (VC turns privacy on)
4. TC-10, TC-11 (toggle sync both directions)
5. TC-06, TC-07 (toast content, recipient, no duplicates)
6. TC-08, TC-09 (activity feeds)
7. TC-05 (VC override)
8. TC-13 (no VC timer; VM timer regression)
9. TC-14 (multi-sitter)
10. TC-02 (tenant config off)
11. TC-16, TC-17 (regression)
12. TC-18 (end-to-end smoke)

P2 cases (TC-12, TC-15) can follow as time allows.
