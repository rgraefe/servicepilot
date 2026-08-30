from hashlib import sha256
from uuid import uuid4

from app.errors import ServiceError, not_found
from app.models import Handover, HandoverCreate
from app.models.handover import HandoverPriority, HandoverReason
from app.repositories.interfaces import (
    CustomerRepository,
    HandoverRepository,
    TicketRepository,
)


class HandoverService:
    def __init__(
        self,
        customers: CustomerRepository,
        tickets: TicketRepository,
        handovers: HandoverRepository,
    ) -> None:
        self._customers = customers
        self._tickets = tickets
        self._handovers = handovers

    async def create(self, request: HandoverCreate) -> Handover:
        if (
            request.customer_id is not None
            and await self._customers.get(request.customer_id) is None
        ):
            raise not_found("customer", request.customer_id)
        if request.ticket_id is not None:
            ticket = await self._tickets.get(request.ticket_id)
            if ticket is None:
                raise not_found("ticket", request.ticket_id)
            if (
                request.customer_id is not None
                and ticket.customer_id != request.customer_id
            ):
                raise ServiceError(
                    "TICKET_NOT_OWNED_BY_CUSTOMER",
                    "The ticket does not belong to the supplied customer.",
                    403,
                )
        handover_id = self._handover_id(request.handover_request_id)
        priority = self._priority(request.reason)
        handover = Handover(
            handover_id=handover_id,
            priority=priority,
            **request.model_dump(),
        )
        existing = await self._handovers.get(handover_id)
        if existing is not None:
            if existing == handover:
                return existing
            raise ServiceError(
                "HANDOVER_REQUEST_CONFLICT",
                "The handover request ID was already used for different content.",
                409,
            )
        return await self._handovers.add(handover)

    @staticmethod
    def _handover_id(request_id: str | None) -> str:
        if request_id is None:
            return f"H-{uuid4().hex[:12].upper()}"
        digest = sha256(request_id.encode("utf-8")).hexdigest()[:12].upper()
        return f"H-{digest}"

    @staticmethod
    def _priority(reason: HandoverReason) -> HandoverPriority:
        if reason in {
            HandoverReason.TECHNICAL_ESCALATION,
            HandoverReason.COMPLAINT,
        }:
            return HandoverPriority.HIGH
        return HandoverPriority.NORMAL
