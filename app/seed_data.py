import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.models import Appointment, AppointmentSlot, Customer, Device, Ticket


class ErrorCode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    error_code_id: str
    model: str
    code: str
    summary: str
    customer_action: str


class DemoData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customers: list[Customer]
    devices: list[Device]
    tickets: list[Ticket]
    appointments: list[Appointment]
    appointment_slots: list[AppointmentSlot]
    error_codes: list[ErrorCode]


SOURCE_SEED_PATH = Path.cwd() / "data" / "seed" / "demo.json"
INSTALLED_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "seed" / "demo.json"
)
DEFAULT_SEED_PATH = (
    SOURCE_SEED_PATH if SOURCE_SEED_PATH.exists() else INSTALLED_SEED_PATH
)


def load_demo_data(path: Path = DEFAULT_SEED_PATH) -> DemoData:
    return DemoData.model_validate_json(path.read_text(encoding="utf-8"))


def firestore_document(model: BaseModel) -> dict[str, object]:
    # Python mode preserves datetime objects for Firestore timestamp fields.
    return model.model_dump(mode="python")
