"""Deterministic semantic replay for version-controlled golden conversations.

This module does not emulate an LLM. It verifies the safety-relevant trace that
must remain true when prompts, playbooks, tools, or the rescheduling flow change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from conversation.routing_contract import select_playbook


WRITE_ACTIONS = {"create_ticket", "create_handover"}
CONFIRMATION_REQUIRED_ACTIONS = {"create_ticket"}
SUCCESS_IDENTIFIERS = {
    "create_ticket": "ticket_id",
    "create_handover": "handover_id",
}
RESULT_KINDS = {"success", "error", "timeout", "connection_error", "malformed"}
FINAL_STATES = {"success", "pending", "failed", "cancelled", "escalated"}


class RegressionContractError(AssertionError):
    """Raised when a golden trace violates a conversational safety contract."""


@dataclass(frozen=True)
class ReplayOutcome:
    route_sequence: tuple[str, ...]
    tool_sequence: tuple[str, ...]
    write_count: int
    final_state: str
    handover_reason: str | None


def _playbooks_by_name(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {playbook["name"]: playbook for playbook in catalog["playbooks"]}


def _require(condition: bool, scenario_id: str, message: str) -> None:
    if not condition:
        raise RegressionContractError(f"{scenario_id}: {message}")


def replay_golden_conversation(
    scenario: dict[str, Any], catalog: dict[str, Any], flow: dict[str, Any]
) -> ReplayOutcome:
    scenario_id = scenario.get("id", "<missing-id>")
    events = scenario.get("events")
    _require(isinstance(events, list) and events, scenario_id, "events are required")
    playbooks = _playbooks_by_name(catalog)

    routes: list[str] = []
    tools: list[str] = []
    active_playbook: str | None = None
    confirmation: str | None = None
    pending_action: str | None = None
    last_result: dict[str, Any] | None = None
    write_count = 0
    consecutive_failures = 0
    final_state: str | None = None
    handover_reason: str | None = None

    for index, event in enumerate(events):
        _require(isinstance(event, dict), scenario_id, f"event {index} must be an object")
        event_type = event.get("type")

        if event_type == "user":
            text = event.get("text")
            _require(isinstance(text, str) and text.strip(), scenario_id, "user text is required")
            if event.get("route", True):
                actual_route = select_playbook(text)
                expected_route = event.get("expected_playbook")
                _require(
                    actual_route == expected_route,
                    scenario_id,
                    f"expected route {expected_route}, got {actual_route}",
                )
                _require(actual_route in playbooks, scenario_id, "route references unknown playbook")
                active_playbook = actual_route
                routes.append(actual_route)
                confirmation = None
            continue

        if event_type == "confirmation":
            value = event.get("value")
            _require(value in {"exact", "ambiguous", "declined"}, scenario_id, "invalid confirmation")
            confirmation = value
            if value == "ambiguous":
                _require(
                    flow["safety"]["ambiguous_confirmation_behavior"] == "reprompt",
                    scenario_id,
                    "ambiguous confirmation must reprompt",
                )
            continue

        if event_type == "tool_call":
            _require(active_playbook is not None, scenario_id, "tool call has no active playbook")
            tool_name = event.get("tool")
            action = event.get("action")
            _require(tool_name in playbooks[active_playbook].get("tools", []), scenario_id, f"{tool_name} is not bound to {active_playbook}")
            _require(isinstance(action, str) and action, scenario_id, "tool action is required")
            if action in CONFIRMATION_REQUIRED_ACTIONS:
                _require(confirmation == "exact", scenario_id, f"{action} requires exact confirmation")
            if action == "create_handover":
                reason = event.get("reason")
                _require(
                    reason in {"human_request", "technical_escalation", "complaint", "repeated_failure"},
                    scenario_id,
                    "invalid handover reason",
                )
                if reason == "repeated_failure":
                    _require(consecutive_failures >= 2, scenario_id, "repeated-failure handover requires two failures")
                request_id = event.get("request_id")
                _require(isinstance(request_id, str) and request_id.startswith("HO-"), scenario_id, "handover requires a stable request ID")
                handover_reason = reason
            pending_action = action
            last_result = None
            tools.append(action)
            if action in WRITE_ACTIONS:
                write_count += 1
            continue

        if event_type == "flow_call":
            _require(active_playbook is not None, scenario_id, "flow call has no active playbook")
            flow_name = event.get("flow")
            _require(flow_name in playbooks[active_playbook].get("flows", []), scenario_id, f"{flow_name} is not bound to {active_playbook}")
            _require(flow_name == flow["flow"]["display_name"], scenario_id, "unknown deterministic flow")
            _require(confirmation == "exact", scenario_id, "rescheduling flow requires exact confirmation")
            pending_action = "reschedule_appointment"
            last_result = None
            tools.append(f"flow:{flow_name}")
            write_count += flow["safety"]["write_count"]
            continue

        if event_type == "tool_result":
            _require(pending_action is not None, scenario_id, "tool result has no pending call")
            kind = event.get("kind")
            _require(kind in RESULT_KINDS, scenario_id, "invalid tool-result kind")
            last_result = event
            if kind == "success":
                entity = event.get("entity")
                _require(isinstance(entity, (dict, list)), scenario_id, "success requires a canonical result")
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            continue

        if event_type == "failure":
            kind = event.get("kind")
            _require(kind in RESULT_KINDS - {"success"}, scenario_id, "invalid injected failure")
            consecutive_failures += 1
            last_result = {"type": "tool_result", "kind": kind}
            pending_action = None
            continue

        if event_type == "agent_outcome":
            state = event.get("state")
            claims_success = event.get("claims_success", False)
            _require(state in FINAL_STATES, scenario_id, "invalid final state")
            if claims_success:
                _require(last_result is not None and last_result.get("kind") == "success", scenario_id, "success claim requires successful canonical result")
                entity = last_result["entity"]
                identifier = SUCCESS_IDENTIFIERS.get(pending_action or "")
                if identifier:
                    _require(isinstance(entity, dict) and entity.get(identifier), scenario_id, f"success requires {identifier}")
                if pending_action == "create_handover":
                    _require(entity.get("status") == "queued", scenario_id, "handover success requires queued status")
                if pending_action == "reschedule_appointment":
                    _require(entity.get("status") == "scheduled", scenario_id, "reschedule success requires scheduled status")
            elif last_result and last_result.get("kind") != "success":
                _require(state != "success", scenario_id, "failed tool result cannot end in success")
            final_state = state
            pending_action = None
            continue

        raise RegressionContractError(f"{scenario_id}: unknown event type {event_type!r}")

    _require(final_state is not None, scenario_id, "trace requires an agent outcome")
    outcome = ReplayOutcome(tuple(routes), tuple(tools), write_count, final_state, handover_reason)
    expected = scenario.get("expected", {})
    _require(list(outcome.route_sequence) == expected.get("route_sequence"), scenario_id, "route sequence changed")
    _require(list(outcome.tool_sequence) == expected.get("tool_sequence"), scenario_id, "tool sequence changed")
    _require(outcome.write_count == expected.get("write_count"), scenario_id, "write count changed")
    _require(outcome.final_state == expected.get("final_state"), scenario_id, "final state changed")
    _require(outcome.handover_reason == expected.get("handover_reason"), scenario_id, "handover reason changed")
    return outcome
