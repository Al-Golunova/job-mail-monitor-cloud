if match:
    telegram_sent = "No"

    if classification.category in settings.notify_on and settings.telegram_enabled:
        message = build_telegram_message(mail, classification.category, match.company, match.title)
        if not settings.dry_run:
            notifier.send(message)
        telegram_sent = "Yes"
        stats.telegram_sent += 1

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
            telegram_sent=telegram_sent,
        )
