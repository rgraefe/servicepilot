from dataclasses import dataclass

from google.cloud.firestore_v1.async_client import AsyncClient

from app.config import Settings, get_settings
from app.repositories import (
    FirestoreAppointmentRepository,
    FirestoreCustomerRepository,
    FirestoreDeviceRepository,
    FirestoreHandoverRepository,
    FirestoreTicketRepository,
    InMemoryAppointmentRepository,
    InMemoryCustomerRepository,
    InMemoryDeviceRepository,
    InMemoryHandoverRepository,
    InMemoryTicketRepository,
)
from app.repositories.interfaces import (
    AppointmentRepository,
    CustomerRepository,
    DeviceRepository,
    HandoverRepository,
    TicketRepository,
)
from app.seed_data import load_demo_data
from app.services.appointment_service import AppointmentService
from app.services.customer_service import CustomerService
from app.services.handover_service import HandoverService
from app.services.ticket_service import TicketService


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    customers: CustomerRepository
    devices: DeviceRepository
    tickets: TicketRepository
    appointments: AppointmentRepository
    handovers: HandoverRepository


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    customers: CustomerService
    tickets: TicketService
    appointments: AppointmentService
    handovers: HandoverService
    persistence_backend: str


def build_in_memory_repositories() -> RepositoryBundle:
    demo = load_demo_data()
    return RepositoryBundle(
        customers=InMemoryCustomerRepository(demo.customers),
        devices=InMemoryDeviceRepository(demo.devices),
        tickets=InMemoryTicketRepository(demo.tickets),
        appointments=InMemoryAppointmentRepository(
            demo.appointments, demo.appointment_slots
        ),
        handovers=InMemoryHandoverRepository(),
    )


def build_firestore_repositories(settings: Settings) -> RepositoryBundle:
    client = AsyncClient(
        project=settings.firestore_project,
        database=settings.firestore_database,
    )
    return RepositoryBundle(
        customers=FirestoreCustomerRepository(client),
        devices=FirestoreDeviceRepository(client),
        tickets=FirestoreTicketRepository(client),
        appointments=FirestoreAppointmentRepository(client),
        handovers=FirestoreHandoverRepository(client),
    )


def build_container(settings: Settings | None = None) -> ServiceContainer:
    resolved_settings = settings or get_settings()
    if resolved_settings.persistence_backend == "firestore":
        repositories = build_firestore_repositories(resolved_settings)
    else:
        repositories = build_in_memory_repositories()

    return ServiceContainer(
        customers=CustomerService(repositories.customers, repositories.devices),
        tickets=TicketService(
            repositories.customers, repositories.devices, repositories.tickets
        ),
        appointments=AppointmentService(
            repositories.customers, repositories.appointments
        ),
        handovers=HandoverService(
            repositories.customers, repositories.tickets, repositories.handovers
        ),
        persistence_backend=resolved_settings.persistence_backend,
    )
