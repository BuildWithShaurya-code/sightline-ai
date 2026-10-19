"""
SightLine AI - Telegram Notification Provider
Integrates with the official Telegram Bot API for verified security alert delivery.
Conforms strictly to server-only token security, error redaction, and HTML message escaping.
"""

import html
import logging
import re
from typing import Optional
import httpx

from .base import BaseNotificationProvider, NotificationPayload, ProviderResult

logger = logging.getLogger("sightline.notifications.telegram")


class TelegramProvider(BaseNotificationProvider):
    """
    Official Telegram Bot API notification adapter.
    Sends formatted security alerts to authorized test chat IDs.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        default_chat_id: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "telegram"

    def _redact_token(self, text: str) -> str:
        """Removes sensitive bot tokens from exception strings and log messages."""
        if not self.bot_token or not text:
            return text
        return text.replace(self.bot_token, "[REDACTED_BOT_TOKEN]")

    def compose_html_message(self, payload: NotificationPayload) -> str:
        """Composes secure HTML-formatted alert message with escaping."""
        inc_id = html.escape(payload.incident_id)
        status = html.escape(payload.review_status.upper())
        ts = html.escape(payload.timestamp)
        loc = f"{html.escape(payload.zone)} // {html.escape(payload.channel_name)}"
        threat_classes = ", ".join(c.upper() for c in payload.detected_classes) or "SUSPICIOUS ACTIVITY"
        escaped_threats = html.escape(threat_classes)
        peak_conf = int(payload.max_confidence * 100) if payload.max_confidence else 0

        msg = (
            "🚨 <b>[SIGHTLINE AI — SECURITY THREAT ALERT (TEST)]</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Incident Reference:</b> <code>#{inc_id}</code>\n"
            f"<b>Operator Status:</b> <b>{status}</b>\n"
            f"<b>Detection Time:</b> <code>{ts}</code>\n"
            f"<b>Monitored Node:</b> {loc}\n"
            f"<b>Threat Detections:</b> <b>{escaped_threats}</b> (Peak: {peak_conf}%)\n"
        )

        if payload.reviewer_notes:
            msg += f"<b>Reviewer Notes:</b> <i>{html.escape(payload.reviewer_notes)}</i>\n"

        msg += "\n⚠️ <i>Verified physical threat confirmed by human operator. (Test destination transmission only)</i>\n"

        if payload.incident_url:
            msg += f'🔗 <a href="{html.escape(payload.incident_url)}">Open Incident in Threat Vault</a>'

        return msg

    async def send_alert(
        self,
        payload: NotificationPayload,
        destination: str,
    ) -> ProviderResult:
        """
        Dispatches notification to authorized Telegram chat ID using sendMessage.
        """
        chat_id = destination or self.default_chat_id

        if not self.bot_token:
            return ProviderResult(
                accepted=False,
                status="failed",
                provider_name=self.name,
                error_message="Telegram Bot token is not configured on server.",
                failure_details="Missing TELEGRAM_BOT_TOKEN in server environment configuration.",
                retryable=False,
            )

        if not chat_id:
            return ProviderResult(
                accepted=False,
                status="failed",
                provider_name=self.name,
                error_message="No authorized destination chat ID configured for Telegram dispatch.",
                failure_details="Missing authorized chat_id in request or server TELEGRAM_CHAT_ID setting.",
                retryable=False,
            )

        message_text = self.compose_html_message(payload)
        endpoint_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        redacted_log_url = "https://api.telegram.org/bot[REDACTED_BOT_TOKEN]/sendMessage"

        logger.info(
            "[TELEGRAM NOTIFIER] Dispatching alert for Incident #%s to chat [%s] via %s",
            payload.incident_id,
            chat_id,
            redacted_log_url,
        )

        post_body = {
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint_url, json=post_body)

            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

            if response.status_code == 200 and data.get("ok"):
                message_id = str(data.get("result", {}).get("message_id", ""))
                logger.info(
                    "[TELEGRAM NOTIFIER] Message accepted by Telegram API! Message ID: %s",
                    message_id,
                )
                return ProviderResult(
                    accepted=True,
                    status="sent",
                    provider_name=self.name,
                    provider_reference=message_id,
                    is_simulated=False,
                    error_message=None,
                    failure_details=None,
                    retryable=False,
                )

            # Handle Provider Errors
            error_code = data.get("error_code", response.status_code)
            error_desc = self._redact_token(data.get("description", response.text))

            logger.warning(
                "[TELEGRAM NOTIFIER] Telegram API rejected dispatch: HTTP %d: %s",
                response.status_code,
                error_desc,
            )

            is_retryable = response.status_code in (429, 500, 502, 503, 504)

            return ProviderResult(
                accepted=False,
                status="failed",
                provider_name=self.name,
                provider_reference=None,
                is_simulated=False,
                error_message=f"Telegram API Error ({error_code}): {error_desc}",
                failure_details=error_desc,
                retryable=is_retryable,
            )

        except httpx.TimeoutException as exc:
            redacted_err = self._redact_token(str(exc))
            logger.error("[TELEGRAM NOTIFIER] Timeout connecting to Telegram: %s", redacted_err)
            return ProviderResult(
                accepted=False,
                status="uncertain",
                provider_name=self.name,
                error_message="Provider request timed out; external transmission outcome is uncertain.",
                failure_details="HTTP timeout before response acknowledged by provider.",
                retryable=False,
            )

        except httpx.ConnectError as exc:
            redacted_err = self._redact_token(str(exc))
            logger.error("[TELEGRAM NOTIFIER] Network connection error: %s", redacted_err)
            return ProviderResult(
                accepted=False,
                status="failed",
                provider_name=self.name,
                error_message=f"Network connection failed: {redacted_err}",
                failure_details="Could not establish connection to api.telegram.org.",
                retryable=True,
            )

        except Exception as exc:
            redacted_err = self._redact_token(str(exc))
            logger.error("[TELEGRAM NOTIFIER] Unexpected provider failure: %s", redacted_err)
            return ProviderResult(
                accepted=False,
                status="failed",
                provider_name=self.name,
                error_message=f"Unexpected error: {redacted_err}",
                failure_details=redacted_err,
                retryable=False,
            )
