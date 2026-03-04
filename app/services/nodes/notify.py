"""Notification node (email/Slack/GHL stubs)."""
from __future__ import annotations

import logging
from typing import Any

from app.services.template import resolve_template as _resolve_template

logger = logging.getLogger(__name__)


class NotifyNode:
    """Sends notifications via various channels (stubs for now)."""

    node_type = "notify"

    SUPPORTED_CHANNELS = {"email", "slack", "ghl", "webhook", "log"}

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute a notification.

        Config keys:
            channel: "email" | "slack" | "ghl" | "webhook" | "log"
            message: message template with placeholders
            recipient: optional recipient (email address, Slack channel, etc.)
            subject: optional subject (for email)

        Returns dict with 'channel', 'message', 'sent' (bool), 'recipient'.
        """
        channel = config.get("channel", "log")
        message_template = config.get("message", "")
        message = _resolve_template(message_template, context)
        recipient = config.get("recipient", "")
        if recipient:
            recipient = _resolve_template(recipient, context)
        subject = config.get("subject", "Workflow Notification")
        if subject:
            subject = _resolve_template(subject, context)

        if channel not in self.SUPPORTED_CHANNELS:
            return {
                "channel": channel,
                "message": message,
                "sent": False,
                "error": f"Unsupported channel: {channel}",
            }

        # All channels are stubs -- log the notification
        logger.info(
            "Notification [%s] to=%s subject=%s: %s",
            channel,
            recipient,
            subject,
            message[:200],
        )

        return {
            "channel": channel,
            "message": message,
            "recipient": recipient,
            "subject": subject,
            "sent": True,
            "note": f"Stub: {channel} notification logged (not actually sent)",
        }
