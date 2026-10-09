import json
from pathlib import Path

from app.main import create_app


TOOL_SCHEMA_PATH = Path("conversation/servicepilot-openapi.json")
EXPECTED_OPERATIONS = {
    "get_customer": ("/customers/{customer_id}", "get"),
    "get_ticket": ("/tickets/{ticket_id}", "get"),
    "create_ticket": ("/tickets", "post"),
    "get_appointments": ("/customers/{customer_id}/appointments", "get"),
    "get_appointment": ("/appointments/{appointment_id}", "get"),
    "list_available_slots": ("/appointments/available-slots", "get"),
    "get_appointment_slot": ("/appointments/slots/{slot_id}", "get"),
    "reschedule_appointment": ("/appointments/{appointment_id}", "put"),
    "create_handover": ("/handover", "post"),
}


def load_tool_schema() -> dict:
    return json.loads(TOOL_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_tool_schema_exposes_exact_current_operations() -> None:
    schema = load_tool_schema()
    actual = {
        operation["operationId"]: (path, method)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
    }

    assert schema["openapi"] == "3.0.3"
    assert actual == EXPECTED_OPERATIONS
    assert schema["servers"] == [{"url": "https://servicepilot-api.invalid"}]


def test_tool_operations_match_real_fastapi_routes() -> None:
    backend_paths = create_app().openapi()["paths"]

    for path, method in EXPECTED_OPERATIONS.values():
        assert path in backend_paths
        assert method in backend_paths[path]


def test_tool_schema_preserves_non_2xx_error_contracts() -> None:
    schema = load_tool_schema()

    for path_item in schema["paths"].values():
        for operation in path_item.values():
            responses = operation["responses"]
            assert "422" in responses
            assert "503" in responses
            assert any(int(status) < 300 for status in responses)
    write_responses = schema["paths"]["/tickets"]["post"]["responses"]
    assert "409" in write_responses
    reschedule_responses = schema["paths"]["/appointments/{appointment_id}"]["put"][
        "responses"
    ]
    assert "409" in reschedule_responses
    handover_responses = schema["paths"]["/handover"]["post"]["responses"]
    assert {"403", "404", "409"} <= set(handover_responses)


def test_reschedule_tool_is_reserved_for_deterministic_phase_six_flow() -> None:
    operation = load_tool_schema()["paths"]["/appointments/{appointment_id}"]["put"]

    assert "Phase 6" in operation["description"]
    assert "Do not call directly" in operation["description"]


def test_handover_tool_has_structured_idempotent_contract() -> None:
    schema = load_tool_schema()
    operation = schema["paths"]["/handover"]["post"]
    request = schema["components"]["schemas"]["HandoverCreate"]

    assert "stable handover_request_id" in operation["description"]
    assert request["required"] == ["reason", "conversation_summary"]
    assert "context" in request["properties"]
    assert request["properties"]["reason"]["enum"] == [
        "human_request",
        "technical_escalation",
        "complaint",
        "repeated_failure",
    ]


def test_tool_schema_contains_no_credentials_or_secret_values() -> None:
    serialized = TOOL_SCHEMA_PATH.read_text(encoding="utf-8").casefold()

    assert "authorization" not in serialized
    assert "api_key" not in serialized
    assert "bearer " not in serialized
