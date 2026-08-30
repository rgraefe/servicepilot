import pytest

from app.errors import ServiceError
from app.models import Customer, HandoverCreate, Ticket
from app.models.handover import HandoverContext, HandoverReason
from app.models.ticket import TicketPriority, TicketStatus
from app.repositories import (
    InMemoryCustomerRepository,
    InMemoryHandoverRepository,
    InMemoryTicketRepository,
)
from app.services.handover_service import HandoverService


def build_service() -> HandoverService:
    return HandoverService(
        InMemoryCustomerRepository(
            [
                Customer(customer_id="C-10023", name="Test", postal_code="80331"),
                Customer(customer_id="C-99999", name="Other", postal_code="10115"),
            ]
        ),
        InMemoryTicketRepository(
            [
                Ticket(
                    ticket_id="T-4711",
                    customer_id="C-10023",
                    device_id="D-1007",
                    problem_code="E37",
                    description="Recurring fault.",
                    priority=TicketPriority.NORMAL,
                    status=TicketStatus.OPEN,
                )
            ]
        ),
        InMemoryHandoverRepository(),
    )


@pytest.mark.asyncio
async def test_human_request_does_not_require_identity() -> None:
    handover = await build_service().create(
        HandoverCreate(
            handover_request_id="HO-UNIT-HUMAN-001",
            reason=HandoverReason.HUMAN_REQUEST,
            conversation_summary="Customer asks for a human.",
        )
    )
    assert handover.customer_id is None
    assert handover.status == "queued"
    assert handover.priority == "normal"


@pytest.mark.asyncio
async def test_technical_escalation_has_deterministic_high_priority() -> None:
    handover = await build_service().create(
        HandoverCreate(
            reason=HandoverReason.TECHNICAL_ESCALATION,
            conversation_summary="Recurring E37 requires review.",
            context=HandoverContext(device_model="HeatPump-X200", error_code="E37"),
        )
    )
    assert handover.priority == "high"


@pytest.mark.asyncio
async def test_unknown_customer_is_rejected_when_supplied() -> None:
    with pytest.raises(ServiceError) as captured:
        await build_service().create(
            HandoverCreate(
                customer_id="C-404",
                reason=HandoverReason.COMPLAINT,
                conversation_summary="Complaint needs review.",
            )
        )
    assert captured.value.code == "CUSTOMER_NOT_FOUND"


@pytest.mark.asyncio
async def test_ticket_ownership_is_validated() -> None:
    with pytest.raises(ServiceError) as captured:
        await build_service().create(
            HandoverCreate(
                customer_id="C-99999",
                ticket_id="T-4711",
                reason=HandoverReason.REPEATED_FAILURE,
                conversation_summary="Ticket lookup failed twice.",
            )
        )
    assert captured.value.code == "TICKET_NOT_OWNED_BY_CUSTOMER"


@pytest.mark.asyncio
async def test_stable_request_id_is_idempotent_and_conflict_safe() -> None:
    service = build_service()
    request = HandoverCreate(
        handover_request_id="HO-UNIT-IDEMPOTENT-001",
        reason=HandoverReason.REPEATED_FAILURE,
        conversation_summary="Backend failed twice.",
        context=HandoverContext(last_tool="get_ticket", failure_count=2),
    )
    first = await service.create(request)
    retry = await service.create(request)
    assert retry == first

    with pytest.raises(ServiceError) as captured:
        await service.create(
            request.model_copy(update={"conversation_summary": "Changed summary."})
        )
    assert captured.value.code == "HANDOVER_REQUEST_CONFLICT"
