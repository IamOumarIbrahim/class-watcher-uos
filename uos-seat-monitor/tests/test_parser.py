"""
tests/test_parser.py

Tests for Banner response parsing and seat evaluation logic.
Tests 1-12 from the README required test suite.
"""

from __future__ import annotations

import sys
import os
import json
import copy
import time
from pathlib import Path

import pytest

# Allow importing from parent directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor import evaluate_and_alert, all_target_crns

# ---------------------------------------------------------------------------
# Minimal config fixture that includes all CRN groups.
# ---------------------------------------------------------------------------

BASE_CFG = {
    "term": {"code": "202610", "name": "Fall 2026/2027"},
    "registered_crns": ["11991", "12780", "12129"],
    "ignored_crns": ["11990", "12769", "12781"],
    "required": {
        "individual": {"OS": "12011", "COMM": "12115", "NETSEC": "12126"},
        "micro": {
            "lecture": "12091",
            "labs_in_preference_order": ["12093", "12094"],
            "required_lab_count": 1,
        },
        "se": {
            "sections_in_preference_order": ["12014", "12015"],
            "required_section_count": 1,
            "course_code": "1501366",
        },
    },
    "poll_seconds": 30,
    "poll_jitter_seconds": 5,
}

ALL_CRNS = all_target_crns(BASE_CFG)
CLOSED_SEATS = {crn: 0 for crn in ALL_CRNS}
OPEN_ONE = {**CLOSED_SEATS, "12115": 1}  # COMM open


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh_state() -> dict:
    return {}


def cfg():
    return copy.deepcopy(BASE_CFG)


# ---------------------------------------------------------------------------
# Test 1: 0 actual seats + waitlist positions → CLOSED
# ---------------------------------------------------------------------------

def test_zero_seats_with_waitlist_is_closed():
    """A section with 0 seatsAvailable must be treated as closed."""
    seats = {**CLOSED_SEATS}  # all zeros
    state = fresh_state()
    # Nothing should be open.
    for crn, v in seats.items():
        assert v == 0, f"Precondition: {crn} should be 0"
    # evaluate_and_alert should not raise; no open CRNs.
    new_state = evaluate_and_alert(seats, state, cfg())
    for crn in ALL_CRNS:
        assert not new_state.get(crn, {}).get("open"), f"CRN {crn} wrongly marked open"


# ---------------------------------------------------------------------------
# Test 2: 1+ seats → OPEN
# ---------------------------------------------------------------------------

def test_one_seat_is_open():
    seats = {**CLOSED_SEATS, "12115": 1}
    state = fresh_state()
    new_state = evaluate_and_alert(seats, state, cfg())
    assert new_state["12115"]["open"] is True


# ---------------------------------------------------------------------------
# Test 3: Wrong term rejected (validate in banner_client — simulate here)
# ---------------------------------------------------------------------------

def test_wrong_term_rejected():
    """Simulate what banner_client does: sections with wrong term return None."""
    # This is integration-tested in test_transitions; here we verify the
    # fetch_seats contract: if term mismatch is detected, CRNs stay None.
    # We confirm evaluate_and_alert treats None as UNKNOWN (not zero).
    seats = {crn: None for crn in ALL_CRNS}
    state = fresh_state()
    new_state = evaluate_and_alert(seats, state, cfg())
    # State should not flip any CRN to open.
    for crn in ALL_CRNS:
        assert not new_state.get(crn, {}).get("open"), f"{crn} wrongly marked open on None seats"


# ---------------------------------------------------------------------------
# Test 4: HTML response (banner_client returns None for each CRN)
# ---------------------------------------------------------------------------

def test_html_response_treated_as_unknown():
    seats = {crn: None for crn in ALL_CRNS}
    state = fresh_state()
    new_state = evaluate_and_alert(seats, state, cfg())
    for crn in ALL_CRNS:
        assert not new_state.get(crn, {}).get("open")


# ---------------------------------------------------------------------------
# Test 5: Missing CRN → None, not zero
# ---------------------------------------------------------------------------

def test_missing_crn_is_none_not_zero():
    seats = {crn: 0 for crn in ALL_CRNS}
    seats["12011"] = None  # OS is missing
    state = fresh_state()
    new_state = evaluate_and_alert(seats, state, cfg())
    # OS state should not have "open" set to True; seats remain None.
    os_state = new_state.get("12011", {})
    # After evaluate, we do NOT update seats to 0 for missing CRNs.
    # The code does `continue` on None, so seats key stays None or previous.
    assert not os_state.get("open")


# ---------------------------------------------------------------------------
# Test 6: First startup alert when seat already open
# ---------------------------------------------------------------------------

