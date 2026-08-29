import asyncio
from datetime import date

from app.models import Appointment, AppointmentSlot, Customer, Device, Handover, Ticket
from app.models.ticket import TicketStatus


class InMemoryCustomerRepository:
    def __init__(self, customers: list[Customer] | None = None) -> None:
        self._items = {item.customer_id: item for item in customers or []}

    async def get(self, customer_id: str) -> Customer | None:
        return self._items.get(customer_id)


class InMemoryDeviceRepository:
    def __init__(self, devices: list[Device] | None = None) -> None:
        self._items = {item.device_id: item for item in devices or []}

    async def get(self, device_id: str) -> Device | None:
        return self._items.get(device_id)

    async def list_for_customer(self, customer_id: str) -> list[Device]:
        return [item for item in self._items.values() if item.customer_id == customer_id]


class InMemoryTicketRepository:
    def __init__(self, tickets: list[Ticket] | None = None) -> None:
        self._items = {item.ticket_id: item for item in tickets or []}
        self._lock = asyncio.Lock()

    async def get(self, ticket_id: str) -> Ticket | None:
        return self._items.get(ticket_id)

    async def list_for_customer(self, customer_id: str) -> list[Ticket]:
        return [item for item in self._items.values() if item.customer_id == customer_id]

    async def find_active(self, customer_id: str, device_id: str, problem_code: str) -> Ticket | None:
        active = {TicketStatus.CREATED, TicketStatus.OPEN, TicketStatus.TECHNICIAN_ASSIGNED}
        return next(
            (
                item
                for item in self._items.values()
                if item.customer_id == customer_id
                and item.device_id == device_id
                and item.problem_code.casefold() == problem_code.casefold()
                and item.status in active
            ),
            None,
        )

    async def add(self, ticket: Ticket) -> Ticket:
        async with self._lock:
            self._items[ticket.ticket_id] = ticket
        return ticket


class InMemoryAppointmentRepository:
    def __init__(
        self,
        appointments: list[Appointment] | None = None,
        slots: list[AppointmentSlot] | None = None,
    ) -> None:
        self._items = {item.appointment_id: item for item in appointments or []}
        self._slots = {item.slot_id: item for item in slots or []}
        self._lock = asyncio.Lock()

    async def get(self, appointment_id: str) -> Appointment | None:
        return self._items.get(appointment_id)

    async def list_for_customer(self, customer_id: str) -> list[Appointment]:
        return [item for item in self._items.values() if item.customer_id == customer_id]

    async def list_available_slots(self, from_date: date, to_date: date) -> list[AppointmentSlot]:
        return [
            slot
            for slot in self._slots.values()
            if slot.available and from_date <= slot.start.date() <= to_date
        ]

    async def reschedule(self, appointment_id: str, slot_id: str) -> Appointment | None:
        async with self._lock:
            appointment = self._items.get(appointment_id)
            slot = self._slots.get(slot_id)
            if appointment is None or slot is None or not slot.available:
                return None
            previous_slot = self._slots.get(appointment.slot_id)
            updated = appointment.model_copy(
                update={"slot_id": slot.slot_id, "start": slot.start, "end": slot.end}
            )
            self._items[appointment_id] = updated
            self._slots[slot_id] = slot.model_copy(update={"available": False})
            if previous_slot is not None and appointment.slot_id != slot_id:
                self._slots[appointment.slot_id] = previous_slot.model_copy(
                    update={"available": True}
                )
            return updated


class InMemoryHandoverRepository:
    def __init__(self, handovers: list[Handover] | None = None) -> None:
        self._items = {item.handover_id: item for item in handovers or []}
        self._lock = asyncio.Lock()

    async def add(self, handover: Handover) -> Handover:
        async with self._lock:
            self._items[handover.handover_id] = handover
        return handover
