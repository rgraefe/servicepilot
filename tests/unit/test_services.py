from datetime import datetime, timezone

import pytest

from app.errors import ServiceError
from app.models import Appointment, AppointmentReschedule, AppointmentSlot, Customer
from app.models.appointment import AppointmentStatus
from app.repositories import (
    InMemoryAppointmentRepository,
    InMemoryCustomerRepository,
)
from app.services.appointment_service import AppointmentService


def build_service(status: AppointmentStatus = AppointmentStatus.SCHEDULED) -> AppointmentService:
    customers = InMemoryCustomerRepository(
        [Customer(customer_id="C-10023", name="Test", postal_code="80331")]
    )
    appointments = InMemoryAppointmentRepository(
        [
            Appointment(
                appointment_id="A-100",
                customer_id="C-10023",
                device_id="D-100",
                status=status,
                start=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
                slot_id="S-100",
            )
        ],
        [
            AppointmentSlot(
                slot_id="S-101",
                start=datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
                end=datetime(2026, 1, 2, 11, tzinfo=timezone.utc),
            )
        ],
    )
    return AppointmentService(customers, appointments)


@pytest.mark.asyncio
async def test_invalid_appointment_state_is_rejected() -> None:
    service = build_service(AppointmentStatus.COMPLETED)
    with pytest.raises(ServiceError) as captured:
        await service.reschedule(
            "A-100",
            AppointmentReschedule(
                customer_id="C-10023", slot_id="S-101", confirmed=True
            ),
        )
    assert captured.value.code == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_missing_appointment_is_rejected() -> None:
    service = build_service()
    with pytest.raises(ServiceError) as captured:
        await service.get("A-404")
    assert captured.value.code == "APPOINTMENT_NOT_FOUND"
