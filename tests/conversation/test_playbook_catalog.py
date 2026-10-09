import json
from pathlib import Path

import pytest

from conversation.routing_contract import select_playbook


CATALOG_PATH = Path("conversation/catalog.json")
ROUTES_PATH = Path("conversation/golden_routes.json")
EXPECTED_PLAYBOOKS = {
    "DefaultService",
    "KnowledgeSupport",
    "ServiceTicket",
    "AppointmentManagement",
    "ComplaintManagement",
}


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalog_defines_phase_four_agent(catalog: dict) -> None:
    assert catalog["schema_version"] == 4
    assert catalog["agent"] == {
        "display_name": "ServicePilot",
        "default_language_code": "de",
        "time_zone": "Europe/Berlin",
        "location": "europe-west3",
        "conversation_start": "PLAYBOOK",
        "description": (
            "Deutschsprachiger Kundenservice-Agent für technische Geräte und "
            "Vor-Ort-Service."
        ),
    }
    assert {item["name"] for item in catalog["playbooks"]} == EXPECTED_PLAYBOOKS
    assert sum(bool(item["default"]) for item in catalog["playbooks"]) == 1


def test_each_playbook_has_complete_narrow_prompt(catalog: dict) -> None:
    required_fields = {
        "goal",
        "scope",
        "instructions",
        "tool_use_rules",
        "failure_behavior",
        "escalation_behavior",
        "examples",
    }
    for playbook in catalog["playbooks"]:
        assert required_fields <= playbook.keys()
        assert playbook["goal"].strip()
        assert all(playbook[field] for field in required_fields - {"goal", "examples"})
        assert len(playbook["examples"]) >= 4
        assert len({example["name"] for example in playbook["examples"]}) == len(
            playbook["examples"]
        )


def test_default_playbook_delegates_to_every_specialist(catalog: dict) -> None:
    default = next(item for item in catalog["playbooks"] if item["default"])
    instructions = "\n".join(default["instructions"])
    specialists = EXPECTED_PLAYBOOKS - {"DefaultService"}
    for specialist in specialists:
        assert f"${{PLAYBOOK: {specialist}}}" in instructions
    assert "do not greet, answer, or ask a generic question first" in instructions
    assert "Always communicate with the customer in German" in default["goal"]
    assert "${TOOL:" not in instructions


def test_guardrails_cover_business_critical_safety(catalog: dict) -> None:
    guardrails = " ".join(catalog["global_guardrails"]).casefold()
    for concept in (
        "erfinde niemals",
        "anderen kunden",
        "kanonische entität",
        "eindeutigen bestätigung",
        "verfügbaren termine",
        "blind",
        "gesprochene korrektur",
        "unterbrechung",
        "backend-latenz",
        "akustisch zu bestätigen",
    ):
        assert concept in guardrails


def test_all_example_routes_reference_known_playbooks(catalog: dict) -> None:
    for playbook in catalog["playbooks"]:
        for example in playbook["examples"]:
            assert example["state"] in {"OK", "PENDING", "ESCALATED", "FAILED", "CANCELLED"}
            if "route_to" in example:
                assert example["route_to"] in EXPECTED_PLAYBOOKS
                assert "tool" not in example
                assert "agent" not in example
            elif "tool" in example:
                assert example["tool"]["name"] in {
                    "ServicePilotBackend",
                    "ServicePilotKnowledge",
                }
                assert example["tool"]["action"]
                assert isinstance(example["tool"]["input"], dict)
                assert isinstance(example["tool"]["output"], (dict, list))
                assert example.get("agent")
            elif "flow" in example:
                assert example["flow"]["name"] == "AppointmentReschedule"
                assert isinstance(example["flow"]["input"], dict)
                assert isinstance(example["flow"]["output"], dict)
                assert example.get("agent")
            elif "steps" in example:
                assert len(example["steps"]) >= 2
                assert all(set(step) <= {"tool", "flow"} for step in example["steps"])
                assert all(len(step) == 1 for step in example["steps"])
            else:
                assert example.get("agent")


def test_default_routing_examples_carry_invocation_context(catalog: dict) -> None:
    default = next(item for item in catalog["playbooks"] if item["default"])
    route_examples = [example for example in default["examples"] if "route_to" in example]

    assert route_examples
    assert {example["state"] for example in route_examples} == {"OK"}
    assert all(example.get("summary") for example in route_examples)
    assert all(example.get("output_summary") for example in route_examples)


