from fastapi.testclient import TestClient
from google.api_core.exceptions import DeadlineExceeded


def assert_error(
    response, status: int, code: str, *, retryable: bool = False
) -> None:
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable


def test_health_and_openapi(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["persistence_backend"] == "memory"
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/tickets" in schema.json()["paths"]


def test_customer_and_related_reads(client: TestClient) -> None:
    assert client.get("/customers/C-10023").json()["name"] == "Max Mustermann"
    assert client.get("/customers/C-10023/devices").json()[0]["device_id"] == "D-1007"
    assert client.get("/customers/C-10023/tickets").json()[0]["ticket_id"] == "T-4711"
    assert (
        client.get("/customers/C-10023/appointments").json()[0]["appointment_id"]
        == "A-0815"
    )


def test_request_logging_uses_correlation_and_route_template(
    client: TestClient, monkeypatch
) -> None:
    info_calls = []

    def capture_info(message, *, extra):
        info_calls.append((message, extra))

    monkeypatch.setattr(client.app.state.logger, "info", capture_info)
    response = client.get(
        "/customers/C-10023", headers={"x-request-id": "caller-request-42"}
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "caller-request-42"
    request_log = next(extra for message, extra in info_calls if message == "request_completed")
    assert request_log["route"] == "/customers/{customer_id}"
    assert "C-10023" not in str(request_log)


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get(
        "/health", headers={"x-request-id": "invalid request id with spaces"}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "invalid request id with spaces"
    assert len(response.headers["x-request-id"]) == 32


def test_missing_customer_has_structured_error(client: TestClient) -> None:
    assert_error(client.get("/customers/C-404"), 404, "CUSTOMER_NOT_FOUND")


def test_get_ticket_and_appointment(client: TestClient) -> None:
    assert client.get("/tickets/T-4711").status_code == 200
    assert client.get("/appointments/A-0815").status_code == 200
    assert_error(client.get("/tickets/T-404"), 404, "TICKET_NOT_FOUND")
    assert_error(client.get("/appointments/A-404"), 404, "APPOINTMENT_NOT_FOUND")


def test_create_ticket_returns_canonical_entity(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "customer_id": "C-10023",
            "device_id": "D-1007",
            "problem_code": "E99",
            "description": "New fault",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ticket_id"].startswith("T-")
    assert body["status"] == "created"
    assert client.get(f"/tickets/{body['ticket_id']}").json() == body


def test_duplicate_ticket_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "customer_id": "C-10023",
            "device_id": "D-1007",
            "problem_code": "e37",
            "description": "Same active fault",
        },
    )
    assert_error(response, 409, "DUPLICATE_ACTIVE_TICKET")


def test_invalid_ticket_input_uses_error_contract(client: TestClient) -> None:
    response = client.post("/tickets", json={"customer_id": "bad"})
    assert_error(response, 422, "VALIDATION_ERROR")
    assert response.json()["error"]["details"]


def test_available_slots_and_reschedule(client: TestClient) -> None:
    slots = client.get(
        "/appointments/available-slots",
        params={
            "customer_id": "C-10023",
            "from_date": "2026-09-09",
            "to_date": "2026-09-10",
        },
    )
    assert slots.status_code == 200
    assert [slot["slot_id"] for slot in slots.json()] == ["S-101", "S-102"]
    response = client.put(
        "/appointments/A-0815",
        json={"customer_id": "C-10023", "slot_id": "S-101", "confirmed": True},
    )
    assert response.status_code == 200
    assert response.json()["slot_id"] == "S-101"
    retry = client.put(
        "/appointments/A-0815",
        json={"customer_id": "C-10023", "slot_id": "S-101", "confirmed": True},
    )
    assert_error(retry, 409, "SLOT_UNAVAILABLE")


def test_reschedule_requires_confirmation_and_ownership(client: TestClient) -> None:
    not_confirmed = client.put(
        "/appointments/A-0815",
        json={"customer_id": "C-10023", "slot_id": "S-101", "confirmed": False},
    )
    assert_error(not_confirmed, 409, "CONFIRMATION_REQUIRED")
    wrong_customer = client.put(
        "/appointments/A-0815",
        json={"customer_id": "C-99999", "slot_id": "S-101", "confirmed": True},
    )
    assert_error(wrong_customer, 403, "APPOINTMENT_NOT_OWNED_BY_CUSTOMER")


def test_create_handover(client: TestClient) -> None:
    response = client.post(
        "/handover",
        json={
            "customer_id": "C-10023",
            "reason": "technical_escalation",
            "summary": "Recurring fault needs review.",
            "ticket_id": "T-4711",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "queued"


def test_handover_rejects_missing_ticket(client: TestClient) -> None:
    response = client.post(
        "/handover",
        json={
            "customer_id": "C-10023",
            "reason": "technical_escalation",
            "summary": "Needs review.",
            "ticket_id": "T-404",
        },
    )
    assert_error(response, 404, "TICKET_NOT_FOUND")


def test_firestore_failure_has_safe_structured_error(
    client: TestClient, monkeypatch
) -> None:
    async def fail(_: str):
        raise DeadlineExceeded("sensitive backend detail")

    monkeypatch.setattr(client.app.state.container.tickets._tickets, "get", fail)
    response = client.get("/tickets/T-4711")
    assert_error(response, 503, "PERSISTENCE_UNAVAILABLE", retryable=True)
    assert "sensitive" not in response.text
