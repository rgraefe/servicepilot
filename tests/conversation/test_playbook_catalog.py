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
    assert catalog["schema_version"] == 1
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
            assert ("route_to" in example) != ("agent" in example)
            if "route_to" in example:
                assert example["route_to"] in EXPECTED_PLAYBOOKS


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


def test_phase_four_does_not_bind_phase_five_tools(catalog: dict) -> None:
    serialized = json.dumps(catalog, ensure_ascii=False)
    assert "${TOOL:" not in serialized
    assert "Phase 5" in serialized
