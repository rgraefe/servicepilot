from datetime import date
from typing import Any, TypeVar

from google.cloud import firestore_v1 as firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_document import AsyncDocumentReference
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel

from app.models import Appointment, AppointmentSlot, Customer, Device, Handover, Ticket
from app.models.ticket import TicketStatus
from app.seed_data import firestore_document

ModelT = TypeVar("ModelT", bound=BaseModel)


def _model_from_snapshot(model_type: type[ModelT], snapshot: Any) -> ModelT | None:
    if not snapshot.exists:
        return None
    return model_type.model_validate(snapshot.to_dict())


async def _models_from_query(model_type: type[ModelT], query: Any) -> list[ModelT]:
    return [model_type.model_validate(snapshot.to_dict()) async for snapshot in query.stream()]


class FirestoreCustomerRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._collection = client.collection("customers")

    async def get(self, customer_id: str) -> Customer | None:
        return _model_from_snapshot(
            Customer, await self._collection.document(customer_id).get()
        )


class FirestoreDeviceRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._collection = client.collection("devices")

    async def get(self, device_id: str) -> Device | None:
        return _model_from_snapshot(
            Device, await self._collection.document(device_id).get()
        )

    async def list_for_customer(self, customer_id: str) -> list[Device]:
        query = self._collection.where(
            filter=FieldFilter("customer_id", "==", customer_id)
        )
        return await _models_from_query(Device, query)


class FirestoreTicketRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._collection = client.collection("tickets")

    async def get(self, ticket_id: str) -> Ticket | None:
        return _model_from_snapshot(
            Ticket, await self._collection.document(ticket_id).get()
        )

    async def list_for_customer(self, customer_id: str) -> list[Ticket]:
        query = self._collection.where(
            filter=FieldFilter("customer_id", "==", customer_id)
        )
        return await _models_from_query(Ticket, query)

    async def find_active(
        self, customer_id: str, device_id: str, problem_code: str
    ) -> Ticket | None:
        # Querying only customer_id avoids requiring a composite index; the
        # remaining bounded customer result is filtered deterministically.
        tickets = await self.list_for_customer(customer_id)
        active = {
            TicketStatus.CREATED,
            TicketStatus.OPEN,
            TicketStatus.TECHNICIAN_ASSIGNED,
        }
        return next(
            (
                ticket
                for ticket in tickets
                if ticket.device_id == device_id
                and ticket.problem_code.casefold() == problem_code.casefold()
                and ticket.status in active
            ),
            None,
        )

    async def add(self, ticket: Ticket) -> Ticket:
        await self._collection.document(ticket.ticket_id).create(
            firestore_document(ticket)
        )
        snapshot = await self._collection.document(ticket.ticket_id).get()
        return _model_from_snapshot(Ticket, snapshot) or ticket


class FirestoreAppointmentRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self._appointments = client.collection("appointments")
        self._slots = client.collection("appointment_slots")

    async def get(self, appointment_id: str) -> Appointment | None:
        return _model_from_snapshot(
            Appointment, await self._appointments.document(appointment_id).get()
        )

    async def get_slot(self, slot_id: str) -> AppointmentSlot | None:
        return _model_from_snapshot(
            AppointmentSlot, await self._slots.document(slot_id).get()
        )

    async def list_for_customer(self, customer_id: str) -> list[Appointment]:
        query = self._appointments.where(
            filter=FieldFilter("customer_id", "==", customer_id)
        )
        return await _models_from_query(Appointment, query)

    async def list_available_slots(
        self, from_date: date, to_date: date
    ) -> list[AppointmentSlot]:
        query = self._slots.where(filter=FieldFilter("available", "==", True))
        slots = await _models_from_query(AppointmentSlot, query)
        return [slot for slot in slots if from_date <= slot.start.date() <= to_date]

    async def reschedule(
        self, appointment_id: str, slot_id: str
    ) -> Appointment | None:
        transaction = self._client.transaction()
        appointment_ref = self._appointments.document(appointment_id)
        slot_ref = self._slots.document(slot_id)

        @firestore.async_transactional
        async def reserve_slot(current_transaction: Any) -> Appointment | None:
            appointment_snapshot = await appointment_ref.get(
                transaction=current_transaction
            )
            slot_snapshot = await slot_ref.get(transaction=current_transaction)
            appointment = _model_from_snapshot(Appointment, appointment_snapshot)
            slot = _model_from_snapshot(AppointmentSlot, slot_snapshot)
            if appointment is None or slot is None or not slot.available:
                return None

            previous_slot_ref: AsyncDocumentReference | None = None
            previous_slot = None
            if appointment.slot_id != slot_id:
                previous_slot_ref = self._slots.document(appointment.slot_id)
                previous_snapshot = await previous_slot_ref.get(
                    transaction=current_transaction
                )
                previous_slot = _model_from_snapshot(
                    AppointmentSlot, previous_snapshot
                )

            current_transaction.update(slot_ref, {"available": False})
            current_transaction.update(
                appointment_ref,
                {"slot_id": slot.slot_id, "start": slot.start, "end": slot.end},
            )
            if previous_slot_ref is not None and previous_slot is not None:
                current_transaction.update(previous_slot_ref, {"available": True})
            return appointment.model_copy(
                update={"slot_id": slot.slot_id, "start": slot.start, "end": slot.end}
            )

        return await reserve_slot(transaction)


class FirestoreHandoverRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._collection = client.collection("handovers")

    async def get(self, handover_id: str) -> Handover | None:
        snapshot = await self._collection.document(handover_id).get()
        return _model_from_snapshot(Handover, snapshot)

    async def add(self, handover: Handover) -> Handover:
        await self._collection.document(handover.handover_id).create(
            firestore_document(handover)
        )
        snapshot = await self._collection.document(handover.handover_id).get()
        return _model_from_snapshot(Handover, snapshot) or handover
