"""
gui.py - Simple Legacy Tkinter GUI for UoS Course Seat Monitor.

Allows any student to easily:
1. Enter up to 10 course CRNs with custom labels.
2. Configure ntfy phone push notifications and Gmail alerts.
3. Read an embedded setup guide in the top right corner.
4. Test notifications, check seats instantly, and run continuous 24/7 background monitoring.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Ensure local imports work
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from banner_client import BannerClient
from monitor import (
    COOLDOWN_SECONDS,
    CONFIG_PATH,
    STATE_PATH,
    TZ,
    evaluate_and_alert,
    load_config,
    load_state,
    save_state,
)
from notifications import send_alert, send_test_notification

# ---------------------------------------------------------------------------
# Logging Handler to stream to Tkinter Text Widget
# ---------------------------------------------------------------------------

class QueueHandler(logging.Handler):
    """Sends log records to a thread-safe Queue for the GUI to display."""
    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.log_queue.put(msg)


# ---------------------------------------------------------------------------
# Main GUI Application
# ---------------------------------------------------------------------------

class UosMonitorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("UoS Course Seat Monitor — Student Edition")
        self.root.geometry("1060x820")
        self.root.minsize(960, 720)

        # Background thread control
        self.is_monitoring = False
        self.stop_event = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        # Load environment and config
        load_dotenv(BASE_DIR / ".env", override=True)
        self.config_data = self._load_initial_config()

        # Set up logging
        self._setup_logging()

        # Build UI
        self._build_ui()

        # Populate fields with loaded configuration
        self._populate_fields()

        # Start log consumer loop
        self.root.after(100, self._process_log_queue)

        # Handle window close cleanly
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -----------------------------------------------------------------------
    # Config & State Helpers
    # -----------------------------------------------------------------------

    def _load_initial_config(self) -> dict:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "term": {"code": "202610", "name": "Fall 2026/2027"},
            "registered_crns": [],
            "ignored_crns": [],
            "required": {"individual": {}},
            "watch_only": {},
            "poll_seconds": 30,
            "poll_jitter_seconds": 5,
        }

    def _setup_logging(self) -> None:
        self.logger = logging.getLogger("UosMonitorGUI")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(formatter)
        logging.getLogger().addHandler(self.queue_handler)

    # -----------------------------------------------------------------------
    # UI Building
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Style configuration
        style = ttk.Style()
        style.theme_use("clam")
        
        # Colors
        self.bg_color = "#f4f6f9"
        self.card_bg = "#ffffff"
        self.accent_color = "#0d6efd"
        self.green_color = "#198754"
        self.red_color = "#dc3545"

        self.root.configure(bg=self.bg_color)

        # Top Header Frame
        header_frame = tk.Frame(self.root, bg="#1a2530", padx=16, pady=12)
        header_frame.pack(fill=tk.X)

        title_lbl = tk.Label(
            header_frame,
            text="🎓 University of Sharjah — Course Seat Monitor",
            font=("Segoe UI", 16, "bold"),
            fg="#ffffff",
            bg="#1a2530",
        )
        title_lbl.pack(side=tk.LEFT)

        self.status_badge = tk.Label(
            header_frame,
            text="● IDLE",
            font=("Segoe UI", 11, "bold"),
            fg="#adb5bd",
            bg="#2c3b4d",
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT)

        term_lbl = tk.Label(
            header_frame,
            text="Term: Fall 2026/2027 (202610)",
            font=("Segoe UI", 10),
            fg="#ced4da",
            bg="#1a2530",
            padx=12,
        )
        term_lbl.pack(side=tk.RIGHT)

        # Main Paned / Grid Area
        main_content = tk.Frame(self.root, bg=self.bg_color, padx=12, pady=10)
        main_content.pack(fill=tk.BOTH, expand=True)

        # Left Column: Inputs (CRNs + Notifications)
        left_col = tk.Frame(main_content, bg=self.bg_color)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        # Right Column: Guide & Action Buttons
        right_col = tk.Frame(main_content, bg=self.bg_color, width=380)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(8, 0))

        # -----------------------------
        # Left: 10 CRN Entry Boxes
        # -----------------------------
        crn_group = tk.LabelFrame(
            left_col,
            text=" 🎯 Target Courses to Monitor (Up to 10 CRNs) ",
            font=("Segoe UI", 11, "bold"),
            bg=self.card_bg,
            fg="#212529",
            padx=10,
            pady=8,
        )
        crn_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Header for CRN table inputs
        headers_frame = tk.Frame(crn_group, bg=self.card_bg)
        headers_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(headers_frame, text="#", width=3, font=("Segoe UI", 9, "bold"), bg=self.card_bg).pack(side=tk.LEFT, padx=2)
        tk.Label(headers_frame, text="5-Digit CRN", width=14, font=("Segoe UI", 9, "bold"), bg=self.card_bg, anchor="w").pack(side=tk.LEFT, padx=4)
        tk.Label(headers_frame, text="Course Name / Label (e.g. OS, MICRO-LEC)", width=32, font=("Segoe UI", 9, "bold"), bg=self.card_bg, anchor="w").pack(side=tk.LEFT, padx=4)

        # 10 Input Rows
        self.crn_entries: list[tuple[tk.Entry, tk.Entry]] = []
        for i in range(1, 11):
            row_frame = tk.Frame(crn_group, bg=self.card_bg)
            row_frame.pack(fill=tk.X, pady=2)

            num_lbl = tk.Label(row_frame, text=f"{i}.", width=3, font=("Segoe UI", 9), bg=self.card_bg, fg="#6c757d")
            num_lbl.pack(side=tk.LEFT, padx=2)

            crn_ent = tk.Entry(row_frame, width=14, font=("Segoe UI", 10))
            crn_ent.pack(side=tk.LEFT, padx=4)

            lbl_ent = tk.Entry(row_frame, width=32, font=("Segoe UI", 10))
            lbl_ent.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

            self.crn_entries.append((crn_ent, lbl_ent))

        # -----------------------------
        # Left: Notification Settings
        # -----------------------------
        notif_group = tk.LabelFrame(
            left_col,
            text=" 🔔 Notification Settings ",
            font=("Segoe UI", 11, "bold"),
            bg=self.card_bg,
            fg="#212529",
            padx=10,
            pady=8,
        )
        notif_group.pack(fill=tk.X, pady=(0, 0))

        # ntfy Push frame
        ntfy_frame = tk.Frame(notif_group, bg=self.card_bg)
        ntfy_frame.pack(fill=tk.X, pady=3)

        tk.Label(ntfy_frame, text="ntfy Server:", width=14, anchor="w", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=0, sticky="w", pady=2)
        self.ntfy_server_ent = tk.Entry(ntfy_frame, width=28, font=("Segoe UI", 9))
        self.ntfy_server_ent.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        self.ntfy_server_ent.insert(0, "https://ntfy.sh")

        tk.Label(ntfy_frame, text="ntfy Topic Name:", width=14, anchor="w", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=1, column=0, sticky="w", pady=2)
        self.ntfy_topic_ent = tk.Entry(ntfy_frame, width=28, font=("Segoe UI", 9))
        self.ntfy_topic_ent.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        # Gmail Frame
        gmail_frame = tk.Frame(notif_group, bg=self.card_bg)
        gmail_frame.pack(fill=tk.X, pady=(6, 2))

        self.gmail_enabled_var = tk.BooleanVar(value=False)
        gmail_chk = tk.Checkbutton(
            gmail_frame,
            text="Enable Gmail Alerts (Optional)",
            variable=self.gmail_enabled_var,
            font=("Segoe UI", 9, "bold"),
            bg=self.card_bg,
            activebackground=self.card_bg,
        )
        gmail_chk.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        tk.Label(gmail_frame, text="Gmail Address:", width=14, anchor="w", font=("Segoe UI", 9), bg=self.card_bg).grid(row=1, column=0, sticky="w", pady=2)
        self.gmail_addr_ent = tk.Entry(gmail_frame, width=28, font=("Segoe UI", 9))
        self.gmail_addr_ent.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        tk.Label(gmail_frame, text="App Password:", width=14, anchor="w", font=("Segoe UI", 9), bg=self.card_bg).grid(row=2, column=0, sticky="w", pady=2)
        self.gmail_pass_ent = tk.Entry(gmail_frame, width=28, font=("Segoe UI", 9), show="•")
        self.gmail_pass_ent.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        self.show_pass_var = tk.BooleanVar(value=False)
        show_pass_chk = tk.Checkbutton(
            gmail_frame,
            text="Show",
            variable=self.show_pass_var,
            command=self._toggle_password_visibility,
            font=("Segoe UI", 8),
            bg=self.card_bg,
            activebackground=self.card_bg,
        )
        show_pass_chk.grid(row=2, column=2, sticky="w", padx=2)

        tk.Label(gmail_frame, text="Alert Recipient:", width=14, anchor="w", font=("Segoe UI", 9), bg=self.card_bg).grid(row=3, column=0, sticky="w", pady=2)
        self.gmail_recip_ent = tk.Entry(gmail_frame, width=28, font=("Segoe UI", 9))
        self.gmail_recip_ent.grid(row=3, column=1, sticky="w", padx=4, pady=2)

        # -----------------------------
        # Right: User Guide Box (Top Right Corner)
        # -----------------------------
        guide_group = tk.LabelFrame(
            right_col,
            text=" 📖 Quick User Guide ",
            font=("Segoe UI", 11, "bold"),
            bg="#fdfefe",
            fg="#0c5460",
            padx=10,
            pady=8,
        )
        guide_group.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        guide_text = (
            "🚀 HOW TO USE THIS MONITOR:\n\n"
            "1. Enter Course CRNs:\n"
            "   • Fill in the 5-digit CRNs on the left.\n"
            "   • Add a clear label (e.g., OS, MICRO).\n\n"
            "2. Setup Phone Push (Recommended):\n"
            "   • Install the free 'ntfy' app on iPhone / Android.\n"
            "   • Subscribe to a unique topic name (e.g. uos-myname-77).\n"
            "   • Type that same topic name in 'ntfy Topic Name'.\n\n"
            "3. Setup Gmail Alerts (Optional):\n"
            "   • Check 'Enable Gmail Alerts'.\n"
            "   • Generate a 16-char App Password at:\n"
            "     myaccount.google.com/apppasswords\n\n"
            "4. Verify & Start:\n"
            "   • Click '🔔 Test Notifications' to verify your phone/email ring.\n"
            "   • Click '▶ Start Monitoring'.\n\n"
            "⚠️ IMPORTANT OPERATIONAL RULES:\n"
            "• Keep computer plugged in, awake, and connected to WiFi.\n"
            "• Polls every 30 seconds (safe university rate).\n"
            "• Alerts fire IMMEDIATELY when seatsAvailable > 0.\n"
            "• This tool is a notifier only — it never adds/drops courses."
        )

        guide_box = tk.Text(
            guide_group,
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            bg="#f8f9fa",
            fg="#212529",
            padx=8,
            pady=8,
            relief=tk.FLAT,
            height=14,
        )
        guide_box.insert(tk.END, guide_text)
        guide_box.configure(state=tk.DISABLED)
        guide_box.pack(fill=tk.BOTH, expand=True)

        # -----------------------------
        # Right: Action Buttons Panel
        # -----------------------------
        actions_group = tk.LabelFrame(
            right_col,
            text=" ⚙️ Controls ",
            font=("Segoe UI", 11, "bold"),
            bg=self.card_bg,
            fg="#212529",
            padx=10,
            pady=8,
        )
        actions_group.pack(fill=tk.X, pady=(0, 0))

        btn_grid = tk.Frame(actions_group, bg=self.card_bg)
        btn_grid.pack(fill=tk.X, pady=2)

        self.start_btn = tk.Button(
            btn_grid,
            text="▶ Start Monitoring",
            font=("Segoe UI", 10, "bold"),
            bg="#198754",
            fg="#ffffff",
            activebackground="#157347",
            activeforeground="#ffffff",
            padx=12,
            pady=6,
            relief=tk.GROOVE,
            command=self._start_monitoring,
        )
        self.start_btn.pack(fill=tk.X, pady=3)

        self.stop_btn = tk.Button(
            btn_grid,
            text="⏹ Stop Monitoring",
            font=("Segoe UI", 10, "bold"),
            bg="#dc3545",
            fg="#ffffff",
            activebackground="#bb2d3b",
            activeforeground="#ffffff",
            padx=12,
            pady=6,
            relief=tk.GROOVE,
            state=tk.DISABLED,
            command=self._stop_monitoring,
        )
        self.stop_btn.pack(fill=tk.X, pady=3)

        btn_row2 = tk.Frame(btn_grid, bg=self.card_bg)
        btn_row2.pack(fill=tk.X, pady=3)

        self.test_btn = tk.Button(
            btn_row2,
            text="🔔 Test Alerts",
            font=("Segoe UI", 9, "bold"),
            bg="#0d6efd",
            fg="#ffffff",
            padx=8,
            pady=4,
            command=self._test_notifications,
        )
        self.test_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.check_once_btn = tk.Button(
            btn_row2,
            text="🔍 Check Once",
            font=("Segoe UI", 9, "bold"),
            bg="#6c757d",
            fg="#ffffff",
            padx=8,
            pady=4,
            command=self._check_once,
        )
        self.check_once_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        self.save_btn = tk.Button(
            btn_grid,
            text="💾 Save Settings",
            font=("Segoe UI", 9),
            bg="#f8f9fa",
            fg="#212529",
            pady=3,
            command=self._save_settings_clicked,
        )
        self.save_btn.pack(fill=tk.X, pady=(4, 0))

        # -----------------------------
        # Bottom Area: Live Status Table & Logs
        # -----------------------------
        bottom_frame = tk.Frame(self.root, bg=self.bg_color, padx=12, pady=6)
        bottom_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Notebook (Tabs) for Live Table and Console Logs
        notebook = ttk.Notebook(bottom_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Live Seat Status Table
        table_tab = tk.Frame(notebook, bg="#ffffff")
        notebook.add(table_tab, text=" 📊 Live Seat Table ")

        columns = ("crn", "label", "seats", "status", "last_check")
        self.tree = ttk.Treeview(table_tab, columns=columns, show="headings", height=6)
        self.tree.heading("crn", text="CRN")
        self.tree.heading("label", text="Course / Label")
        self.tree.heading("seats", text="Seats Available")
        self.tree.heading("status", text="Status")
        self.tree.heading("last_check", text="Last Checked (UAE Time)")

        self.tree.column("crn", width=90, anchor="center")
        self.tree.column("label", width=220, anchor="w")
        self.tree.column("seats", width=120, anchor="center")
        self.tree.column("status", width=160, anchor="center")
        self.tree.column("last_check", width=180, anchor="center")

        self.tree.tag_configure("open", background="#d1e7dd", foreground="#0f5132", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("closed", background="#ffffff", foreground="#495057")
        self.tree.tag_configure("unknown", background="#fff3cd", foreground="#664d03")

        tree_scroll = ttk.Scrollbar(table_tab, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 2: Activity Logs
        logs_tab = tk.Frame(notebook, bg="#ffffff")
        notebook.add(logs_tab, text=" 📜 Activity Logs ")

        self.log_text = tk.Text(
            logs_tab,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            padx=8,
            pady=6,
        )
        log_scroll = ttk.Scrollbar(logs_tab, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # -----------------------------------------------------------------------
    # Populate & Save Settings
    # -----------------------------------------------------------------------

    def _toggle_password_visibility(self) -> None:
        if self.show_pass_var.get():
            self.gmail_pass_ent.configure(show="")
        else:
            self.gmail_pass_ent.configure(show="•")

    def _populate_fields(self) -> None:
        # 1. Populate CRNs from config
        req = self.config_data.get("required", {})
        watch_only = self.config_data.get("watch_only", {})

        entries_to_fill: list[tuple[str, str]] = []
        if "individual" in req:
            for lbl, crn in req["individual"].items():
                entries_to_fill.append((crn, lbl))
        if "micro" in req:
            micro = req["micro"]
            entries_to_fill.append((micro.get("lecture", ""), "MICRO-LEC"))
            for idx, lab_crn in enumerate(micro.get("labs_in_preference_order", [])):
                pref = "MICRO-LAB-PREF" if idx == 0 else "MICRO-LAB-FALL"
                entries_to_fill.append((lab_crn, pref))
        for lbl, crn in watch_only.items():
            entries_to_fill.append((crn, lbl))

        for i, (crn, lbl) in enumerate(entries_to_fill[:10]):
            self.crn_entries[i][0].delete(0, tk.END)
            self.crn_entries[i][0].insert(0, str(crn).strip())
            self.crn_entries[i][1].delete(0, tk.END)
            self.crn_entries[i][1].insert(0, str(lbl).strip())

        # 2. Populate Notifications from .env
        ntfy_server = os.getenv("NTFY_SERVER", "https://ntfy.sh").strip()
        ntfy_topic = os.getenv("NTFY_TOPIC", "").strip()
        self.ntfy_server_ent.delete(0, tk.END)
        self.ntfy_server_ent.insert(0, ntfy_server)
        self.ntfy_topic_ent.delete(0, tk.END)
        self.ntfy_topic_ent.insert(0, ntfy_topic)

        gmail_enabled = os.getenv("GMAIL_ENABLED", "false").strip().lower() == "true"
        gmail_addr = os.getenv("GMAIL_ADDRESS", "").strip()
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        alert_recip = os.getenv("ALERT_RECIPIENT", gmail_addr).strip()

        self.gmail_enabled_var.set(gmail_enabled)
        self.gmail_addr_ent.delete(0, tk.END)
        self.gmail_addr_ent.insert(0, gmail_addr)
        self.gmail_pass_ent.delete(0, tk.END)
        self.gmail_pass_ent.insert(0, gmail_pass)
        self.gmail_recip_ent.delete(0, tk.END)
        self.gmail_recip_ent.insert(0, alert_recip)

    def _collect_settings(self) -> tuple[dict, dict]:
        """Collects current GUI inputs into config and env dicts."""
        # 1. Target CRNs
        individual = {}
        watch_only = {}
        for idx, (crn_ent, lbl_ent) in enumerate(self.crn_entries):
            crn = crn_ent.get().strip()
            lbl = lbl_ent.get().strip() or f"COURSE-{idx+1}"
            if crn:
                # Group into watch_only or individual
                watch_only[lbl] = crn

        cfg = {
            "term": self.config_data.get("term", {"code": "202610", "name": "Fall 2026/2027"}),
            "registered_crns": self.config_data.get("registered_crns", []),
            "ignored_crns": self.config_data.get("ignored_crns", []),
            "required": self.config_data.get("required", {"individual": {}}),
            "watch_only": watch_only,
            "poll_seconds": 30,
            "poll_jitter_seconds": 5,
        }

        # 2. Env dictionary
        env_vars = {
            "NTFY_SERVER": self.ntfy_server_ent.get().strip() or "https://ntfy.sh",
            "NTFY_TOPIC": self.ntfy_topic_ent.get().strip(),
            "GMAIL_ENABLED": "true" if self.gmail_enabled_var.get() else "false",
            "GMAIL_ADDRESS": self.gmail_addr_ent.get().strip(),
            "GMAIL_APP_PASSWORD": self.gmail_pass_ent.get().strip(),
            "ALERT_RECIPIENT": self.gmail_recip_ent.get().strip() or self.gmail_addr_ent.get().strip(),
        }

        return cfg, env_vars

    def _save_settings(self) -> None:
        cfg, env_vars = self._collect_settings()
        self.config_data = cfg

        # Save config.json
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        # Save .env
        env_lines = [
            "# UoS Course Seat Monitor - Environment Settings",
            f"NTFY_SERVER={env_vars['NTFY_SERVER']}",
            f"NTFY_TOPIC={env_vars['NTFY_TOPIC']}",
            f"GMAIL_ENABLED={env_vars['GMAIL_ENABLED']}",
            f"GMAIL_ADDRESS={env_vars['GMAIL_ADDRESS']}",
            f"GMAIL_APP_PASSWORD={env_vars['GMAIL_APP_PASSWORD']}",
            f"ALERT_RECIPIENT={env_vars['ALERT_RECIPIENT']}",
        ]
        with open(BASE_DIR / ".env", "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(env_lines) + "\n")

        # Reload environment
        for k, v in env_vars.items():
            os.environ[k] = v

    def _save_settings_clicked(self) -> None:
        try:
            self._save_settings()
            messagebox.showinfo("Saved", "Settings successfully saved to config.json and .env!")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save settings: {exc}")

    # -----------------------------------------------------------------------
    # Actions & Threading
    # -----------------------------------------------------------------------

    def _test_notifications(self) -> None:
        self._save_settings()
        self.test_btn.configure(state=tk.DISABLED)

        def worker():
            try:
                self.logger.info("Sending test notifications across all configured channels...")
                send_test_notification()
                self.logger.info("Test notification completed successfully!")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Test Sent",
                    "Test notification sent!\n\nCheck your phone (ntfy), Windows notifications, and Gmail inbox."
                ))
            except Exception as exc:
                self.logger.error(f"Test notification failed: {exc}")
                self.root.after(0, lambda: messagebox.showerror("Test Failed", f"Notification error: {exc}"))
            finally:
                self.root.after(0, lambda: self.test_btn.configure(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _check_once(self) -> None:
        self._save_settings()
        self.check_once_btn.configure(state=tk.DISABLED)

        def worker():
            try:
                self.logger.info("Performing one-time live seat query...")
                cfg = load_config()
                client = BannerClient()
                term_code = cfg["term"]["code"]
                client.initialize(term_code)

                from monitor import all_target_crns, build_label_map
                targets = set(all_target_crns(cfg))
                build_label_map(cfg)

                if not targets:
                    self.logger.warning("No CRNs entered to check.")
                    return

                seats = client.fetch_seats(term_code, targets)
                self.root.after(0, lambda: self._update_table(seats, cfg))
                self.logger.info("Live query complete.")
            except Exception as exc:
                self.logger.error(f"Check once failed: {exc}")
            finally:
                self.root.after(0, lambda: self.check_once_btn.configure(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _start_monitoring(self) -> None:
        if self.is_monitoring:
            return

        cfg, _ = self._collect_settings()
        from monitor import all_target_crns
        targets = all_target_crns(cfg)
        if not targets:
            messagebox.showwarning("No CRNs", "Please enter at least one 5-digit CRN before starting monitoring.")
            return

        self._save_settings()
        self.is_monitoring = True
        self.stop_event.clear()

        # Update UI state
        self.status_badge.configure(text="● MONITORING ACTIVE", fg="#ffffff", bg="#198754")
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        # Launch background monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Background monitoring started.")

    def _stop_monitoring(self) -> None:
        if not self.is_monitoring:
            return

        self.logger.info("Stopping monitoring...")
        self.stop_event.set()
        self.is_monitoring = False

        self.status_badge.configure(text="● IDLE", fg="#adb5bd", bg="#2c3b4d")
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def _monitor_loop(self) -> None:
        """Main continuous polling loop in background thread."""
        cfg = load_config()
        term_code = cfg["term"]["code"]
        poll_seconds = cfg.get("poll_seconds", 30)

        from monitor import all_target_crns, build_label_map
        build_label_map(cfg)
        targets = set(all_target_crns(cfg))

        client = BannerClient()
        state = load_state()

        try:
            client.initialize(term_code)
        except Exception as exc:
            self.logger.error(f"Session init failed: {exc}")
            self.root.after(0, self._stop_monitoring)
            return

        while not self.stop_event.is_set():
            try:
                seats = client.fetch_seats(term_code, targets)
                state = evaluate_and_alert(seats, state, cfg)
                save_state(state)

                # Update live table on GUI thread
                self.root.after(0, lambda s=seats, c=cfg: self._update_table(s, c))

                # Sleep in small increments to respond quickly to stop event
                for _ in range(poll_seconds * 2):
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.5)

            except Exception as exc:
                self.logger.error(f"Poll cycle error: {exc}")
                time.sleep(10)

        self.logger.info("Monitoring loop stopped cleanly.")

    # -----------------------------------------------------------------------
    # Table & Log Updates
    # -----------------------------------------------------------------------

    def _update_table(self, seats: dict[str, int | None], cfg: dict) -> None:
        """Refreshes the Treeview with latest seat counts."""
        from monitor import _crn_label, all_target_crns
        target_crns = all_target_crns(cfg)
        now_str = datetime.now(tz=TZ).strftime("%H:%M:%S")

        # Clear existing rows
        for item in self.tree.get_children():
            self.tree.delete(item)

        for crn in target_crns:
            label = _crn_label(crn, cfg)
            val = seats.get(crn)
            if val is None:
                seats_str = "MISSING"
                status_str = "⚠️ UNKNOWN / ERROR"
                tag = "unknown"
            elif val > 0:
                seats_str = f"🔥 {val} OPEN"
                status_str = "🎉 OPEN SEAT AVAILABLE"
                tag = "open"
            else:
                seats_str = "0"
                status_str = "Closed"
                tag = "closed"

            self.tree.insert(
                "",
                tk.END,
                values=(crn, label, seats_str, status_str, now_str),
                tags=(tag,),
            )

    def _process_log_queue(self) -> None:
        """Pulls log messages from thread-safe queue and appends to Text widget."""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        self.root.after(100, self._process_log_queue)

    def _on_close(self) -> None:
        """Cleanup on window exit."""
        if self.is_monitoring:
            self._stop_monitoring()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    root = tk.Tk()
    app = UosMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
