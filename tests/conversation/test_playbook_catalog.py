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
    assert catalog["schema_version"] == 3
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
                assert example["tool"]["name"] == "ServicePilotBackend"
                assert example["tool"]["action"]
                assert isinstance(example["tool"]["input"], dict)
                assert isinstance(example["tool"]["output"], (dict, list))
                assert example.get("agent")
            elif "flow" in example:
                assert example["flow"]["name"] == "AppointmentReschedule"
                assert isinstance(example["flow"]["input"], dict)
                assert isinstance(example["flow"]["output"], dict)
                assert example.get("agent")
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


def test_phase_five_binds_tools_only_to_responsible_playbooks(catalog: dict) -> None:
    instructions = {
        playbook["name"]: "\n".join(playbook["instructions"])
        for playbook in catalog["playbooks"]
    }

    assert "${TOOL: ServicePilotBackend}" in instructions["ServiceTicket"]
    assert "${TOOL: ServicePilotBackend}" in instructions["AppointmentManagement"]
    assert "${TOOL:" not in instructions["DefaultService"]
    assert "${TOOL:" not in instructions["KnowledgeSupport"]
    assert "${TOOL:" not in instructions["ComplaintManagement"]
    tool_bindings = {
        playbook["name"]: playbook.get("tools", [])
        for playbook in catalog["playbooks"]
    }
    assert tool_bindings["ServiceTicket"] == ["ServicePilotBackend"]
    assert tool_bindings["AppointmentManagement"] == ["ServicePilotBackend"]
    assert not tool_bindings["DefaultService"]
    assert not tool_bindings["KnowledgeSupport"]
    assert not tool_bindings["ComplaintManagement"]


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
    actions = {example["tool"]["action"] for example in tool_examples}

    assert {
        "get_customer",
        "get_ticket",
        "create_ticket",
        "get_appointments",
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
    flow_example = next(
        example for example in appointment["examples"] if "flow" in example
    )
    assert flow_example["flow"]["output"]["reschedule_outcome"] == "succeeded"
