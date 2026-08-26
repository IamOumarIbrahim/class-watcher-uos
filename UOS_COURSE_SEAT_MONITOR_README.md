# UoS Course Seat Monitor - Implementation Handoff

## Purpose

Build and run a reliable course-seat monitor for the University of Sharjah Fall 2026/2027 registration system. The monitor must notify the student immediately when any required course gains a real registration seat.

This file is the authoritative task description. Do not reuse CRNs from earlier conversations, screenshots, or drafts when they conflict with this file.

The monitor is a notification tool only. It must **never register, add, drop, waitlist, or submit courses automatically**.

## Student's Current Registration

These courses are already registered and must not be monitored as missing:

| Course | CRN | Subject/course code | State |
|---|---:|---:|---|
| DATA | `11991` | `1501 263` | Registered |
| TELE | `12780` | `0402 347` | Registered |
| SDP | `12129` | `1502 491` | Registered |

Important corrections:

- DATA is CRN `11991`, not `11990`.
- TELE is CRN `12780`, not `12781`.
- CTRL must not be monitored or registered.

## Courses Still Required

| Requirement | CRN | Subject/course code | Rule |
|---|---:|---:|---|
| MICRO lecture | `12091` | `1502 232` | Required |
| MICRO lab - preferred | `12093` | `1502 232` | Preferred lab alternative |
| MICRO lab - fallback | `12094` | `1502 232` | Acceptable alternative; late session |
| OS | `12011` | `1501 352` | Required |
| COMM | `12115` | `1502 346` | Required |
| NETSEC | `12126` | `1502 444` | Required |
| SE - section A | `12014` | `1501 366` | Required |
| SE - section B | `12015` | `1501 366` | Required |

The MICRO requirement is a linked bundle:

```text
MICRO is satisfied only by:

12091 AND (12093 OR 12094)
```

Preference order:

1. `12091 + 12093`
2. `12091 + 12094` only if the preferred lab cannot be obtained

Do not treat either lab by itself as completing MICRO. Still notify when only one bundle component opens, because the student may need to react quickly, but label the alert as **PARTIAL MICRO AVAILABILITY**.

## Definition of Success

The desired final registration is:

```text
Already registered:
11991, 12780, 12129

Still required:
12011, 12115, 12126, 12091, one of {12093, 12094}, and one of {12014, 12015}
```

The monitor succeeds operationally when it:

1. Detects a genuine available seat for any target CRN.
2. Sends an urgent notification without requiring the student to watch a terminal.
3. Distinguishes actual registration seats from waitlist positions.
4. Gives special priority to a simultaneously available MICRO lecture/lab pair.
5. Survives transient network failures and detects stale or invalid responses.

## Verified Registration-System Facts

- Public base URL: `https://reg-prod.ec.sharjah.ac.ae/StudentRegistrationSsb`
- Public registration landing page: `/ssb/registration/registration`
- Public Browse Classes term page: `/ssb/term/termSelection?mode=search`
- Authenticated manual registration page: `/ssb/classRegistration/classRegistration`
- Term name: `Fall 2026/2027`
- Term code: `202610`
- Standard Banner results endpoint: `/ssb/searchResults/searchResults`
- Seat results expose a numeric `seatsAvailable` value in the Banner result data.
- The public Browse Classes flow does not require the student's Microsoft/UoS login.

The implementation must use the public Browse Classes data path. It must not store or request the student's UoS password, Microsoft password, MFA code, SSO cookie, or authenticated registration session.

## Required Implementation Strategy

### Primary method: public Banner data request

Use Python 3.11+ and a persistent `requests.Session` or `httpx.Client`.

1. Open the public term-selection page to establish cookies.
2. Select/initialize term `202610` using the public Banner term-search flow.
3. Request the public search-results endpoint.
4. Query only the relevant subjects or courses; do not download all university classes every cycle.
5. Filter the response by exact CRN.

Relevant subjects:

```text
1501
1502
```

Relevant course numbers:

```text
232
352
346
444
366
```

The standard Banner query normally uses parameters resembling:

```text
txt_term=202610
txt_subject=1501
txt_subject=1502
pageOffset=0
pageMaxSize=500
sortColumn=courseReferenceNumber
sortDirection=asc
```

