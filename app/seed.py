import argparse
import asyncio

from google.cloud.firestore_v1.async_client import AsyncClient

from app.config import get_settings
from app.seed_data import firestore_document, load_demo_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load the deterministic ServicePilot demo dataset into Firestore."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to perform Firestore writes.",
    )
    return parser.parse_args()


async def seed_firestore(confirm: bool) -> dict[str, int]:
    if not confirm:
        raise RuntimeError("Refusing to write without --confirm.")

    settings = get_settings()
    if settings.persistence_backend != "firestore":
        raise RuntimeError(
            "Set SERVICEPILOT_PERSISTENCE_BACKEND=firestore before seeding."
        )

    client = AsyncClient(
        project=settings.firestore_project,
        database=settings.firestore_database,
    )
    demo = load_demo_data()
    collections = {
        "customers": (demo.customers, "customer_id"),
        "devices": (demo.devices, "device_id"),
        "tickets": (demo.tickets, "ticket_id"),
        "appointments": (demo.appointments, "appointment_id"),
        "appointment_slots": (demo.appointment_slots, "slot_id"),
        "error_codes": (demo.error_codes, "error_code_id"),
    }

    batch = client.batch()
    counts: dict[str, int] = {}
    for collection_name, (models, identifier_field) in collections.items():
        counts[collection_name] = len(models)
        for model in models:
            document_id = str(getattr(model, identifier_field))
            reference = client.collection(collection_name).document(document_id)
            batch.set(reference, firestore_document(model))
    await batch.commit()
    return counts


def main() -> None:
    args = parse_args()
    counts = asyncio.run(seed_firestore(args.confirm))
    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    print(f"Firestore seed completed: {summary}")


if __name__ == "__main__":
    main()
