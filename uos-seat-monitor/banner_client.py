"""
banner_client.py - Public Banner search client for UoS seat monitor.

Uses the public Browse Classes flow (no UoS/Microsoft credentials required).
"""

from __future__ import annotations

import logging
import time
import random
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://reg-prod.ec.sharjah.ac.ae/StudentRegistrationSsb"
TERM_PAGE = f"{BASE_URL}/ssb/term/termSelection?mode=search"
SEARCH_URL = f"{BASE_URL}/ssb/searchResults/searchResults"
TERM_SUBMIT_URL = f"{BASE_URL}/ssb/term/search?mode=search"

SUBJECTS = ["1501", "1502"]
COURSE_NUMBERS = ["232", "352", "346", "444", "366"]

PAGE_MAX = 500
REQUEST_TIMEOUT = 20


class BannerClient:
    """Stateful HTTP client for the public UoS Banner search flow."""

    def __init__(self) -> None:
        self.session: Optional[requests.Session] = None
        self._term_code: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self, term_code: str) -> None:
        """Open the public term page, set cookies, and select the given term."""
        self._term_code = term_code
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        # Step 1: Open term selection page to obtain cookies / CSRF tokens.
        logger.info("Opening public term page …")
        resp = self.session.get(TERM_PAGE, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        logger.debug("Term page status: %s", resp.status_code)

        # Step 2: POST to select the term (initialises the search session).
        logger.info("Selecting term %s …", term_code)
        resp = self.session.post(
            TERM_SUBMIT_URL,
            data={"dataType": "json", "term": term_code},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.debug("Term selection response: %s %s", resp.status_code, resp.text[:120])
        logger.info("PUBLIC TERM SESSION READY")

    def fetch_seats(self, term_code: str, target_crns: set[str]) -> dict[str, int | None]:
        """
        Query the public Banner search endpoint for all relevant subjects/courses
        and return a mapping of CRN -> seats_available (None = CRN missing / error).
        """
        if self.session is None:
            raise RuntimeError("Call initialize() before fetch_seats()")

        crn_seats: dict[str, int | None] = {crn: None for crn in target_crns}
        found: dict[str, int] = {}

        for subject in SUBJECTS:
            for course_number in COURSE_NUMBERS:
                result = self._query_subject_course(term_code, subject, course_number)
                if result is None:
                    continue
                for section in result:
                    crn = str(section.get("courseReferenceNumber", ""))
                    seats = section.get("seatsAvailable")
                    if crn in target_crns:
                        found[crn] = int(seats) if seats is not None else 0

        # Build final mapping: tracked CRNs use found value or stay None.
        for crn in target_crns:
            crn_seats[crn] = found.get(crn)  # None if not found in response

        logger.info(
            "ALL TARGET CRNS VALIDATED"
            if all(v is not None for v in crn_seats.values())
            else "WARNING: some CRNs missing from response: %s",
            [crn for crn, v in crn_seats.items() if v is None],
        )
        return crn_seats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_subject_course(
        self, term_code: str, subject: str, course_number: str
    ) -> list[dict] | None:
        """
        Query Banner for a single subject+course combination.
        Returns the list of section dicts, or None on error.
        """
        params = {
            "txt_term": term_code,
            "txt_subject": subject,
            "txt_courseNumber": course_number,
            "pageOffset": "0",
            "pageMaxSize": str(PAGE_MAX),
            "sortColumn": "courseReferenceNumber",
            "sortDirection": "asc",
        }
        try:
            resp = self.session.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.warning("Network error querying %s %s: %s", subject, course_number, exc)
            return None

        if resp.status_code != 200:
            logger.warning(
                "Non-200 from Banner for %s %s: %s", subject, course_number, resp.status_code
            )
            return None

        # Detect HTML error/login page masquerading as a response.
        ct = resp.headers.get("Content-Type", "")
        if "html" in ct.lower():
            logger.warning(
                "HTML response received for %s %s — session may have expired",
                subject,
                course_number,
            )
            return None

        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("Invalid JSON for %s %s: %s", subject, course_number, exc)
            return None

        # Validate term.
        actual_term = data.get("term", {}).get("code") if isinstance(data.get("term"), dict) else None
        # Some Banner versions embed term differently — also check first section.
        sections: list[dict] = data.get("data", []) or []
        if sections:
            first_term = str(sections[0].get("term", ""))
            if first_term and first_term != term_code:
                logger.error(
                    "Term mismatch! Expected %s, got %s — discarding response",
                    term_code,
                    first_term,
                )
                return None

        return sections

    def reset(self, term_code: str) -> None:
        """Re-initialize the session (called after expiry or repeated errors)."""
        logger.info("Reinitializing public term session …")
        try:
            self.initialize(term_code)
        except Exception as exc:
            logger.error("Session reinit failed: %s", exc)
            raise
