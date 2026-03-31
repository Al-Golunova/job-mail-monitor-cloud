from __future__ import annotations

import email
import imaplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime, parseaddr
from typing import Iterable

from .config import Settings
from .utils import html_to_text


@dataclass
class MailItem:
    uid: str
    message_id: str
    date: datetime
    from_name: str
    from_email: str
    subject: str
    body_text: str
    raw_from: str


class GMXImapClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "GMXImapClient":
        context = ssl.create_default_context()
        self._client = imaplib.IMAP4_SSL(
            self.settings.imap_host,
            self.settings.imap_port,
            ssl_context=context,
        )
        self._client.login(self.settings.gmx_email, self.settings.gmx_password)
        self._client.select(self.settings.mailbox)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            try:
                self._client.logout()
            except Exception:
                pass

    def fetch_recent_messages(self, scan_days: int, max_messages: int) -> list[MailItem]:
        assert self._client is not None
        since_date = (datetime.now(timezone.utc) - timedelta(days=scan_days)).strftime("%d-%b-%Y")
        status, data = self._client.uid("search", None, f'(SINCE "{since_date}")')
        if status != "OK":
            raise RuntimeError("IMAP search failed")

        uids = data[0].split()
        selected = list(reversed(uids[-max_messages:]))
        items: list[MailItem] = []
        for uid in selected:
            item = self._fetch_one(uid.decode("utf-8"))
            if item:
                items.append(item)
        return items

    def _fetch_one(self, uid: str) -> MailItem | None:
        assert self._client is not None
        status, data = self._client.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            return None

        raw_bytes = None
        for chunk in data:
            if isinstance(chunk, tuple):
                raw_bytes = chunk[1]
                break
        if raw_bytes is None:
            return None

        msg = email.message_from_bytes(raw_bytes)
        from_name, from_email, raw_from = _decode_from(msg.get("From", ""))
        subject = _decode_value(msg.get("Subject", ""))
        message_id = (msg.get("Message-ID") or f"uid:{uid}").strip()
        date = _parse_date(msg.get("Date"))
        body_text = _extract_body_text(msg)
        return MailItem(
            uid=uid,
            message_id=message_id,
            date=date,
            from_name=from_name,
            from_email=from_email,
            subject=subject,
            body_text=body_text,
            raw_from=raw_from,
        )


def _decode_value(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _decode_from(value: str) -> tuple[str, str, str]:
    decoded = _decode_value(value)
    name, email_address = parseaddr(decoded)
    return name.strip(), email_address.strip().lower(), decoded


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _extract_body_text(msg: Message) -> str:
    text_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disposition:
                continue
            payload = _decode_part(part)
            if not payload:
                continue
            if content_type == "text/plain":
                text_parts.append(payload)
            elif content_type == "text/html":
                html_parts.append(payload)
    else:
        payload = _decode_part(msg)
        if msg.get_content_type() == "text/html":
            html_parts.append(payload)
        else:
            text_parts.append(payload)

    text = "\n".join(p for p in text_parts if p).strip()
    if text:
        return text
    return "\n".join(html_to_text(p) for p in html_parts if p).strip()


def _decode_part(part: Message) -> str:
    try:
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            if isinstance(raw, str):
                return raw
            return ""
        return payload.decode(charset, errors="replace")
    except Exception:
        try:
            payload = part.get_payload(decode=True)
            return payload.decode("utf-8", errors="replace") if payload else ""
        except Exception:
            return ""
