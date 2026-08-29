from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_container
from app.container import ServiceContainer
from app.models import Appointment, AppointmentReschedule, AppointmentSlot

router = APIRouter(prefix="/appointments", tags=["appointments"])
Container = Annotated[ServiceContainer, Depends(get_container)]


@router.get("/available-slots", response_model=list[AppointmentSlot])
async def list_available_slots(
    customer_id: str,
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    container: Container,
) -> list[AppointmentSlot]:
    return await container.appointments.list_available_slots(
        customer_id, from_date, to_date
    )


@router.get("/{appointment_id}", response_model=Appointment)
async def get_appointment(appointment_id: str, container: Container) -> Appointment:
    return await container.appointments.get(appointment_id)


@router.put("/{appointment_id}", response_model=Appointment)
async def reschedule_appointment(
    appointment_id: str,
    request: AppointmentReschedule,
    container: Container,
) -> Appointment:
    return await container.appointments.reschedule(appointment_id, request)
