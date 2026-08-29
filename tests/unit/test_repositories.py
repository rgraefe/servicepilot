import asyncio
from datetime import datetime, timezone

import pytest

from app.models import Appointment, AppointmentSlot
from app.models.appointment import AppointmentStatus
from app.repositories import InMemoryAppointmentRepository


@pytest.mark.asyncio
async def test_slot_reservation_is_atomic() -> None:
    appointments = [
        Appointment(
            appointment_id=f"A-{number}",
            customer_id="C-100",
            device_id="D-100",
            status=AppointmentStatus.SCHEDULED,
            start=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
            slot_id=f"S-{number}",
        )
        for number in (100, 101)
    ]
    repository = InMemoryAppointmentRepository(
        appointments,
        [
            AppointmentSlot(
                slot_id=f"S-{number}",
                start=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
                available=False,
            )
            for number in (100, 101)
        ]
        + [
            AppointmentSlot(
                slot_id="S-200",
                start=datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
                end=datetime(2026, 1, 2, 11, tzinfo=timezone.utc),
            )
        ],
    )
    results = await asyncio.gather(
        repository.reschedule("A-100", "S-200"),
        repository.reschedule("A-101", "S-200"),
    )
    assert sum(result is not None for result in results) == 1
    released_slots = await repository.list_available_slots(
        datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
    )
    assert {slot.slot_id for slot in released_slots} in ({"S-100"}, {"S-101"})
