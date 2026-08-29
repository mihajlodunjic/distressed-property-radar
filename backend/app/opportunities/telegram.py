from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings
from app.db.models import Alert


@dataclass(frozen=True)
class TelegramDeliveryResult:
    provider_message_id: str | None = None
    provider_response: dict[str, object] | None = None


class TelegramDeliveryError(RuntimeError):
    """Raised when Telegram delivery fails."""


class TelegramSender(Protocol):
    def send_alert(self, alert: Alert) -> TelegramDeliveryResult: ...


class HttpTelegramSender:
    def __init__(
        self,
        *,
        bot_token: str | None,
        chat_id: str | None,
        api_base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpTelegramSender:
        return cls(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            api_base_url=settings.telegram_api_base_url,
        )

    def send_alert(self, alert: Alert) -> TelegramDeliveryResult:
        if not self._bot_token or not self._chat_id:
            raise TelegramDeliveryError("telegram credentials are not configured")

        response_json = self._send_message(message_text_from_alert(alert))
        result = response_json.get("result")
        provider_message_id = None
        if isinstance(result, dict) and result.get("message_id") is not None:
            provider_message_id = str(result["message_id"])
        return TelegramDeliveryResult(
            provider_message_id=provider_message_id,
            provider_response=response_json,
        )

    def _send_message(self, text: str) -> dict[str, object]:
        url = f"{self._api_base_url}/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout_seconds)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError("telegram request failed") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError("telegram response was not valid json") from exc

        if response.status_code >= 400:
            raise TelegramDeliveryError(f"telegram http status {response.status_code}")
        if response_json.get("ok") is not True:
            description = response_json.get("description")
            if isinstance(description, str) and description:
                raise TelegramDeliveryError(f"telegram rejected message: {description}")
            raise TelegramDeliveryError("telegram rejected message")
        return response_json


def message_text_from_alert(alert: Alert) -> str:
    text = alert.payload_json.get("message_text")
    if not isinstance(text, str) or not text.strip():
        raise TelegramDeliveryError("alert payload is missing message_text")
    return text
