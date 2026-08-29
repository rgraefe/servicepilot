from uuid import uuid4

from app.errors import ServiceError, not_found
from app.models import Handover, HandoverCreate
from app.repositories.interfaces import CustomerRepository, HandoverRepository, TicketRepository


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
        if await self._customers.get(request.customer_id) is None:
            raise not_found("customer", request.customer_id)
        if request.ticket_id is not None:
            ticket = await self._tickets.get(request.ticket_id)
            if ticket is None:
                raise not_found("ticket", request.ticket_id)
            if ticket.customer_id != request.customer_id:
                raise ServiceError(
                    "TICKET_NOT_OWNED_BY_CUSTOMER",
                    "The ticket does not belong to the supplied customer.",
                    403,
                )
        handover = Handover(
            handover_id=f"H-{uuid4().hex[:8].upper()}",
            **request.model_dump(),
        )
        return await self._handovers.add(handover)
