from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container
from app.container import ServiceContainer
from app.models import Appointment, Customer, Device, Ticket

router = APIRouter(prefix="/customers", tags=["customers"])
Container = Annotated[ServiceContainer, Depends(get_container)]


@router.get("/{customer_id}", response_model=Customer)
async def get_customer(customer_id: str, container: Container) -> Customer:
    return await container.customers.get_customer(customer_id)


@router.get("/{customer_id}/devices", response_model=list[Device])
async def list_customer_devices(customer_id: str, container: Container) -> list[Device]:
    return await container.customers.list_devices(customer_id)


@router.get("/{customer_id}/tickets", response_model=list[Ticket])
async def list_customer_tickets(customer_id: str, container: Container) -> list[Ticket]:
    return await container.tickets.list_for_customer(customer_id)


@router.get("/{customer_id}/appointments", response_model=list[Appointment])
async def list_customer_appointments(
    customer_id: str, container: Container
) -> list[Appointment]:
    return await container.appointments.list_for_customer(customer_id)