Banner deployments can vary. Do not blindly assume every parameter name. Validate the live public request and response before beginning continuous polling. If the server requires a generated `uniqueSessionId`, obtain it from the public search session rather than inventing or hardcoding it.

### Public-browser fallback

If the direct JSON workflow cannot be made reliable, use Playwright against **Public Browse Classes only**:

1. Open the public term page.
2. choose `Fall 2026/2027`.
3. Search the exact subject/course combinations.
4. Read each exact CRN row and its status.

Use a persistent public browser context only to preserve the public term/search state. Do not fall back to automating the authenticated registration page.

## Availability Rules

Treat a target as open only when all of the following are true:

- The exact CRN is present exactly once.
- The response belongs to term `202610` / Fall 2026/2027.
- The section is not cancelled or otherwise unavailable.
- `seatsAvailable` parses as an integer greater than zero.

Never infer availability from any of the following:

- `waitAvailable`
- waitlist capacity
- wording such as `40 of 40 waitlist seats remain`
- `openSection` without also confirming a positive numeric seat count
- a missing CRN
- an empty, expired, HTML-login, or malformed response

A missing CRN is a monitor error, not zero seats.

## Polling Policy

- Default interval: 30 seconds.
- Add random jitter of approximately plus/minus 5 seconds.
- Prefer one batched public request per cycle.
- Never run parallel request floods.
- On HTTP `429`, `5xx`, timeout, invalid JSON, or session expiry, back off progressively: 60, 120, then 300 seconds.
- Reinitialize the public term session after expiry.
- Return to the normal interval after a successful validated response.
- Log every poll timestamp and the extracted seat counts.

Do not poll more frequently than once every 20 seconds. The goal is fast detection without placing unreasonable load on the university system.

## State and Transition Logic

Persist the last validated status for every target CRN in a local generated file such as `state.json`.

Required behavior:

- At first startup, immediately alert for any target that is already open.
- When a target changes from `0` to `1+`, alert immediately.
- If an open target returns to `0`, record the closure without an urgent notification.
- If the same target later changes from `0` to `1+` again, alert again.
- Do not spam continuously while the count remains unchanged.
- One reminder after 60 seconds is acceptable if the seat remains open.
- Apply a short per-CRN cooldown while preserving reopening alerts.

The console should always show a compact live status table.

## MICRO Bundle Logic

Evaluate these conditions after every successful poll:

```python
lecture_open = seats["12091"] > 0
preferred_lab_open = seats["12093"] > 0
fallback_lab_open = seats["12094"] > 0

preferred_bundle_open = lecture_open and preferred_lab_open
fallback_bundle_open = lecture_open and fallback_lab_open
```

Alert priorities:

1. **CRITICAL - PREFERRED MICRO BUNDLE OPEN:** `12091 + 12093`
2. **CRITICAL - FALLBACK MICRO BUNDLE OPEN:** `12091 + 12094`
3. **HIGH - PARTIAL MICRO AVAILABILITY:** only the lecture or one lab is open

If both labs are open, recommend CRN `12093` first.

## Notification Requirements

Primary recommendation: an urgent `ntfy` push notification to the student's phone.

Also provide:

- A Windows desktop notification.
- An audible local alarm.
- Optional Gmail backup if the user configures it.

Never commit notification credentials or topic names. Read them from environment variables or a local `.env` file excluded by `.gitignore`.

Recommended environment variables:

```text
NTFY_SERVER=https://ntfy.sh
NTFY_TOPIC=<long-random-private-topic>
GMAIL_ENABLED=false
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
ALERT_RECIPIENT=
```

Gmail is optional and secondary. The monitor must work with ntfy and local notifications even when Gmail is disabled.

Example urgent message:

```text
UOS SEAT OPEN
COMM - CRN 12115
Seats available: 1
Open registration immediately.
```

Example bundle message:

```text
UOS MICRO BUNDLE OPEN
Lecture: 12091
Preferred lab: 12093
Both currently have seats. Register both together immediately.
```

Include the normal authenticated registration URL in the notification, but do not include cookies, tokens, or session parameters.

## Suggested Project Layout

```text
uos-seat-monitor/
|-- README.md
|-- monitor.py
|-- banner_client.py
|-- notifications.py
|-- config.json
|-- config.example.json
|-- requirements.txt
|-- install.ps1
|-- run.ps1
|-- .env.example
|-- .gitignore
`-- tests/
    |-- test_parser.py
    |-- test_transitions.py
    `-- fixtures/
```

