from enum import StrEnum

from pydantic import AliasChoices, Field

from app.models.common import ApiModel, Identifier, NonEmptyText


class HandoverReason(StrEnum):
    HUMAN_REQUEST = "human_request"
    TECHNICAL_ESCALATION = "technical_escalation"
    COMPLAINT = "complaint"
    REPEATED_FAILURE = "repeated_failure"


class HandoverStatus(StrEnum):
    QUEUED = "queued"


class HandoverPriority(StrEnum):
    NORMAL = "normal"
    HIGH = "high"


class HandoverContext(ApiModel):
    device_id: Identifier | None = None
    device_model: NonEmptyText | None = None
    error_code: NonEmptyText | None = None
    appointment_id: Identifier | None = None
    last_tool: NonEmptyText | None = None
    failure_count: int | None = Field(default=None, ge=1, le=10)


class HandoverCreate(ApiModel):
    handover_request_id: Identifier | None = None
    customer_id: Identifier | None = None
    reason: HandoverReason
    conversation_summary: NonEmptyText = Field(
        validation_alias=AliasChoices("conversation_summary", "summary")
    )
    ticket_id: Identifier | None = None
    context: HandoverContext = Field(default_factory=HandoverContext)


class Handover(HandoverCreate):
    handover_id: Identifier
    status: HandoverStatus = HandoverStatus.QUEUED
    priority: HandoverPriority
