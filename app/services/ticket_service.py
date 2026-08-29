from uuid import uuid4

from app.errors import ServiceError, not_found
from app.models import Ticket, TicketCreate
from app.repositories.interfaces import CustomerRepository, DeviceRepository, TicketRepository


class TicketService:
    def __init__(
        self,
        customers: CustomerRepository,
        devices: DeviceRepository,
        tickets: TicketRepository,
    ) -> None:
        self._customers = customers
        self._devices = devices
        self._tickets = tickets

    async def get(self, ticket_id: str) -> Ticket:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise not_found("ticket", ticket_id)
        return ticket

    async def list_for_customer(self, customer_id: str) -> list[Ticket]:
        if await self._customers.get(customer_id) is None:
            raise not_found("customer", customer_id)
        return await self._tickets.list_for_customer(customer_id)

    async def create(self, request: TicketCreate) -> Ticket:
        if await self._customers.get(request.customer_id) is None:
            raise not_found("customer", request.customer_id)
        device = await self._devices.get(request.device_id)
        if device is None:
            raise not_found("device", request.device_id)
        if device.customer_id != request.customer_id:
            raise ServiceError(
                "DEVICE_NOT_OWNED_BY_CUSTOMER",
                "The device does not belong to the supplied customer.",
                403,
            )
        duplicate = await self._tickets.find_active(
            request.customer_id, request.device_id, request.problem_code
        )
        if duplicate is not None:
            raise ServiceError(
                "DUPLICATE_ACTIVE_TICKET",
                f"Active ticket '{duplicate.ticket_id}' already covers this problem.",
                409,
            )
        ticket = Ticket(ticket_id=f"T-{uuid4().hex[:8].upper()}", **request.model_dump())
        return await self._tickets.add(ticket)
