from app.repositories.in_memory import (
    InMemoryAppointmentRepository,
    InMemoryCustomerRepository,
    InMemoryDeviceRepository,
    InMemoryHandoverRepository,
    InMemoryTicketRepository,
)
from app.repositories.firestore import (
    FirestoreAppointmentRepository,
    FirestoreCustomerRepository,
    FirestoreDeviceRepository,
    FirestoreHandoverRepository,
    FirestoreTicketRepository,
)

__all__ = [
    "InMemoryAppointmentRepository",
    "InMemoryCustomerRepository",
    "InMemoryDeviceRepository",
    "InMemoryHandoverRepository",
    "InMemoryTicketRepository",
    "FirestoreAppointmentRepository",
    "FirestoreCustomerRepository",
    "FirestoreDeviceRepository",
    "FirestoreHandoverRepository",
    "FirestoreTicketRepository",
]
