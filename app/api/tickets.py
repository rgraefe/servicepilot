from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_container
from app.container import ServiceContainer
from app.models import Ticket, TicketCreate

router = APIRouter(prefix="/tickets", tags=["tickets"])
Container = Annotated[ServiceContainer, Depends(get_container)]


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket(ticket_id: str, container: Container) -> Ticket:
    return await container.tickets.get(ticket_id)


@router.post("", response_model=Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(request: TicketCreate, container: Container) -> Ticket:
    return await container.tickets.create(request)
