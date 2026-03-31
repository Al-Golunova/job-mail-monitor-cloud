from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import timezone

from dotenv import load_dotenv

from .classifier import classify_email
from .config import load_settings
from .imap_client import GMXImapClient, MailItem
from .sheets_client import SheetsClient
from .telegram_notifier import TelegramNotifier
from .utils import clip


STATUS_MAP = {
    "offer": "Offer",
    "interview": "Interview",
    "documents": "Documents requested",
    "rejection": "Rejected",
    "reply": "Reply received",
    "auto_reply": "Auto reply",
    "other": "Email received",
}


@dataclass
class RunStats:
    fetched: int = 0
    skipped_as_processed: int = 0
    matched: int = 0
    unmatched: int = 0
    telegram_sent: int = 0


def build_telegram_message(mail: MailItem, category: str, company: str, title: str) -> str:
    lines = [
        "📬 New employer email",
        f"Type: {STATUS_MAP.get(category, category)}",
    ]
    if company:
        lines.append(f"Company: {company}")
    if title:
        lines.append(f"Position: {title}")
    lines.append(f"From: {mail.from_name or mail.from_email}")
    lines.append(f"Subject: {clip(mail.subject, 180)}")
    lines.append(f"Date: {mail.date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)


def process_once(test_telegram: bool = False) -> RunStats:
    load_dotenv()
    settings = load_settings()
    notifier = TelegramNotifier(settings)

    if test_telegram:
        notifier.send("✅ Test message from job-mail-monitor")
        print("Telegram test sent.")
        return RunStats()

    sheets = SheetsClient(settings)
    processed_ids = sheets.get_processed_message_ids()
    jobs, header_map = sheets.get_jobs()
    stats = RunStats()

    with GMXImapClient(settings) as imap_client:
        messages = imap_client.fetch_recent_messages(settings.scan_days, settings.max_messages_per_run)

    stats.fetched = len(messages)

    for mail in messages:
        if mail.message_id in processed_ids or mail.uid in processed_ids:
            stats.skipped_as_processed += 1
            continue

        classification = classify_email(mail)
        match = sheets.find_best_match(
            jobs=jobs,
            header_map=header_map,
            subject=mail.subject,
            body=mail.body_text,
            from_email=mail.from_email,
        )

        action = "logged_only"
        telegram_sent = "No"
        email_date = mail.date.astimezone(timezone.utc).isoformat()
        status = STATUS_MAP.get(classification.category, "Email received")

        if match:
            stats.matched += 1
            action = "row_updated"
            note = f"Auto-updated from email ({classification.category}, rule={classification.reason})"
            if not settings.dry_run:
                sheets.update_job_row(
                    row_number=match.row_number,
                    header_map=header_map,
                    status=status,
                    email_date=email_date,
                    email_from=mail.from_email,
                    email_subject=mail.subject,
                    email_category=classification.category,
                    message_id=mail.message_id,
                    score=match.score,
                    note=note,
                    telegram_sent="No",
                )

            if classification.category in settings.notify_on and settings.telegram_enabled:
                message = build_telegram_message(mail, classification.category, match.company, match.title)
                if not settings.dry_run:
                    notifier.send(message)
                telegram_sent = "Yes"
                stats.telegram_sent += 1
                if not settings.dry_run:
                    sheets.update_job_row(
                        row_number=match.row_number,
                        header_map=header_map,
                        status=status,
                        email_date=email_date,
                        email_from=mail.from_email,
                        email_subject=mail.subject,
                        email_category=classification.category,
                        message_id=mail.message_id,
                        score=match.score,
                        note=note,
                        telegram_sent="Yes",
                    )
        else:
            stats.unmatched += 1
            action = "unmatched_logged"
            if classification.category in settings.notify_on and settings.telegram_enabled:
                message = build_telegram_message(mail, classification.category, "", "") + "\n⚠️ No row matched in Google Sheets"
                if not settings.dry_run:
                    notifier.send(message)
                telegram_sent = "Yes"
                stats.telegram_sent += 1

        if not settings.dry_run:
            sheets.append_event(
                message_id=mail.message_id,
                uid=mail.uid,
                email_date=email_date,
                from_email=mail.from_email,
                from_name=mail.from_name,
                subject=mail.subject,
                category=classification.category,
                matched_row=str(match.row_number) if match else "",
                company=match.company if match else "",
                title=match.title if match else "",
                score=str(match.score) if match else "",
                action=action,
            )
        processed_ids.add(mail.message_id)
        processed_ids.add(mail.uid)

    print(
        f"Fetched={stats.fetched}, skipped={stats.skipped_as_processed}, matched={stats.matched}, "
        f"unmatched={stats.unmatched}, telegram={stats.telegram_sent}"
    )
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor GMX mailbox and update Google Sheets")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test Telegram message and exit")
    args = parser.parse_args()
    process_once(test_telegram=args.test_telegram)
