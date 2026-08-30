import json
from pathlib import Path


FLOW_PATH = Path("conversation/appointment-reschedule-flow.json")


def load_flow() -> dict:
    return json.loads(FLOW_PATH.read_text(encoding="utf-8"))


def test_flow_requires_canonical_state_before_confirmation() -> None:
    flow = load_flow()

    assert flow["flow"]["required_inputs"] == [
        "customer_id",
        "appointment_id",
        "current_start",
        "current_end",
        "slot_id",
        "proposed_start",
        "proposed_end",
    ]
    prompt = flow["pages"]["confirm"]["prompt"]
    for parameter in flow["flow"]["required_inputs"]:
        assert f"$session.params.{parameter}" in prompt or parameter == "customer_id"


def test_only_explicit_confirmation_can_reach_single_write() -> None:
    flow = load_flow()
    safety = flow["safety"]
    webhook = flow["webhook"]

    assert safety["write_intent"] == flow["pages"]["confirm"]["confirm_intent"]
    assert safety["write_count"] == 1
    assert safety["ambiguous_confirmation_behavior"] == "reprompt"
    assert webhook["method"] == "PUT"
    assert webhook["path"] == "/appointments/$session.params.appointment_id"
    assert webhook["request_body"] == {
        "customer_id": "$session.params.customer_id",
        "slot_id": "$session.params.slot_id",
        "confirmed": True,
    }


def test_flow_verifies_canonical_backend_result_before_success() -> None:
    flow = load_flow()
    condition = flow["pages"]["verify"]["success_condition"]

    for comparison in (
        "updated_appointment_id = $session.params.appointment_id",
        "updated_customer_id = $session.params.customer_id",
        "updated_slot_id = $session.params.slot_id",
        'updated_status = \"scheduled\"',
    ):
        assert comparison in condition
    assert flow["safety"]["success_outcome"] == "succeeded"
    assert "kein Erfolg" in flow["pages"]["verify"]["failure_message"]


def test_flow_handles_decline_and_webhook_failures_without_success() -> None:
    flow = load_flow()

    assert flow["safety"]["decline_outcome"] == "cancelled"
    assert flow["safety"]["error_outcome"] == "failed"
    assert set(flow["pages"]["confirm"]["webhook_errors"]) == {
        "webhook.error",
        "webhook.error.timeout",
    }


def test_flexible_webhook_uses_private_cloud_run_auth_without_secrets() -> None:
    serialized = FLOW_PATH.read_text(encoding="utf-8").casefold()
    webhook = load_flow()["webhook"]

    assert webhook["type"] == "FLEXIBLE"
    assert webhook["authentication"] == "ID_TOKEN"
    assert "api_key" not in serialized
    assert "bearer " not in serialized
    assert "password" not in serialized
