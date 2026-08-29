from enum import StrEnum

from pydantic import Field

from app.models.common import ApiModel, Identifier, NonEmptyText


class TicketStatus(StrEnum):
    CREATED = "created"
    OPEN = "open"
    TECHNICIAN_ASSIGNED = "technician_assigned"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketCreate(ApiModel):
    customer_id: Identifier
    device_id: Identifier
    problem_code: str = Field(min_length=1, max_length=32)
    description: NonEmptyText
    priority: TicketPriority = TicketPriority.NORMAL


class Ticket(TicketCreate):
    ticket_id: Identifier
    status: TicketStatus = TicketStatus.CREATED