Generated runtime files such as `.env`, `state.json`, and `monitor.log` must be ignored by Git.

## Authoritative Configuration

Use a machine-readable configuration equivalent to:

```json
{
  "term": {
    "code": "202610",
    "name": "Fall 2026/2027"
  },
  "registered_crns": ["11991", "12780", "12129"],
  "ignored_crns": ["11990", "12769", "12781"],
  "required": {
    "individual": {
      "OS": "12011",
      "COMM": "12115",
      "NETSEC": "12126"
    },
    "micro": {
      "lecture": "12091",
      "labs_in_preference_order": ["12093", "12094"],
      "required_lab_count": 1
    },
    "se": {
      "sections_in_preference_order": ["12014", "12015"],
      "required_section_count": 1,
      "course_code": "1501366",
      "note": "Register exactly one SE section; 12014 preferred, 12015 fallback"
    }
  },
  "poll_seconds": 30,
  "poll_jitter_seconds": 5
}
```

The ignored CRNs exist to prevent accidental reuse of superseded or explicitly excluded identifiers. Do not monitor them unless the user later edits this configuration.

## Logging and Health Checks

Every log entry should include:

- UAE timestamp using timezone `Asia/Dubai`
- request result
- term validated
- CRNs found
- numeric seat count for every target
- notification result
- retry/backoff state

The monitor must visibly report:

- `MONITOR STARTED`
- `PUBLIC TERM SESSION READY`
- `ALL TARGET CRNS VALIDATED`
- the current seat table
- `MONITOR DEGRADED` after repeated errors
- `MONITOR RECOVERED` after a successful validated poll

Send a startup test notification only when explicitly requested with a flag such as `--test-notification`.

## Windows Operation

The user runs Windows. Supply simple commands such as:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe monitor.py --once
.\.venv\Scripts\python.exe monitor.py --test-notification
.\.venv\Scripts\python.exe monitor.py
```

`--once` must perform one live validated check, print the exact target table, and exit without continuous polling.

The continuous monitor should be runnable from PowerShell and optionally installable in Windows Task Scheduler with restart-on-failure. Do not silently change system settings. Tell the user to keep the computer connected to power, connected to the internet, and awake until registration closes.

## Required Tests

The implementation is not complete until all of these pass:

1. Parse a full section with `0` actual seats and available waitlist positions as **closed**.
2. Parse `1+` actual seats as **open**.
3. Reject a response from the wrong term.
4. Reject an HTML login/error page presented where JSON is expected.
5. Reject a response missing a target CRN; do not convert it to zero.
6. Trigger an alert on first startup when a seat is already open.
7. Trigger an alert on `0 -> 1+`.
8. Avoid duplicate alerts while availability is unchanged.
9. Alert again after `1+ -> 0 -> 1+`.
10. Mark `12091 + 12093` as the preferred complete MICRO bundle.
11. Mark `12091 + 12094` as the acceptable fallback bundle.
12. Mark a lone lecture or lone lab as partial MICRO availability.
13. Successfully send a test ntfy notification.
14. Complete a live `--once` check and reconcile every displayed target against the public Browse Classes page.

## Non-Goals and Prohibited Behavior

Do not:

- Automatically register or submit any course.
- Add or drop courses.
- Join a waitlist automatically.
- Use the authenticated student registration page for monitoring.
- Request or store UoS/Microsoft credentials or MFA codes.
- Bypass CAPTCHA, rate limits, access controls, or bot protections.
- Interpret waitlist positions as real registration seats.
- Alert on partial/malformed data as if it were an opening.
- Monitor CTRL.
- Replace the authoritative CRNs with similar sections without explicit user approval.

## Expected Handoff From the Implementing LLM

The implementing LLM should finish by providing:

1. All project files.
2. A short explanation of the public data path used.
3. Evidence that every required test passed.
4. The output of a successful live `--once` check.
5. Exact Windows installation and launch commands.
6. Confirmation that no UoS credentials are stored.
7. Clear instructions for the student to stop monitoring a CRN after successfully registering it.

Do not claim the monitor is ready merely because the code runs. It is ready only after the live response schema, exact target CRNs, notification delivery, transition behavior, MICRO bundle logic, and failure handling have all been validated.
