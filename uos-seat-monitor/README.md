# UoS Seat Monitor

Monitors the University of Sharjah Banner registration system for open seats
in your required courses. Sends push notifications (ntfy), Windows desktop
toasts, and audible alerts the moment a seat becomes available.

**Never registers, drops, or modifies courses automatically.**

## Quick Setup

```powershell
cd uos-seat-monitor
.\install.ps1
```

Or manually:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env — set NTFY_TOPIC to your private topic name
```

## Usage

```powershell
# One live check — prints seat table and exits
.\.venv\Scripts\python.exe monitor.py --once

# Send a test notification to verify ntfy / toast / beep
.\.venv\Scripts\python.exe monitor.py --test-notification

# Continuous monitor (30 s polling)
.\.venv\Scripts\python.exe monitor.py
# or
.\run.ps1
```

## Target CRNs

| Label         | CRN   | Notes                            |
|---------------|-------|----------------------------------|
| OS            | 12011 | Required                         |
| COMM          | 12115 | Required                         |
| NETSEC        | 12126 | Required                         |
| MICRO-LEC     | 12091 | Must pair with a lab             |
| MICRO-LAB-PREF| 12093 | Preferred lab                    |
| MICRO-LAB-FALL| 12094 | Fallback lab                     |
| SE-A          | 12014 | Preferred SE section             |
| SE-B          | 12015 | Fallback SE section              |

## Stopping Monitoring for a CRN

After you successfully register a course, edit `config.json`:
1. Add the CRN to `registered_crns`.
2. Remove it from `required`.

## Keep the PC Awake

Windows Task Scheduler (optional for 24/7 monitoring):
- Action: `powershell -File C:\path\to\run.ps1`
- Trigger: At startup / daily
- Settings: Restart on failure, every 1 minute, for 1 day.

Keep your computer plugged in, connected to the internet, and awake until
registration closes.

## Configuration

Edit `config.json` to change poll interval, add/remove CRNs, or adjust jitter.
Edit `.env` for ntfy topic, Gmail settings, etc.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
