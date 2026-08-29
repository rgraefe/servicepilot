from datetime import date, datetime, timezone
from typing import Any

import pytest

import app.repositories.firestore as firestore_module
from app.models import Appointment, AppointmentSlot, Customer, Ticket
from app.models.appointment import AppointmentStatus
from app.models.ticket import TicketPriority, TicketStatus
from app.repositories.firestore import (
    FirestoreAppointmentRepository,
    FirestoreCustomerRepository,
    FirestoreTicketRepository,
)


class FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class FakeDocument:
    def __init__(self, documents: dict[str, dict[str, Any]], document_id: str) -> None:
        self._documents = documents
        self.document_id = document_id

    async def get(self, transaction: Any = None) -> FakeSnapshot:
        return FakeSnapshot(self._documents.get(self.document_id))

    async def create(self, data: dict[str, Any]) -> None:
        if self.document_id in self._documents:
            raise RuntimeError("already exists")
        self._documents[self.document_id] = data


class FakeQuery:
    def __init__(self, documents: dict[str, dict[str, Any]], field: str, value: Any) -> None:
        self._documents = documents
        self._field = field
        self._value = value

    async def stream(self):
        for data in self._documents.values():
            if data.get(self._field) == self._value:
                yield FakeSnapshot(data)


class FakeCollection:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self._documents = documents

    def document(self, document_id: str) -> FakeDocument:
        return FakeDocument(self._documents, document_id)

    def where(self, *, filter: Any) -> FakeQuery:
        return FakeQuery(self._documents, filter.field_path, filter.value)


class FakeTransaction:
    def __init__(self) -> None:
        self.updates: list[tuple[FakeDocument, dict[str, Any]]] = []

    def update(self, reference: FakeDocument, changes: dict[str, Any]) -> None:
        reference._documents[reference.document_id].update(changes)
        self.updates.append((reference, changes))


class FakeClient:
    def __init__(self, collections: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._collections = collections
        self.last_transaction: FakeTransaction | None = None

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._collections.setdefault(name, {}))

    def transaction(self) -> FakeTransaction:
        self.last_transaction = FakeTransaction()
        return self.last_transaction


@pytest.mark.asyncio
async def test_firestore_customer_repository_deserializes_document() -> None:
    client = FakeClient(
        {
            "customers": {
                "C-10023": {
                    "customer_id": "C-10023",
                    "name": "Max Mustermann",
                    "postal_code": "80331",
                }
            }
        }
    )
    repository = FirestoreCustomerRepository(client)  # type: ignore[arg-type]
    assert await repository.get("C-404") is None
    assert await repository.get("C-10023") == Customer(
        customer_id="C-10023", name="Max Mustermann", postal_code="80331"
    )


@pytest.mark.asyncio
async def test_firestore_ticket_repository_queries_and_returns_canonical_write() -> None:
    client = FakeClient({"tickets": {}})
    repository = FirestoreTicketRepository(client)  # type: ignore[arg-type]
    ticket = Ticket(
        ticket_id="T-9000",
        customer_id="C-10023",
        device_id="D-1007",
        problem_code="E99",
        description="Test fault",
        priority=TicketPriority.NORMAL,
        status=TicketStatus.CREATED,
    )
    assert await repository.add(ticket) == ticket
    assert await repository.find_active("C-10023", "D-1007", "e99") == ticket


@pytest.mark.asyncio
async def test_firestore_reschedule_is_transactional_and_releases_old_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    new_start = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
    appointment = Appointment(
        appointment_id="A-100",
        customer_id="C-100",
        device_id="D-100",
        status=AppointmentStatus.SCHEDULED,
        start=start,
        end=start.replace(hour=11),
        slot_id="S-100",
    )
    old_slot = AppointmentSlot(
        slot_id="S-100", start=start, end=start.replace(hour=11), available=False
    )
    new_slot = AppointmentSlot(
        slot_id="S-101",
        start=new_start,
        end=new_start.replace(hour=11),
        available=True,
    )
    client = FakeClient(
        {
            "appointments": {"A-100": appointment.model_dump(mode="python")},
            "appointment_slots": {
                "S-100": old_slot.model_dump(mode="python"),
                "S-101": new_slot.model_dump(mode="python"),
            },
        }
    )
    monkeypatch.setattr(
        firestore_module.firestore, "async_transactional", lambda function: function
    )
    repository = FirestoreAppointmentRepository(client)  # type: ignore[arg-type]

    updated = await repository.reschedule("A-100", "S-101")

    assert updated is not None
    assert updated.slot_id == "S-101"
    assert client._collections["appointment_slots"]["S-101"]["available"] is False
    assert client._collections["appointment_slots"]["S-100"]["available"] is True
    assert len(client.last_transaction.updates) == 3  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_firestore_available_slots_filters_date_range() -> None:
    inside = AppointmentSlot(
        slot_id="S-101",
        start=datetime(2026, 9, 2, 10, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, 11, tzinfo=timezone.utc),
    )
    outside = AppointmentSlot(
        slot_id="S-102",
        start=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
        end=datetime(2026, 10, 2, 11, tzinfo=timezone.utc),
    )
    client = FakeClient(
        {
            "appointment_slots": {
                "S-101": inside.model_dump(mode="python"),
                "S-102": outside.model_dump(mode="python"),
            }
        }
    )
    repository = FirestoreAppointmentRepository(client)  # type: ignore[arg-type]
    slots = await repository.list_available_slots(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert slots == [inside]
