import json
from pathlib import Path


CATALOG = Path("conversation/catalog.json")


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _playbook(name: str) -> dict:
    return next(item for item in _catalog()["playbooks"] if item["name"] == name)


def test_phase_eight_covers_all_handover_reasons() -> None:
    examples = [
        example
        for playbook in _catalog()["playbooks"]
        for example in playbook["examples"]
        if example.get("tool", {}).get("action") == "create_handover"
    ]
    reasons = {
        example["tool"]["input"]["requestBody"]["reason"] for example in examples
    }
    assert reasons == {
        "human_request",
        "technical_escalation",
        "complaint",
        "repeated_failure",
    }


def test_handover_examples_have_structured_context_and_stable_request_id() -> None:
    handovers = [
        example["tool"]["input"]["requestBody"]
        for playbook in _catalog()["playbooks"]
        for example in playbook["examples"]
        if example.get("tool", {}).get("action") == "create_handover"
    ]
    assert handovers
    for request in handovers:
        assert request["handover_request_id"].startswith("HO-")
        assert request["conversation_summary"]
        assert isinstance(request["context"], dict)
        assert "summary" not in request


def test_repeated_failure_escalates_only_after_two_failures() -> None:
    instructions = " ".join(
        instruction
        for name in ("KnowledgeSupport", "ServiceTicket", "AppointmentManagement")
        for instruction in _playbook(name)["failure_behavior"]
    )
    assert "zwei aufeinanderfolgenden" in instructions
    repeated = [
        example
        for example in _playbook("ServiceTicket")["examples"]
        if example.get("tool", {}).get("action") == "create_handover"
        and example["tool"]["input"]["requestBody"]["reason"] == "repeated_failure"
    ]
    assert repeated[0]["tool"]["input"]["requestBody"]["context"]["failure_count"] == 2


def test_failed_handover_never_claims_success() -> None:
    failure = next(
        example
        for example in _playbook("ComplaintManagement")["examples"]
        if example["name"] == "handover creation failure"
    )
    assert failure["state"] == "FAILED"
    assert failure["tool"]["output"]["error"]["retryable"] is True
    assert "nicht bestätigt" in failure["agent"]
    assert "keine Übergabenummer" in failure["agent"]


def test_missing_identity_does_not_block_explicit_human_request() -> None:
    example = next(
        example
        for example in _playbook("ComplaintManagement")["examples"]
        if example["name"] == "handover with missing identity"
    )
    request = example["tool"]["input"]["requestBody"]
    assert "customer_id" not in request
    assert example["tool"]["output"]["status"] == "queued"
