from __future__ import annotations

import requests

from .config import Settings


class TelegramNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, message: str) -> None:
        if not self.settings.telegram_enabled:
            return
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": self.settings.telegram_chat_id,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        response.raise_for_status()