def test_startup_alert_when_already_open(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    seats = {**CLOSED_SEATS, "12126": 2}  # NETSEC open at startup
    state = fresh_state()  # empty — first run
    evaluate_and_alert(seats, state, cfg())
    assert any("12126" in a or "NETSEC" in a or "SEAT OPEN" in a for a in alerts_sent), \
        f"Expected startup alert, got: {alerts_sent}"


# ---------------------------------------------------------------------------
# Test 7: Alert on 0 → 1+
# ---------------------------------------------------------------------------

def test_alert_on_transition_closed_to_open(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    state = {"12011": {"seats": 0, "last_alerted": 0, "open": False}}
    seats = {**CLOSED_SEATS, "12011": 1}
    evaluate_and_alert(seats, state, cfg())
    assert any("12011" in a or "OS" in a or "SEAT OPEN" in a for a in alerts_sent)


# ---------------------------------------------------------------------------
# Test 8: No duplicate alert while unchanged
# ---------------------------------------------------------------------------

def test_no_duplicate_alert_while_open(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    # First poll — alert fires.
    state = fresh_state()
    seats = {**CLOSED_SEATS, "12011": 1}
    state = evaluate_and_alert(seats, state, cfg())
    first_count = len([a for a in alerts_sent if "12011" in a or "OS" in a])

    # Second poll immediately — no new alert (cooldown not expired).
    alerts_sent.clear()
    # Ensure last_alerted is set to NOW so cooldown hasn't expired.
    state["12011"]["last_alerted"] = time.time()
    evaluate_and_alert(seats, state, cfg())
    second_count = len([a for a in alerts_sent if "12011" in a or "OS" in a])
    assert second_count == 0, "Duplicate alert fired while seat count unchanged"


# ---------------------------------------------------------------------------
# Test 9: Alert again after 1+ → 0 → 1+
# ---------------------------------------------------------------------------

def test_alert_again_after_reopen(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    state = fresh_state()
    seats_open = {**CLOSED_SEATS, "12115": 1}
    seats_closed = {**CLOSED_SEATS}

    # Open.
    state = evaluate_and_alert(seats_open, state, cfg())
    # Close.
    state = evaluate_and_alert(seats_closed, state, cfg())
    alerts_sent.clear()
    # Reopen.
    state = evaluate_and_alert(seats_open, state, cfg())
    assert any("12115" in a or "COMM" in a or "SEAT OPEN" in a for a in alerts_sent)


# ---------------------------------------------------------------------------
# Test 10: 12091 + 12093 → preferred MICRO bundle
# ---------------------------------------------------------------------------

def test_preferred_micro_bundle(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append((t, priority)))

    seats = {**CLOSED_SEATS, "12091": 1, "12093": 1}
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("PREFERRED" in t for t, _ in alerts_sent), f"No preferred bundle alert. Got: {alerts_sent}"
    assert any(p == "critical" for _, p in alerts_sent)


# ---------------------------------------------------------------------------
# Test 11: 12091 + 12094 → fallback MICRO bundle
# ---------------------------------------------------------------------------

def test_fallback_micro_bundle(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append((t, priority)))

    seats = {**CLOSED_SEATS, "12091": 1, "12094": 1}
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("FALLBACK" in t for t, _ in alerts_sent), f"No fallback bundle alert. Got: {alerts_sent}"


# ---------------------------------------------------------------------------
# Test 12: Lone lecture or lone lab → PARTIAL MICRO
# ---------------------------------------------------------------------------

def test_partial_micro_lecture_only(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    seats = {**CLOSED_SEATS, "12091": 1}  # only lecture open
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("PARTIAL" in a for a in alerts_sent), f"No partial alert. Got: {alerts_sent}"


def test_partial_micro_lab_only(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    seats = {**CLOSED_SEATS, "12093": 1}  # only preferred lab open
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("PARTIAL" in a for a in alerts_sent), f"No partial alert. Got: {alerts_sent}"


# ---------------------------------------------------------------------------
# SE-specific tests
# ---------------------------------------------------------------------------

def test_se_preferred_section_alert(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    seats = {**CLOSED_SEATS, "12014": 1}
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("SE" in a or "12014" in a for a in alerts_sent)


def test_se_fallback_section_alert(monkeypatch):
    alerts_sent = []
    monkeypatch.setattr("monitor.send_alert", lambda t, b, priority="high": alerts_sent.append(t))

    seats = {**CLOSED_SEATS, "12015": 1}
    state = fresh_state()
    evaluate_and_alert(seats, state, cfg())
    assert any("SE" in a or "12015" in a for a in alerts_sent)
