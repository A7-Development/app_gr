"""NotificationNode — dispatches/records a notification during the workflow.

MVP: persists a `PlaybookNotification` row + (future) integrates with email
provider. Right now `channel="log"` is the only one that actually does
anything (record + log). `channel="email"` records the intent but does not
send — wires up to SES/SMTP later.

Config schema (all template-resolvable):
    {
        "channel": "log" | "email",
        "to": "{{trigger.analyst_email}}",      # optional, recipient
        "subject": "Dossie #{{trigger.dossier_id}} aguardando revisao",
        "body": "Mensagem com {{node.opinion.output.recommendation}}"
    }

Output:
    {"notification_id": "...", "delivered": bool, "channel": "..."}
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.workflow.models.notification import PlaybookNotification
from app.shared.workflow.nodes._base import BaseNode, NodeContext, NodeOutput

logger = logging.getLogger(__name__)

_VALID_CHANNELS = {"log", "email"}


class NotificationNode(BaseNode):
    """Dispatches a notification. MVP supports `log` (recorded only)."""

    type = "notification"

    def validate_config(self) -> None:
        channel = (self.config.get("channel") or "log").lower()
        if channel not in _VALID_CHANNELS:
            raise ValueError(
                f"notification: invalid channel '{channel}'. "
                f"Use one of {sorted(_VALID_CHANNELS)}."
            )
        if not self.config.get("body"):
            raise ValueError("notification: `config.body` is required.")

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        channel = (self.config.get("channel") or "log").lower()
        notif = PlaybookNotification(
            id=uuid4(),
            tenant_id=ctx.tenant_id,
            run_id=ctx.run_id,
            node_id=ctx.node_id,
            channel=channel,
            recipient=self.config.get("to"),
            subject=self.config.get("subject"),
            body=str(self.config["body"]),
            delivered=(channel == "log"),  # log channel is always "delivered"
        )
        db.add(notif)
        await db.flush()

        if channel == "log":
            logger.info(
                "Workflow notification (run=%s node=%s subject=%r): %s",
                ctx.run_id,
                ctx.node_id,
                notif.subject,
                notif.body[:200],
            )

        return NodeOutput(
            data={
                "notification_id": str(notif.id),
                "delivered": notif.delivered,
                "channel": channel,
            },
            status_hint=f"{channel}: {notif.subject or 'enviada'}",
        )
