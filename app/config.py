from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    gmx_email: str
    gmx_password: str
    imap_host: str = "imap.gmx.com"
    imap_port: int = 993
    mailbox: str = "INBOX"
    scan_days: int = 14
    google_sheet_id: str = ""
    jobs_worksheet: str = "jobs"
    events_worksheet: str = "mail_events"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = True
    notify_on: tuple[str, ...] = ("interview", "documents", "offer")
    google_service_account_json: Optional[str] = None
    google_service_account_file: Optional[str] = None
    max_messages_per_run: int = 200
    dry_run: bool = False


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def load_settings() -> Settings:
    settings = Settings(
        gmx_email=os.getenv("GMX_EMAIL", "").strip(),
        gmx_password=os.getenv("GMX_PASSWORD", "").strip(),
        imap_host=os.getenv("IMAP_HOST", "imap.gmx.com").strip(),
        imap_port=_get_int("IMAP_PORT", 993),
        mailbox=os.getenv("MAILBOX", "INBOX").strip(),
        scan_days=_get_int("SCAN_DAYS", 14),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
        jobs_worksheet=os.getenv("JOBS_WORKSHEET", "jobs").strip(),
        events_worksheet=os.getenv("EVENTS_WORKSHEET", "mail_events").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        telegram_enabled=_get_bool("TELEGRAM_ENABLED", True),
        notify_on=_get_tuple("NOTIFY_ON", ("interview", "documents", "offer")),
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        max_messages_per_run=_get_int("MAX_MESSAGES_PER_RUN", 200),
        dry_run=_get_bool("DRY_RUN", False),
    )

    missing = []
    if not settings.gmx_email:
        missing.append("GMX_EMAIL")
    if not settings.gmx_password:
        missing.append("GMX_PASSWORD")
    if not settings.google_sheet_id:
        missing.append("GOOGLE_SHEET_ID")
    if not (settings.google_service_account_json or settings.google_service_account_file):
        missing.append("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")

    if missing:
        raise ValueError(f"Missing required settings: {', '.join(missing)}")

    return settings


def get_service_account_info(settings: Settings) -> dict:
    if settings.google_service_account_json:
        return json.loads(settings.google_service_account_json)
    assert settings.google_service_account_file
    with open(settings.google_service_account_file, "r", encoding="utf-8") as fh:
        return json.load(fh)