@pytest.mark.parametrize(
    ("utterance", "expected_playbook"),
    [
        pytest.param(item["utterance"], item["expected_playbook"], id=str(index))
        for index, item in enumerate(json.loads(ROUTES_PATH.read_text(encoding="utf-8")))
    ],
)
def test_golden_route_contract(utterance: str, expected_playbook: str) -> None:
    assert select_playbook(utterance) == expected_playbook


def test_tools_are_bound_only_to_responsible_playbooks(catalog: dict) -> None:
    instructions = {
        playbook["name"]: "\n".join(playbook["instructions"])
        for playbook in catalog["playbooks"]
    }

    assert "${TOOL: ServicePilotBackend}" in instructions["ServiceTicket"]
    assert "${TOOL: ServicePilotBackend}" in instructions["AppointmentManagement"]
    assert "${TOOL:" not in instructions["DefaultService"]
    assert "${TOOL: ServicePilotKnowledge}" in instructions["KnowledgeSupport"]
    assert "${TOOL: ServicePilotBackend}" in instructions["ComplaintManagement"]
    tool_bindings = {
        playbook["name"]: playbook.get("tools", [])
        for playbook in catalog["playbooks"]
    }
    assert tool_bindings["ServiceTicket"] == ["ServicePilotBackend"]
    assert tool_bindings["AppointmentManagement"] == ["ServicePilotBackend"]
    assert not tool_bindings["DefaultService"]
    assert tool_bindings["KnowledgeSupport"] == [
        "ServicePilotKnowledge",
        "ServicePilotBackend",
    ]
    assert tool_bindings["ComplaintManagement"] == ["ServicePilotBackend"]


def test_phase_six_binds_reschedule_flow_only_to_appointment_playbook(
    catalog: dict,
) -> None:
    flow_bindings = {
        playbook["name"]: playbook.get("flows", [])
        for playbook in catalog["playbooks"]
    }
    assert flow_bindings["AppointmentManagement"] == ["AppointmentReschedule"]
    assert all(
        not flows
        for name, flows in flow_bindings.items()
        if name != "AppointmentManagement"
    )
    appointment = next(
        item for item in catalog["playbooks"] if item["name"] == "AppointmentManagement"
    )
    assert "${FLOW: AppointmentReschedule}" in " ".join(appointment["instructions"])


def test_phase_five_tool_examples_cover_reads_writes_and_errors(catalog: dict) -> None:
    tool_examples = [
        example
        for playbook in catalog["playbooks"]
        for example in playbook["examples"]
        if "tool" in example
    ]
    sequence_tools = [
        step["tool"]
        for playbook in catalog["playbooks"]
        for example in playbook["examples"]
        for step in example.get("steps", [])
        if "tool" in step
    ]
    actions = {example["tool"]["action"] for example in tool_examples} | {
        tool["action"] for tool in sequence_tools
    }

    assert {
        "get_customer",
        "get_ticket",
        "create_ticket",
        "get_appointments",
        "get_appointment",
        "get_appointment_slot",
        "list_available_slots",
    } <= actions
    assert any("error" in example["tool"]["output"] for example in tool_examples)
    confirmed_write = next(
        example for example in tool_examples if example["tool"]["action"] == "create_ticket"
    )
    assert "not yet confirmed" in confirmed_write["input_summary"]
    assert confirmed_write["agent_before_user"]
    assert confirmed_write["user"].startswith("Ja")
    assert set(confirmed_write["tool"]["input"]) == {"requestBody"}
    assert "reschedule_appointment" not in actions
    appointment = next(
        item for item in catalog["playbooks"] if item["name"] == "AppointmentManagement"
    )
    assert "niemals direkt" in " ".join(appointment["instructions"])
    sequence_example = next(
        example for example in appointment["examples"] if "steps" in example
    )
    actions = [
        step["tool"]["action"] if "tool" in step else f"flow:{step['flow']['name']}"
        for step in sequence_example["steps"]
    ]
    assert actions == [
        "get_appointment",
        "get_appointment_slot",
        "flow:AppointmentReschedule",
    ]


