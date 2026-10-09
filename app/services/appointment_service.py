from datetime import date

from app.errors import ServiceError, not_found
from app.models import Appointment, AppointmentReschedule, AppointmentSlot
from app.models.appointment import AppointmentStatus
from app.repositories.interfaces import AppointmentRepository, CustomerRepository


class AppointmentService:
    def __init__(
        self,
        customers: CustomerRepository,
        appointments: AppointmentRepository,
    ) -> None:
        self._customers = customers
        self._appointments = appointments

    async def get(self, appointment_id: str) -> Appointment:
        appointment = await self._appointments.get(appointment_id)
        if appointment is None:
            raise not_found("appointment", appointment_id)
        return appointment

    async def list_for_customer(self, customer_id: str) -> list[Appointment]:
        if await self._customers.get(customer_id) is None:
            raise not_found("customer", customer_id)
        return await self._appointments.list_for_customer(customer_id)

    async def get_slot(self, customer_id: str, slot_id: str) -> AppointmentSlot:
        if await self._customers.get(customer_id) is None:
            raise not_found("customer", customer_id)
        slot = await self._appointments.get_slot(slot_id)
        if slot is None:
            raise not_found("appointment_slot", slot_id)
        return slot

    async def list_available_slots(
        self, customer_id: str, from_date: date, to_date: date
    ) -> list[AppointmentSlot]:
        if await self._customers.get(customer_id) is None:
            raise not_found("customer", customer_id)
        if to_date < from_date:
            raise ServiceError("INVALID_DATE_RANGE", "to_date must not precede from_date.", 422)
        return await self._appointments.list_available_slots(from_date, to_date)

    async def reschedule(
        self, appointment_id: str, request: AppointmentReschedule
    ) -> Appointment:
        appointment = await self.get(appointment_id)
        if appointment.customer_id != request.customer_id:
            raise ServiceError(
                "APPOINTMENT_NOT_OWNED_BY_CUSTOMER",
                "The appointment does not belong to the supplied customer.",
                403,
            )
        if not request.confirmed:
            raise ServiceError(
                "CONFIRMATION_REQUIRED",
                "Explicit confirmation is required before rescheduling.",
                409,
            )
        if appointment.status != AppointmentStatus.SCHEDULED:
            raise ServiceError(
                "INVALID_STATE_TRANSITION",
                f"Appointment in state '{appointment.status}' cannot be rescheduled.",
                409,
            )
        updated = await self._appointments.reschedule(appointment_id, request.slot_id)
        if updated is None:
            raise ServiceError(
                "SLOT_UNAVAILABLE",
                "The requested appointment slot is unavailable.",
                409,
            )
        return updated
