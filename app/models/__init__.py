from app.models.appointment import Appointment, AppointmentReschedule, AppointmentSlot
from app.models.customer import Customer
from app.models.device import Device
from app.models.handover import Handover, HandoverCreate
from app.models.ticket import Ticket, TicketCreate

__all__ = [
    "Appointment",
    "AppointmentReschedule",
    "AppointmentSlot",
    "Customer",
    "Device",
    "Handover",
    "HandoverCreate",
    "Ticket",
    "TicketCreate",
]

