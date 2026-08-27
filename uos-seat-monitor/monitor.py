"""
monitor.py - Main polling loop for UoS seat monitor.

Usage:
    python monitor.py              # continuous monitor
    python monitor.py --once       # single poll, print table, exit
    python monitor.py --test-notification  # send test notification and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from banner_client import BannerClient
from notifications import send_alert, send_test_notification

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

TZ = ZoneInfo("Asia/Dubai")
CONFIG_PATH = Path(__file__).parent / "config.json"
STATE_PATH = Path(__file__).parent / "state.json"
LOG_PATH = Path(__file__).parent / "monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def all_target_crns(cfg: dict) -> list[str]:
    """Return every CRN that must be monitored."""
    crns: list[str] = []
    req = cfg.get("required", {})
    if "individual" in req:
        crns += list(req["individual"].values())
    if "micro" in req:
        micro = req["micro"]
        crns.append(micro["lecture"])
        crns += micro.get("labs_in_preference_order", [])
    se = req.get("se", {})
    crns += se.get("sections_in_preference_order", [])
    watch_only = cfg.get("watch_only", {})
    crns += list(watch_only.values())
    # Preserve order while removing any duplicates
    return list(dict.fromkeys(c for c in crns if c))


def load_state() -> dict[str, dict]:
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Alert logic
# ---------------------------------------------------------------------------

COOLDOWN_SECONDS = 60  # re-alert after this long if seat still open


def evaluate_and_alert(
    seats: dict[str, int | None],
    state: dict[str, dict],
    cfg: dict,
) -> dict[str, dict]:
    """
    Compare current seat counts against persisted state.
    Fire alerts for transitions and MICRO / SE bundle conditions.
    Returns updated state.
    """
    now = time.time()
    req = cfg.get("required", {})
    micro = req.get("micro")
    se = req.get("se", {})

    # --- Per-CRN individual alerts ---
    for crn, seats_now in seats.items():
        crn_state = state.setdefault(crn, {"seats": None, "last_alerted": 0, "open": False})
        prev_seats = crn_state.get("seats")

        if seats_now is None:
            # CRN not found — monitor error, do not treat as closed.
            logger.warning("CRN %s missing from Banner response — treating as UNKNOWN", crn)
            continue

        opened = (prev_seats is None or prev_seats == 0) and seats_now > 0
        still_open = crn_state.get("open") and seats_now > 0
        reminder_due = still_open and (now - crn_state.get("last_alerted", 0)) >= COOLDOWN_SECONDS

        if opened or reminder_due:
            label = _crn_label(crn, cfg)
            title = f"UOS SEAT OPEN - {label}"
            body = (
                f"{label} - CRN {crn}\n"
                f"Seats available: {seats_now}\n"
                f"Open registration immediately."
            )
            send_alert(title, body, priority="high")
            crn_state["last_alerted"] = now

        crn_state["seats"] = seats_now
        crn_state["open"] = seats_now > 0
        state[crn] = crn_state

    # --- MICRO bundle alerts ---
    if micro:
        lecture_crn = micro["lecture"]
        lab_crns = micro.get("labs_in_preference_order", [])  # [preferred, fallback]

        lecture_open = (seats.get(lecture_crn) or 0) > 0
        preferred_lab_open = len(lab_crns) > 0 and (seats.get(lab_crns[0]) or 0) > 0
        fallback_lab_open = len(lab_crns) > 1 and (seats.get(lab_crns[1]) or 0) > 0

        preferred_bundle = lecture_open and preferred_lab_open
        fallback_bundle = lecture_open and fallback_lab_open

        bundle_state = state.setdefault("_micro_bundle", {"last_alerted": 0, "level": None})
        last_bundle_alert = bundle_state.get("last_alerted", 0)
        current_level = bundle_state.get("level")

        if preferred_bundle:
            new_level = "preferred"
            if current_level != "preferred" or (now - last_bundle_alert) >= COOLDOWN_SECONDS:
                send_alert(
                    "UOS MICRO BUNDLE OPEN - PREFERRED",
                    f"CRITICAL - PREFERRED MICRO BUNDLE OPEN\n"
                    f"Lecture: {lecture_crn}\n"
                    f"Preferred lab: {lab_crns[0]}\n"
                    f"Both currently have seats. Register both together IMMEDIATELY.",
                    priority="critical",
                )
                bundle_state["last_alerted"] = now
            bundle_state["level"] = new_level
        elif fallback_bundle:
            new_level = "fallback"
            if current_level != "fallback" or (now - last_bundle_alert) >= COOLDOWN_SECONDS:
                send_alert(
                    "UOS MICRO BUNDLE OPEN - FALLBACK",
                    f"CRITICAL - FALLBACK MICRO BUNDLE OPEN\n"
                    f"Lecture: {lecture_crn}\n"
                    f"Fallback lab: {lab_crns[1] if len(lab_crns) > 1 else 'N/A'}\n"
                    f"Register both together IMMEDIATELY.",
                    priority="critical",
                )
                bundle_state["last_alerted"] = now
            bundle_state["level"] = new_level
        elif lecture_open or preferred_lab_open or fallback_lab_open:
            new_level = "partial"
            if current_level != "partial" or (now - last_bundle_alert) >= COOLDOWN_SECONDS:
                open_parts = []
                if lecture_open:
                    open_parts.append(f"Lecture {lecture_crn}")
                if preferred_lab_open:
                    open_parts.append(f"Preferred lab {lab_crns[0]}")
                if fallback_lab_open and len(lab_crns) > 1:
                    open_parts.append(f"Fallback lab {lab_crns[1]}")
                send_alert(
                    "HIGH - PARTIAL MICRO AVAILABILITY",
                    f"PARTIAL MICRO AVAILABILITY\n"
                    f"Open: {', '.join(open_parts)}\n"
                    f"Wait for the paired component before registering.",
                    priority="high",
                )
                bundle_state["last_alerted"] = now
            bundle_state["level"] = new_level
        else:
            bundle_state["level"] = None

        state["_micro_bundle"] = bundle_state

    # --- SE bundle alerts ---
    se_crns = se.get("sections_in_preference_order", [])
    if se_crns:
        se_bundle_state = state.setdefault("_se_bundle", {"last_alerted": 0, "level": None})
        last_se_alert = se_bundle_state.get("last_alerted", 0)
        current_se_level = se_bundle_state.get("level")

        preferred_se_open = (seats.get(se_crns[0]) or 0) > 0
        fallback_se_open = len(se_crns) > 1 and (seats.get(se_crns[1]) or 0) > 0

        if preferred_se_open:
            new_se_level = "preferred"
            if current_se_level != "preferred" or (now - last_se_alert) >= COOLDOWN_SECONDS:
                send_alert(
                    f"UOS SE SEAT OPEN - CRN {se_crns[0]}",
                    f"SE (Software Engineering) preferred section has seats!\n"
                    f"CRN: {se_crns[0]}\n"
                    f"Seats: {seats.get(se_crns[0])}\n"
                    f"Register CRN {se_crns[0]} immediately.",
                    priority="high",
                )
                se_bundle_state["last_alerted"] = now
            se_bundle_state["level"] = new_se_level
        elif fallback_se_open:
            new_se_level = "fallback"
            if current_se_level != "fallback" or (now - last_se_alert) >= COOLDOWN_SECONDS:
                send_alert(
                    f"UOS SE SEAT OPEN - CRN {se_crns[1]}",
                    f"SE (Software Engineering) fallback section has seats!\n"
                    f"CRN: {se_crns[1]}\n"
                    f"Seats: {seats.get(se_crns[1])}\n"
                    f"Register CRN {se_crns[1]} immediately (preferred {se_crns[0]} is closed).",
                    priority="high",
                )
                se_bundle_state["last_alerted"] = now
            se_bundle_state["level"] = new_se_level
        else:
            se_bundle_state["level"] = None

        state["_se_bundle"] = se_bundle_state

    return state


# ---------------------------------------------------------------------------
# Display table
# ---------------------------------------------------------------------------

LABEL_MAP: dict[str, str] = {}  # populated by build_label_map


def build_label_map(cfg: dict) -> None:
    req = cfg.get("required", {})
    if "individual" in req:
        for name, crn in req["individual"].items():
            LABEL_MAP[crn] = name
    if "micro" in req:
        micro = req["micro"]
        LABEL_MAP[micro["lecture"]] = "MICRO-LEC"
        labs = micro.get("labs_in_preference_order", [])
        if labs:
            LABEL_MAP[labs[0]] = "MICRO-LAB-PREF"
        if len(labs) > 1:
            LABEL_MAP[labs[1]] = "MICRO-LAB-FALL"
    se = req.get("se", {})
    se_crns = se.get("sections_in_preference_order", [])
    if se_crns:
        LABEL_MAP[se_crns[0]] = "SE-A"
    if len(se_crns) > 1:
        LABEL_MAP[se_crns[1]] = "SE-B"
    watch_only = cfg.get("watch_only", {})
    for name, crn in watch_only.items():
        LABEL_MAP[crn] = name


def _crn_label(crn: str, cfg: dict) -> str:
    if not LABEL_MAP:
        build_label_map(cfg)
    return LABEL_MAP.get(crn, crn)


def print_table(seats: dict[str, int | None], cfg: dict) -> None:
    now_str = datetime.now(tz=TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"\n{'='*54}")
    print(f"  UoS Seat Monitor   {now_str}")
    print(f"{'='*54}")
    print(f"  {'CRN':<8} {'Label':<18} {'Seats':>7}  {'Status'}")
    print(f"  {'-'*48}")
    target_crns = all_target_crns(cfg)
    for crn in target_crns:
        label = _crn_label(crn, cfg)
        s = seats.get(crn)
        if s is None:
            seats_str = " MISS"
            status = "UNKNOWN"
        elif s == 0:
            seats_str = f"{s:>5}"
            status = "closed"
        else:
            seats_str = f"{s:>5}"
            status = f"*** OPEN ***"
        print(f"  {crn:<8} {label:<18} {seats_str}   {status}")
    print(f"{'='*54}\n")


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def run(once: bool = False, test_notification: bool = False) -> None:
    logger.info("MONITOR STARTED")

    if test_notification:
        send_test_notification()
        logger.info("Test notification sent. Exiting.")
        return

    cfg = load_config()
    term_code = cfg["term"]["code"]
    poll_seconds = cfg.get("poll_seconds", 30)
    jitter = cfg.get("poll_jitter_seconds", 5)
    targets = set(all_target_crns(cfg))

    build_label_map(cfg)

    client = BannerClient()
    state = load_state()

    backoff_sequence = [60, 120, 300]
    consecutive_errors = 0
    degraded = False

    try:
        client.initialize(term_code)
    except Exception as exc:
        logger.error("Initial session setup failed: %s", exc)
        sys.exit(1)

    while True:
        try:
            seats = client.fetch_seats(term_code, targets)
            consecutive_errors = 0
            if degraded:
                logger.info("MONITOR RECOVERED")
                degraded = False

            state = evaluate_and_alert(seats, state, cfg)
            save_state(state)
            print_table(seats, cfg)
            logger.info(
                "Poll OK | %s",
                " | ".join(
                    f"{crn}={v if v is not None else 'MISSING'}"
                    for crn, v in seats.items()
                ),
            )

            if once:
                break

            sleep_time = poll_seconds + random.uniform(-jitter, jitter)
            time.sleep(max(sleep_time, 20))

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user.")
            break

        except Exception as exc:
            consecutive_errors += 1
            backoff = backoff_sequence[min(consecutive_errors - 1, len(backoff_sequence) - 1)]
            logger.error("Poll error #%d: %s — backing off %ds", consecutive_errors, exc, backoff)
            if consecutive_errors >= 3 and not degraded:
                logger.warning("MONITOR DEGRADED")
                degraded = True

            # Try to reinitialize session on repeated failures.
            if consecutive_errors % 3 == 0:
                try:
                    client.reset(term_code)
                except Exception:
                    pass

            if once:
                raise

            time.sleep(backoff)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UoS Course Seat Monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Perform one live check, print table, and exit.",
    )
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Send a test notification across all channels and exit.",
    )
    args = parser.parse_args()
    run(once=args.once, test_notification=args.test_notification)
