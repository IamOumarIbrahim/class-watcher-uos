# UoS Seat Monitor

Monitors the University of Sharjah Banner registration system for open seats
in your required courses. Sends push notifications (ntfy), Windows desktop
toasts, and audible alerts the moment a seat becomes available.

**Never registers, drops, or modifies courses automatically.**

---

## 📥 1-Click Windows Download (Recommended)

Download the standalone installer — no Python installation required!

[![Download Windows Installer](https://img.shields.io/badge/Download-Windows_Installer_(.exe)-2ea44f?style=for-the-badge&logo=windows)](https://github.com/IamOumarIbrahim/class-watcher-uos/releases/download/v1.0.0/UoS-Course-Seat-Monitor-Setup.exe)

👉 **[Download UoS-Course-Seat-Monitor-Setup.exe (v1.0.0)](https://github.com/IamOumarIbrahim/class-watcher-uos/releases/download/v1.0.0/UoS-Course-Seat-Monitor-Setup.exe)**

1. Download and run `UoS-Course-Seat-Monitor-Setup.exe`.
2. Follow the 1-click setup wizard to install to your computer and desktop.
3. Open **UoS Course Seat Monitor** from your Desktop or Start Menu!

---

## 🛠️ Developer / Python Setup

If running from source code:

```powershell
cd uos-seat-monitor
.\install.ps1
```

Or manually:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env — set NTFY_TOPIC to your private topic name
```

## Graphical Interface (Recommended for Students) 🖥️

To launch the easy-to-use graphical monitor:

```powershell
.\run_gui.ps1
# or
.\.venv\Scripts\python.exe gui.py
```

The GUI allows you to:
- Enter up to 10 course CRNs with custom course labels.
- Set up phone push notifications (ntfy) and Gmail alerts.
- Follow the simple setup guide embedded in the top right corner.
- Test alerts with 1-click.
- View live seat availability in a real-time status table.

## Command Line Usage (Terminal)

```powershell
# Continuous monitor (30 s polling)
.\run.ps1
# or
.\.venv\Scripts\python.exe monitor.py

# One live check — prints seat table and exits
.\.venv\Scripts\python.exe monitor.py --once

# Send a test notification across all channels
.\.venv\Scripts\python.exe monitor.py --test-notification
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
