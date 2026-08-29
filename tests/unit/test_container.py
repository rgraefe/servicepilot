from app.config import Settings
from app.container import build_container
from app.repositories.firestore import FirestoreCustomerRepository


class FakeFirestoreClient:
    def __init__(self, **_: object) -> None:
        pass

    def collection(self, name: str) -> tuple[str]:
        return (name,)


def test_default_container_uses_seeded_in_memory_repositories() -> None:
    container = build_container(Settings())
    assert container.persistence_backend == "memory"
    assert container.customers._customers.__class__.__name__.startswith("InMemory")


def test_firestore_container_keeps_service_layer_unchanged(monkeypatch) -> None:
    monkeypatch.setattr("app.container.AsyncClient", FakeFirestoreClient)
    container = build_container(
        Settings(persistence_backend="firestore", firestore_project="demo-project")
    )
    assert container.persistence_backend == "firestore"
    assert isinstance(container.customers._customers, FirestoreCustomerRepository)
