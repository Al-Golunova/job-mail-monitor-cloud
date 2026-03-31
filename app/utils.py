from __future__ import annotations

import re
import unicodedata
from html import unescape
from typing import Iterable

from bs4 import BeautifulSoup


HEADER_ALIASES = {
    "company": ["company", "firma", "unternehmen", "arbeitgeber"],
    "title": ["title", "job_title", "position", "rolle", "stellenbezeichnung", "vacancy", "job"],
    "link": ["link", "job_link", "url", "vacancy_link", "stellenlink"],
    "status": ["status", "bewerbungsstatus", "application_status"],
    "notes": ["notes", "note", "kommentar", "bemerkung"],
    "applied_date": ["applied_date", "application_date", "bewerbungsdatum", "date_applied"],
    "job_id": ["job_id", "id", "record_id"],
    "telegram_sent": ["telegram_sent", "telegram", "notification_sent"],
    "last_email_date": ["last_email_date", "email_date"],
    "last_email_from": ["last_email_from", "email_from"],
    "last_email_subject": ["last_email_subject", "email_subject"],
    "last_email_category": ["last_email_category", "email_category"],
    "last_message_id": ["last_message_id", "message_id", "last_processed_message_id"],
    "match_score": ["match_score", "score"],
}


EVENT_HEADERS = [
    "processed_at",
    "message_id",
    "uid",
    "email_date",
    "from_email",
    "from_name",
    "subject",
    "category",
    "matched_row",
    "company",
    "title",
    "score",
    "action",
]


def normalize_text(value: str) -> str:
    value = unescape(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9@._+\-\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def text_to_keywords(value: str) -> set[str]:
    value = normalize_text(value)
    return {token for token in value.split() if len(token) >= 3}


def html_to_text(value: str) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    return soup.get_text(" ", strip=True)


def first_present(mapping: dict[str, str], aliases: Iterable[str]) -> str | None:
    for alias in aliases:
        if alias in mapping:
            return mapping[alias]
    return None


def canonicalize_headers(headers: list[str]) -> dict[str, str]:
    normalized_headers = {normalize_text(h): h for h in headers if h}
    result: dict[str, str] = {}
    for canonical, variants in HEADER_ALIASES.items():
        for variant in variants:
            if variant in normalized_headers:
                result[canonical] = normalized_headers[variant]
                break
    return result


def extract_email_domain(email_address: str) -> str:
    email_address = email_address.lower().strip()
    return email_address.split("@", 1)[1] if "@" in email_address else ""


def clip(value: str, limit: int = 500) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"
