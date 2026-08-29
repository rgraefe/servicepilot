from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import AppointmentSlot, TicketCreate


def test_slot_requires_increasing_timezone_aware_times() -> None:
    with pytest.raises(ValidationError):
        AppointmentSlot(
            slot_id="S-100",
            start=datetime(2026, 1, 1, 11, 0),
            end=datetime(2026, 1, 1, 10, 0),
        )
    valid = AppointmentSlot(
        slot_id="S-100",
        start=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
    )
    assert valid.available


def test_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TicketCreate(
            customer_id="C-10023",
            device_id="D-1007",
            problem_code="E37",
            description="Fault",
            secret="must not pass",
        )
