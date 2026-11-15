# 11/15/2026: site down (out of memory), then owners locked out

Two problems on the same evening. All times are Central.

## 1. The site went down over and over (5:15 PM to 6:36 PM)

**What people saw:** "Couldn't load your account (502)". The site came back and then went down again every few minutes while the office staffed shifts and confirmed clients.

**Why it broke:**
- The Render server has **512 MB** of memory.
- Two parts of the app loaded the season's **entire schedule save history** at once: 1,540 saves, about 53 MB of trimmed data, which grows several times larger once loaded into memory.
  1. The client page's **2026 Install panel** (`GET /api/clients/{id}/install-summary`, added in #156 the night before) did this whenever a client was confirmed. It only wanted to show who confirmed the client and when.
  2. The **Install Changes** feed (`schedule_changes.load_events`, behind the Changes page and the menu badge). On real data it peaked at **544 MB**.
- The history grows with every save: 158 saves on 11/12 and 74 on 11/14. It crossed the limit that afternoon.
- Each team member opening a client page killed the server. Retrying killed it again.

**What we checked:**
- Render **Events** said "Ran out of memory (used over 512MB)" every 4 to 8 minutes.
- The **Metrics** memory graph sat flat at about 20% and then jumped past the limit, so a single request was blowing up rather than memory leaking slowly.
- In the logs, every `install-summary` request was missing. Those requests never finished.
- The database was healthy and no save was lost. The last schedule save before the outage was 3:56 PM.

**How we fixed it:**
- **#159** (live 6:21 PM): the install panel no longer loads the change history. It still shows "Confirmed", but without who and when for now.
- **#160** (live 6:36 PM): the Changes feed reads the history **100 saves at a time**. Each save is still compared with the one before it, across chunk edges. Only the last save stays in memory, and only one rebuild runs at a time.
  - On real data: **135 MB** peak instead of 544 MB, and the same 902 changes, byte for byte.
  - A new test checks that the feed is identical at any chunk size.
- **Load test after both fixes:** about 780 requests on the live site in under a minute, covering every client page, the Changes page 7 times at once, the schedule, card facts and the dashboard. No errors and no crashes. The first load of the Changes page after a restart takes about a minute; after that it loads in under a second.

**So it doesn't happen again:**
- Never load the whole schedule history, or whole saved states, in one request. Read it in chunks or keep a running summary.
- Before merging an endpoint that touches `install_schedule_history`, `install_schedule_state` or the published page, **measure peak memory on real data**: a local script against the database, printing `resource.getrusage(...).ru_maxrss`. Keep it well under 512 MB, since the app itself uses about 100 MB.
- After a deploy, lightly load-test the new endpoints and watch Render **Events** for "Ran out of memory".
- The history keeps growing every season. If the Changes page gets slow again, store computed events instead of rebuilding them, or move the server to a larger Render plan.
- Follow-up: bring back "confirmed by and when" on the client panel from a cheap source, such as a small table written when a stop is confirmed, not from the full history.

## 2. Two owners were locked out as "crew" (6:40 PM)

**What people saw:** My Shifts said "You don't have access to this (role: crew, route: GET /api/lead/shifts)".

**Why it broke:** a login's role is decided in `backend/app/libs/roles.py`, and the first match wins:
1. The hard-coded super admin.
2. A saved role in **Settings → Users** (`ll_app.user_roles`).
3. **The installer roster:** a Lead gets `lead`, and **anyone else on the roster gets `crew`**.
4. Everyone else gets `staff`.

Cynthia and Chris had no saved role, so they had been getting `staff` by default. As soon as they were added to the roster as General Installers for this season, step 3 dropped them to crew.

**How we fixed it:** both now have **super_admin** saved in Settings → Users (6:45 PM and 6:47 PM). A saved role always beats the roster, so roster changes can't affect them again. Their roster entries were left as they are, on purpose.

**So it doesn't happen again:**
- **Everyone who uses the office side needs a saved role in Settings → Users.** Never rely on the "no row means staff" default.
- Before adding an office person to the installer roster, check that they have a saved role.
- Possible code guard, not built yet because changing who can see what needs the owner's approval: refuse to demote a login that has recently used office pages, or show a warning in the roster when the email being added belongs to someone with no saved role.
