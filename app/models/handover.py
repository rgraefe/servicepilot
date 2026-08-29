from enum import StrEnum

from app.models.common import ApiModel, Identifier, NonEmptyText


class HandoverReason(StrEnum):
    HUMAN_REQUEST = "human_request"
    TECHNICAL_ESCALATION = "technical_escalation"
    COMPLAINT = "complaint"
    REPEATED_FAILURE = "repeated_failure"


class HandoverStatus(StrEnum):
    QUEUED = "queued"


class HandoverCreate(ApiModel):
    customer_id: Identifier
    reason: HandoverReason
    summary: NonEmptyText
    ticket_id: Identifier | None = None


class Handover(HandoverCreate):
    handover_id: Identifier
    status: HandoverStatus = HandoverStatus.QUEUED
