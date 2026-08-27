"""
banner_client.py - Public Banner search client for UoS seat monitor.

Uses the public Browse Classes flow (no UoS/Microsoft credentials required).

KEY DISCOVERY: The UoS Banner server issues a single-use search JSESSIONID.
Each JSESSIONID only serves ONE searchResults query before returning empty
data for all subsequent queries in the same session. The workaround is to
reinitialise the full session (new JSESSIONID) for every poll cycle.
One query per subject (1501, 1502) fetches all course data in one shot.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://reg-prod.ec.sharjah.ac.ae/StudentRegistrationSsb"
TERM_PAGE = f"{BASE_URL}/ssb/term/termSelection?mode=search"
SEARCH_URL = f"{BASE_URL}/ssb/searchResults/searchResults"
TERM_SUBMIT_URL = f"{BASE_URL}/ssb/term/search?mode=search"

SUBJECTS = [
    "1501",  # Computer Science
    "1502",  # Computer Engineering
    "0402",  # Electrical / Telecom Engineering
    "1503",  # Information Technology
    "1504",  # Cybersecurity
    "1505",  # Artificial Intelligence
    "1401",  # Mathematics
    "1402",  # Physics
    "0401",  # General Engineering
    "0404",  # Mechanical Engineering
]

PAGE_MAX = 500
REQUEST_TIMEOUT = 20


class BannerClient:
    """
    HTTP client for the public UoS Banner search flow.

    Because Banner's JSESSIONID is single-use per search query, we create a
    fresh session for every poll cycle rather than trying to reuse one.
    """

    def __init__(self) -> None:
        self._term_code: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self, term_code: str) -> None:
        """Store the term code; actual session is created per fetch."""
        self._term_code = term_code
        # Validate connectivity: do one quick session init to confirm the
        # server is reachable and the term is accepted.
        logger.info("Opening public term page …")
        session = self._new_session(term_code)
        logger.info("PUBLIC TERM SESSION READY")

    def fetch_seats(self, term_code: str, target_crns: set[str]) -> dict[str, int | None]:
        """
        Query the public Banner search endpoint.

        A fresh HTTP session is created for every call because the Banner
        server only honours one searchResults query per JSESSIONID.
        Results from target subjects are combined and filtered by CRN.
        """
        crn_seats: dict[str, int | None] = {crn: None for crn in target_crns}
        found: dict[str, int] = {}

        for subject in SUBJECTS:
            # Stop querying further subjects if all targets have already been found
            if target_crns and all(crn in found for crn in target_crns):
                break

            # Each subject query needs its own fresh session.
            try:
                session = self._new_session(term_code)
            except Exception as exc:
                logger.warning("Session init failed for subject %s: %s", subject, exc)
                continue

            result = self._query_subject(session, term_code, subject)
            if result is None:
                continue
            for section in result:
                crn = str(section.get("courseReferenceNumber", ""))
                seats = section.get("seatsAvailable")
                if crn in target_crns:
                    # Banner returns negative seatsAvailable when over-enrolled.
                    # Clamp to 0: anything <= 0 is treated as closed.
                    raw = int(seats) if seats is not None else 0
                    found[crn] = max(raw, 0)

        # Build final mapping.
        for crn in target_crns:
            crn_seats[crn] = found.get(crn)  # None = CRN absent from response

        missing = [crn for crn, v in crn_seats.items() if v is None]
        if missing:
            logger.warning("WARNING: some CRNs missing from response: %s", missing)
        else:
            logger.info("ALL TARGET CRNS VALIDATED")

        return crn_seats

    def reset(self, term_code: str) -> None:
        """No persistent state to reset; kept for API compatibility."""
        logger.info("Reset requested ? next fetch will use a fresh session.")
        self._term_code = term_code

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_session(self, term_code: str) -> requests.Session:
        """
        Create a fresh requests.Session, navigate to the term page, and
        POST to select the given term. Returns the ready session.
        """
        session = requests.Session()
        session.headers.update(
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
        resp = session.get(TERM_PAGE, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp = session.post(
            TERM_SUBMIT_URL,
            data={"dataType": "json", "term": term_code},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return session

    def _query_subject(
        self, session: requests.Session, term_code: str, subject: str
    ) -> list[dict] | None:
        """
        Query Banner for ALL courses under a subject.
        Returns the list of section dicts, or None on error.
        """
        params = {
            "txt_term": term_code,
            "txt_subject": subject,
            "pageOffset": "0",
            "pageMaxSize": str(PAGE_MAX),
            "sortColumn": "courseReferenceNumber",
            "sortDirection": "asc",
        }
        try:
            resp = session.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.warning("Network error querying subject %s: %s", subject, exc)
            return None

        if resp.status_code != 200:
            logger.warning("Non-200 from Banner for subject %s: %s", subject, resp.status_code)
            return None

        ct = resp.headers.get("Content-Type", "")
        if "html" in ct.lower():
            logger.warning(
                "HTML response for subject %s ? session may have been redirected to login", subject
            )
            return None

        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("Invalid JSON for subject %s: %s", subject, exc)
            return None

        sections: list[dict] = data.get("data") or []

        # Validate term on first section.
        if sections:
            first_term = str(sections[0].get("term", ""))
            if first_term and first_term != term_code:
                logger.error(
                    "Term mismatch! Expected %s, got %s ? discarding response", term_code, first_term
                )
                return None

        logger.debug("Subject %s: %d sections returned", subject, len(sections))
        return sections