def test_ticket_status_is_structured_and_executes_without_acknowledgement_turn(
    catalog: dict,
) -> None:
    default = next(item for item in catalog["playbooks"] if item["name"] == "DefaultService")
    service_ticket = next(
        item for item in catalog["playbooks"] if item["name"] == "ServiceTicket"
    )
    route = next(
        example for example in default["examples"] if example["name"] == "route ticket status"
    )
    retrieval = next(
        example
        for example in service_ticket["examples"]
        if example["name"] == "retrieve routed ticket status"
    )
    unknown_retrieval = next(
        example
        for example in service_ticket["examples"]
        if example["name"] == "routed unknown ticket"
    )

    assert service_ticket["input_parameters"] == [
        {
            "name": "ticket_id",
            "type": "STRING",
            "description": (
                "Exact ticket identifier explicitly supplied by the customer, for example "
                "T-4711. Empty when no ticket identifier is known."
            ),
        }
    ]
    assert route["route_parameters"] == {"ticket_id": "T-4711"}
    assert retrieval["input_parameters"] == {"ticket_id": "T-4711"}
    assert retrieval["input_summary"]
    assert "user" not in retrieval
    assert retrieval["tool"]["action"] == "get_ticket"
    assert retrieval["state"] == "PENDING"
    assert unknown_retrieval["state"] == "PENDING"
    instructions = " ".join(service_ticket["instructions"])
    assert "antworte nicht mit einer Ankündigung" in instructions
    assert "im selben Turn genau einmal" in instructions
    assert "genau eine Kundenantwort" in instructions


def test_appointment_id_is_structured_and_executes_without_clarification(
    catalog: dict,
) -> None:
    default = next(item for item in catalog["playbooks"] if item["name"] == "DefaultService")
    appointment = next(
        item for item in catalog["playbooks"] if item["name"] == "AppointmentManagement"
    )
    route = next(
        example for example in default["examples"] if example["name"] == "route multiple requests"
    )
    retrieval = next(
        example
        for example in appointment["examples"]
        if example["name"] == "retrieve routed appointment with additional issue"
    )

    assert appointment["input_parameters"] == [
        {
            "name": "appointment_id",
            "type": "STRING",
            "description": (
                "Exact appointment identifier explicitly supplied by the customer, for "
                "example A-0815. Empty when no appointment identifier is known."
            ),
        },
        {
            "name": "slot_id",
            "type": "STRING",
            "description": (
                "Exact appointment-slot identifier explicitly supplied by the customer, "
                "for example S-101. Empty when no slot identifier is known."
            ),
        },
    ]
    assert route["route_parameters"] == {"appointment_id": "A-0815"}
    assert "E37" in route["summary"]
    assert retrieval["input_parameters"] == {"appointment_id": "A-0815"}
    assert retrieval["input_summary"]
    assert "user" not in retrieval
    assert retrieval["tool"]["action"] == "get_appointment"
    assert retrieval["state"] == "PENDING"
    instructions = " ".join(appointment["instructions"])
    assert "antworte nicht mit einer Ankündigung oder Rückfrage" in instructions
    assert "im selben Turn genau einmal" in instructions
    assert "zusätzliche Anliegen wie E37" in instructions


def test_exact_reschedule_reads_canonical_records_before_flow(catalog: dict) -> None:
    default = next(item for item in catalog["playbooks"] if item["name"] == "DefaultService")
    appointment = next(
        item for item in catalog["playbooks"] if item["name"] == "AppointmentManagement"
    )
    route = next(
        example for example in default["examples"] if example["name"] == "route exact reschedule"
    )
    sequence = next(
        example
        for example in appointment["examples"]
        if example["name"] == "verify exact reschedule and enter deterministic flow"
    )

    assert route["route_parameters"] == {
        "appointment_id": "A-0815",
        "slot_id": "S-101",
    }
    assert sequence["input_parameters"] == route["route_parameters"]
    assert "user" not in sequence
    assert [next(iter(step)) for step in sequence["steps"]] == [
        "tool",
        "tool",
        "flow",
    ]
    assert sequence["steps"][0]["tool"]["action"] == "get_appointment"
    assert sequence["steps"][1]["tool"]["action"] == "get_appointment_slot"
    assert sequence["steps"][1]["tool"]["output"]["available"] is True
    assert sequence["steps"][2]["flow"]["name"] == "AppointmentReschedule"
    assert sequence["state"] == "OK"
    assert sequence["steps"][2]["flow"]["output"]["reschedule_outcome"] == "succeeded"
    instructions = " ".join(appointment["instructions"])
    assert "Benutzerbehauptung, der Slot sei frei" in instructions
    assert "ohne eigene Bestätigungsfrage" in instructions
    assert "Der Flow allein" in instructions
    assert "unmittelbar nächste Aktion zwingend" in instructions
    assert "frage insbesondere nicht selbst 'Ist das korrekt?'" in instructions
    tool_rules = " ".join(appointment["tool_use_rules"])
    assert "Bestätigungsfrage aus AppointmentManagement ist verboten" in tool_rules
