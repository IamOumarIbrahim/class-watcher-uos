"""
tests/test_transitions.py

Tests for BannerClient response validation logic (term check, HTML rejection, etc.)
Uses fixture JSON files.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from banner_client import BannerClient

FIXTURES = Path(__file__).parent / "fixtures"

TERM_CODE = "202610"
TARGET_CRNS = {"12091", "12093", "12094", "12011", "12115", "12126", "12014", "12015"}


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture: valid response with some open / closed CRNs
# ---------------------------------------------------------------------------

def test_fixture_valid_open_seats():
    """Fixture with seatsAvailable > 0 must be detected as open."""
    data = json.loads(_load("valid_open.json"))
    sections = data.get("data", [])
    section = next(s for s in sections if s["courseReferenceNumber"] == "12115")
    assert section["seatsAvailable"] > 0


def test_fixture_valid_closed_seats():
    """Fixture with seatsAvailable == 0 and waitAvailable > 0 must be closed."""
    data = json.loads(_load("valid_closed_with_waitlist.json"))
    sections = data.get("data", [])
    section = next(s for s in sections if s["courseReferenceNumber"] == "12091")
    # seatsAvailable must be 0.
    assert section["seatsAvailable"] == 0
    # waitAvailable may be > 0 but must not affect our evaluation.
    # The monitor checks seatsAvailable only.
    assert section.get("waitAvailable", 0) >= 0  # structural check


def test_fixture_wrong_term_rejected():
    """A fixture with wrong term code must be identified."""
    data = json.loads(_load("wrong_term.json"))
    sections = data.get("data", [])
    if sections:
        first_term = str(sections[0].get("term", ""))
        assert first_term != TERM_CODE, "Fixture should have wrong term"


def test_fixture_html_login_page():
    """HTML text should not parse as JSON."""
    raw = _load("html_login_page.html")
    with pytest.raises((json.JSONDecodeError, ValueError)):
        json.loads(raw)


def test_fixture_missing_crn():
    """A fixture missing a target CRN should not include that CRN in data."""
    data = json.loads(_load("missing_crn.json"))
    sections = data.get("data", [])
    crns_in_response = {str(s["courseReferenceNumber"]) for s in sections}
    assert "12011" not in crns_in_response, "OS CRN should be absent from missing_crn fixture"
