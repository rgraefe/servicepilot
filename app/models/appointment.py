from datetime import datetime
from enum import StrEnum

from pydantic import model_validator

from app.models.common import ApiModel, Identifier


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AppointmentSlot(ApiModel):
    slot_id: Identifier
    start: datetime
    end: datetime
    available: bool = True

    @model_validator(mode="after")
    def validate_times(self) -> "AppointmentSlot":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("slot timestamps must include a timezone")
        return self


class Appointment(ApiModel):
    appointment_id: Identifier
    customer_id: Identifier
    device_id: Identifier
    status: AppointmentStatus
    start: datetime
    end: datetime
    slot_id: Identifier


class AppointmentReschedule(ApiModel):
    customer_id: Identifier
    slot_id: Identifier
    confirmed: bool
