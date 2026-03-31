from __future__ import annotations

import re
from dataclasses import dataclass

from .imap_client import MailItem
from .utils import normalize_text


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    reason: str


PATTERNS: list[tuple[str, float, list[str]]] = [
    (
        "offer",
        0.98,
        [
            r"\bjob offer\b",
            r"\boffer of employment\b",
            r"\bvertragsangebot\b",
            r"\barbeitsvertrag\b",
            r"\bangebot fur die stelle\b",
            r"\bangebot fur ihre bewerbung\b",
        ],
    ),
    (
        "interview",
        0.97,
        [
            r"\binterview\b",
            r"\binterview invitation\b",
            r"\bjob interview\b",
            r"\bvorstellungsgesprach\b",
            r"\beinladung zum gesprach\b",
            r"\beinladung zum interview\b",
            r"\bkennenlerngesprach\b",
            r"\bteams interview\b",
            r"\bzoom interview\b",
        ],
    ),
    (
        "documents",
        0.95,
        [
            r"\bplease send\b",
            r"\bmissing documents\b",
            r"\bsend us\b",
            r"\bweitere unterlagen\b",
            r"\bunterlagen\b",
            r"\bnachweise\b",
            r"\bzeugnisse\b",
            r"\blebenslauf\b",
            r"\banschreiben\b",
            r"\bportfolio\b",
        ],
    ),
    (
        "rejection",
        0.96,
        [
            r"\bunfortunately\b",
            r"\bwe regret to inform you\b",
            r"\bnot moving forward\b",
            r"\babsage\b",
            r"\bleider\b",
            r"\bhaben uns fur andere kandidaten entschieden\b",
            r"\bderzeit nicht berucksichtigen\b",
        ],
    ),
    (
        "auto_reply",
        0.88,
        [
            r"\bauto.?reply\b",
            r"\bout of office\b",
            r"\bautomatische antwort\b",
            r"\babwesenheitsnotiz\b",
            r"\beingangsbestatigung\b",
            r"\bthank you for your application\b",
            r"\bthank you for applying\b",
            r"\bwir haben ihre bewerbung erhalten\b",
        ],
    ),
]


def classify_email(mail: MailItem) -> ClassificationResult:
    haystack = normalize_text(f"{mail.subject}\n{mail.body_text}")

    for category, confidence, patterns in PATTERNS:
        for pattern in patterns:
            if re.search(pattern, haystack):
                return ClassificationResult(category=category, confidence=confidence, reason=pattern)

    if any(token in haystack for token in ["application", "bewerbung", "position", "vacancy", "stelle"]):
        return ClassificationResult(category="reply", confidence=0.65, reason="generic_application_reply")

    return ClassificationResult(category="other", confidence=0.35, reason="no_rule_matched")
