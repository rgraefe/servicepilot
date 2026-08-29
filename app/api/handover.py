from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_container
from app.container import ServiceContainer
from app.models import Handover, HandoverCreate

router = APIRouter(prefix="/handover", tags=["handover"])
Container = Annotated[ServiceContainer, Depends(get_container)]


@router.post("", response_model=Handover, status_code=status.HTTP_201_CREATED)
async def create_handover(request: HandoverCreate, container: Container) -> Handover:
    return await container.handovers.create(request)
