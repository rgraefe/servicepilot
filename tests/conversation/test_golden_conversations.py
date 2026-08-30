import copy
import json
from pathlib import Path

import pytest

from conversation.regression_contract import (
    RegressionContractError,
    replay_golden_conversation,
)


GOLDEN_PATH = Path("conversation/golden_conversations.json")
CATALOG_PATH = Path("conversation/catalog.json")
FLOW_PATH = Path("conversation/appointment-reschedule-flow.json")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


GOLDEN = load_json(GOLDEN_PATH)
CATALOG = load_json(CATALOG_PATH)
FLOW = load_json(FLOW_PATH)
SCENARIOS = GOLDEN["scenarios"]


def test_phase_ten_has_at_least_thirty_unique_semantic_conversations() -> None:
    assert GOLDEN["schema_version"] == 1
    assert len(SCENARIOS) >= 30
    assert len({scenario["id"] for scenario in SCENARIOS}) == len(SCENARIOS)
    assert all(scenario["events"] and scenario["expected"] for scenario in SCENARIOS)
    assert all(
        "agent" not in event and "response_text" not in event
        for scenario in SCENARIOS
        for event in scenario["events"]
    )


def test_phase_ten_covers_every_required_regression_category() -> None:
    categories = {scenario["category"] for scenario in SCENARIOS}
    assert {
        "happy_path",
        "invalid_identifier",
        "unknown_error_code",
        "unavailable_slot",
        "backend_timeout",
        "duplicate_submission",
        "ambiguous_confirmation",
        "handover",
        "topic_switch",
        "repeated_failure",
    } <= categories


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["id"])
def test_golden_conversation_semantics_are_repeatable(scenario: dict) -> None:
    outcome = replay_golden_conversation(scenario, CATALOG, FLOW)

    assert outcome.final_state == scenario["expected"]["final_state"]


def test_failure_injection_covers_transport_provider_and_shape_failures() -> None:
    result_events = [
        event
        for scenario in SCENARIOS
        for event in scenario["events"]
        if event["type"] in {"tool_result", "failure"}
    ]
    kinds = {event["kind"] for event in result_events}
    error_codes = {
        event["error_code"] for event in result_events if "error_code" in event
    }

    assert {"success", "error", "timeout", "connection_error", "malformed"} <= kinds
    assert {
        "TICKET_NOT_FOUND",
        "CUSTOMER_NOT_FOUND",
        "APPOINTMENT_SLOT_UNAVAILABLE",
        "DUPLICATE_ACTIVE_TICKET",
        "PERSISTENCE_UNAVAILABLE",
        "INVALID_APPOINTMENT_STATE",
    } <= error_codes


def test_corpus_exercises_all_playbooks_and_critical_boundaries() -> None:
    routes = {
        route
        for scenario in SCENARIOS
        for route in scenario["expected"]["route_sequence"]
    }
    tools = {
        tool
        for scenario in SCENARIOS
        for tool in scenario["expected"]["tool_sequence"]
    }
    assert routes == {
        "DefaultService",
        "KnowledgeSupport",
        "ServiceTicket",
        "AppointmentManagement",
        "ComplaintManagement",
    }
    assert {
        "get_customer",
        "get_ticket",
        "create_ticket",
        "get_appointments",
        "list_available_slots",
        "search_knowledge",
        "create_handover",
        "flow:AppointmentReschedule",
    } <= tools


def scenario_by_id(scenario_id: str) -> dict:
    return copy.deepcopy(next(item for item in SCENARIOS if item["id"] == scenario_id))


def test_unconfirmed_ticket_write_is_rejected_by_replay_contract() -> None:
    scenario = scenario_by_id("ticket-create-confirmed")
    scenario["events"] = [
        event for event in scenario["events"] if event["type"] != "confirmation"
    ]

    with pytest.raises(RegressionContractError, match="requires exact confirmation"):
        replay_golden_conversation(scenario, CATALOG, FLOW)


def test_false_success_after_timeout_is_rejected_by_replay_contract() -> None:
    scenario = scenario_by_id("backend-timeout-ticket-read")
    scenario["events"][-1] = {
        "type": "agent_outcome",
        "state": "success",
        "claims_success": True,
    }

    with pytest.raises(RegressionContractError, match="success claim requires"):
        replay_golden_conversation(scenario, CATALOG, FLOW)


def test_early_repeated_failure_handover_is_rejected() -> None:
    scenario = scenario_by_id("repeated-ticket-failure-handover")
    first_failure = next(
        index
        for index, event in enumerate(scenario["events"])
        if event["type"] == "failure"
    )
    del scenario["events"][first_failure]

    with pytest.raises(RegressionContractError, match="requires two failures"):
        replay_golden_conversation(scenario, CATALOG, FLOW)


def test_tool_owned_by_wrong_playbook_is_rejected() -> None:
    scenario = scenario_by_id("technical-faq-cited")
    tool_call = next(
        event for event in scenario["events"] if event["type"] == "tool_call"
    )
    tool_call["tool"] = "ServicePilotUnknownTool"

    with pytest.raises(RegressionContractError, match="not bound"):
        replay_golden_conversation(scenario, CATALOG, FLOW)
