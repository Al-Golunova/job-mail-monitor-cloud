from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

from .config import Settings, get_service_account_info
from .utils import EVENT_HEADERS, canonicalize_headers, clip, extract_email_domain, normalize_text, text_to_keywords

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass
class JobMatch:
    row_number: int
    score: float
    company: str
    title: str


class SheetsClient:
    def __init__(self, settings: Settings):
        creds_info = get_service_account_info(settings)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(settings.google_sheet_id)
        self.settings = settings

        self.jobs_ws = self._get_or_create(settings.jobs_worksheet, rows=2000, cols=30)
        self.events_ws = self._get_or_create(settings.events_worksheet, rows=2000, cols=20)
        self._ensure_event_headers()
        self._ensure_job_headers()

    def _get_or_create(self, title: str, rows: int, cols: int):
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def _ensure_event_headers(self) -> None:
        first_row = self.events_ws.row_values(1)
        if first_row != EVENT_HEADERS:
            self.events_ws.update("A1", [EVENT_HEADERS])

    def _ensure_job_headers(self) -> None:
        headers = self.jobs_ws.row_values(1)
        if not headers:
            raise ValueError(
                f"Worksheet '{self.settings.jobs_worksheet}' is empty. Add your jobs header row first."
            )
        present = canonicalize_headers(headers)
        required_new = {
            "last_email_date": "last_email_date",
            "last_email_from": "last_email_from",
            "last_email_subject": "last_email_subject",
            "last_email_category": "last_email_category",
            "last_message_id": "last_message_id",
            "match_score": "match_score",
            "telegram_sent": "telegram_sent",
            "notes": "notes",
        }
        to_add = [column_name for key, column_name in required_new.items() if key not in present]
        if to_add:
            updated = headers + to_add
            self.jobs_ws.update("A1", [updated])

    def get_processed_message_ids(self) -> set[str]:
        records = self.events_ws.get_all_records(expected_headers=EVENT_HEADERS)
        ids = {str(row.get("message_id", "")).strip() for row in records if row.get("message_id")}
        ids.update({str(row.get("uid", "")).strip() for row in records if row.get("uid")})
        return ids

    def get_jobs(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        values = self.jobs_ws.get_all_values()
        headers = values[0]
        records = []
        for idx, row in enumerate(values[1:], start=2):
            padded = row + [""] * (len(headers) - len(row))
            record = dict(zip(headers, padded))
            record["_row_number"] = idx
            records.append(record)
        return records, canonicalize_headers(headers)

    def find_best_match(
        self,
        jobs: list[dict[str, Any]],
        header_map: dict[str, str],
        subject: str,
        body: str,
        from_email: str,
    ) -> JobMatch | None:
        company_col = header_map.get("company")
        title_col = header_map.get("title")
        link_col = header_map.get("link")
        if not company_col and not title_col:
            return None

        subject_n = normalize_text(subject)
        body_n = normalize_text(body)
        combined = f"{subject_n} {body_n}"
        combined_keywords = text_to_keywords(combined)
        sender_domain = extract_email_domain(from_email)

        best: JobMatch | None = None
        for row in jobs:
            company = row.get(company_col, "") if company_col else ""
            title = row.get(title_col, "") if title_col else ""
            link = row.get(link_col, "") if link_col else ""
            score = 0.0

            company_n = normalize_text(company)
            title_n = normalize_text(title)
            link_n = normalize_text(link)
            company_domain = extract_email_domain(link_n.replace("https://", "").replace("http://", "").split("/", 1)[0]) if link_n else ""

            if company_n and company_n in combined:
                score += 70
            else:
                company_tokens = text_to_keywords(company)
                overlap = len(company_tokens & combined_keywords)
                score += overlap * 12

            title_tokens = text_to_keywords(title)
            title_overlap = len(title_tokens & combined_keywords)
            score += title_overlap * 8

            if sender_domain and company_domain and sender_domain == company_domain:
                score += 30
            elif sender_domain and sender_domain in combined:
                score += 10

            if title_n and title_n in combined:
                score += 25

            if score > 0:
                candidate = JobMatch(
                    row_number=int(row["_row_number"]),
                    score=score,
                    company=company,
                    title=title,
                )
                if best is None or candidate.score > best.score:
                    best = candidate

        return best if best and best.score >= 35 else None

    def update_job_row(
        self,
        row_number: int,
        header_map: dict[str, str],
        *,
        status: str,
        email_date: str,
        email_from: str,
        email_subject: str,
        email_category: str,
        message_id: str,
        score: float,
        note: str,
        telegram_sent: str,
    ) -> None:
        headers = self.jobs_ws.row_values(1)
        header_index = {name: idx + 1 for idx, name in enumerate(headers)}

        canonical_to_real = {
            "status": header_map.get("status", "status"),
            "last_email_date": header_map.get("last_email_date", "last_email_date"),
            "last_email_from": header_map.get("last_email_from", "last_email_from"),
            "last_email_subject": header_map.get("last_email_subject", "last_email_subject"),
            "last_email_category": header_map.get("last_email_category", "last_email_category"),
            "last_message_id": header_map.get("last_message_id", "last_message_id"),
            "match_score": header_map.get("match_score", "match_score"),
            "notes": header_map.get("notes", "notes"),
            "telegram_sent": header_map.get("telegram_sent", "telegram_sent"),
        }

        updates = {
            canonical_to_real["status"]: status,
            canonical_to_real["last_email_date"]: email_date,
            canonical_to_real["last_email_from"]: email_from,
            canonical_to_real["last_email_subject"]: email_subject,
            canonical_to_real["last_email_category"]: email_category,
            canonical_to_real["last_message_id"]: message_id,
            canonical_to_real["match_score"]: str(score),
            canonical_to_real["notes"]: note,
            canonical_to_real["telegram_sent"]: telegram_sent,
        }

        cells = []
        for column_name, value in updates.items():
            col_index = header_index.get(column_name)
            if not col_index:
                continue
            cells.append(
                {
                    "range": f"{rowcol_to_a1(row_number, col_index)}",
                    "values": [[value]],
                }
            )
        if cells:
            self.jobs_ws.batch_update(cells)

    def append_event(
        self,
        *,
        message_id: str,
        uid: str,
        email_date: str,
        from_email: str,
        from_name: str,
        subject: str,
        category: str,
        matched_row: str,
        company: str,
        title: str,
        score: str,
        action: str,
    ) -> None:
        self.events_ws.append_row(
            [
                datetime.now(timezone.utc).isoformat(),
                message_id,
                uid,
                email_date,
                from_email,
                from_name,
                clip(subject, 300),
                category,
                matched_row,
                clip(company, 120),
                clip(title, 160),
                score,
                action,
            ],
            value_input_option="USER_ENTERED",
        )
