"""Deterministic preflight contract for Phase 4 routing examples.

Production routing belongs to the Dialogflow CX default playbook. This small,
dependency-free classifier only makes route ownership executable in CI; it is not
used by the FastAPI service and is not a substitute for generative-agent tests.
"""

from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


ROUTE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ComplaintManagement",
        (
            r"\bbeschwer",
            r"\bunzufrieden\b",
            r"\bmensch(?:en)?\b",
            r"\bmitarbeiter(?:in)?\b",
            r"\bverbinden\b",
        ),
    ),
    (
        "AppointmentManagement",
        (
            r"\btermin",
            r"\b(?:wann|ob)\b.*\btechniker\b",
            r"\btechniker\b.*\b(?:kommt|kommen|da)\b",
            r"\bverschieb",
            r"\bslot\b",
            r"\buhr\b.*\bfrei\b",
        ),
    ),
    (
        "ServiceTicket",
        (
            r"\bticket\b",
            r"\bservicefall\b",
            r"\bstorung\b",
        ),
    ),
    (
        "KnowledgeSupport",
        (
            r"\bfehler(?:code)?\b",
            r"\be\d{2}\b",
            r"\bhandbuch\b",
            r"\bgarantie\b",
            r"\bwarmepumpe\b",
        ),
    ),
)


def select_playbook(utterance: str) -> str:
    """Return the contract owner for a German Phase 4 utterance."""

    normalized = _normalize(utterance)
    for playbook, patterns in ROUTE_PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return playbook
    return "DefaultService"
