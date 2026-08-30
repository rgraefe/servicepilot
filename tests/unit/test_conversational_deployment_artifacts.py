from pathlib import Path


def test_conversational_deployment_script_is_idempotent_and_scoped() -> None:
    script = Path("scripts/deploy-conversational-agent.ps1").read_text(encoding="utf-8")
    assert "00000000-0000-0000-0000-000000000000" in script
    assert "dialogflow.googleapis.com" in script
    assert "updateMask=" in script
    assert "startPlaybook" in script
    assert "print-access-token" in script
    assert "x-goog-user-project" in script
    assert "examples?pageSize=100" in script
    assert "tools?pageSize=100" in script
    assert "ServicePilotBackend is missing" in script
    assert "referencedTools" in script
    assert "$currentToolSet -eq $desiredToolSet" in script
    assert "$body.Remove('referencedTools')" in script
    assert "so the resolver" in script
    assert "validates against the current agent draft" in script
    assert "instruction.guidelines" in script
    assert "instruction.steps" in script
    assert "Masking the parent" in script
    assert "Test-PlaybookAlreadyCurrent" in script
    assert "toolUse = $toolUse" in script
    assert "inputActionParameters" in script
    assert "outputActionParameters" in script
    assert 'outputParameterName = "$($example.tool.action) output"' in script
    assert "agent_before_user" in script
    assert "flows?pageSize=100" in script
    assert "AppointmentReschedule is missing" in script
    assert "flowInvocation" in script
    assert "referencedFlows is output-only" in script
    assert "updateFields += 'referencedFlows'" not in script
    assert 'playbookState = "OUTPUT_STATE_$($example.state)"' in script
    assert "playbookState = 'OUTPUT_STATE_OK'" not in script
    assert "Dialogflow appends repeated actions during PATCH" in script
    assert 'Invoke-DialogflowApi -Method Delete -Uri "$endpoint/v3/$exampleName"' in script
    assert "Referenced resource.*does not exist" in script
    assert "RATE_LIMIT_EXCEEDED|RESOURCE_EXHAUSTED" in script
    assert "[Math]::Min(15 * $attempt, 45)" in script
    assert "SupportsShouldProcess" in script


def test_conversational_tool_deployment_uses_private_cloud_run_auth() -> None:
    script = Path("scripts/deploy-conversational-tools.ps1").read_text(encoding="utf-8")

    assert "SupportsShouldProcess" in script
    assert "service-$projectNumber@gcp-sa-dialogflow.iam.gserviceaccount.com" in script
    assert "roles/run.invoker" in script
    assert "serviceAgentAuthConfig" in script
    assert "serviceAgentAuth = 'ID_TOKEN'" in script
    assert "servicepilot-openapi.json" in script
    assert "updateMask=displayName,description,openApiSpec" in script
    assert "$toolUnchanged" in script
    assert "versions?pageSize=100" in script
    assert "tool = $toolBody" in script
    assert "bearerTokenConfig" not in script
    assert "apiKeyConfig" not in script


def test_reschedule_flow_deployment_has_deterministic_write_boundary() -> None:
    script = Path("scripts/deploy-appointment-reschedule-flow.ps1").read_text(
        encoding="utf-8"
    )

    assert "SupportsShouldProcess" in script
    assert "roles/run.invoker" in script
    assert "serviceAgentAuth" in script
    assert "$definition.webhook.authentication" in script
    assert "write_attempted" in script
    assert "webhook.error.timeout" in script
    assert "END_FLOW_WITH_CANCELLATION" in script
    assert "END_FLOW_WITH_FAILURE" in script
    assert "$definition.pages.verify.success_condition" in script
    assert "$definition.flow.outputs" in script
    assert ":train" in script


def test_voice_deployment_uses_versioned_safe_speech_settings() -> None:
    script = Path("scripts/deploy-voice-agent.ps1").read_text(encoding="utf-8")

    assert "SupportsShouldProcess" in script
    assert "print-access-token" in script
    assert "speechToTextSettings" in script
    assert "textToSpeechSettings" in script
    assert "advancedSettings.speechSettings" in script
    assert "enableInteractionLogging" in script
    assert "voice-profile.json" in script
    assert "service-account" not in script.casefold()
    assert "api-key" not in script.casefold()


def test_voice_session_is_streaming_and_keeps_business_logic_external() -> None:
    script = Path("scripts/voice-session.py").read_text(encoding="utf-8")

    assert "streaming_detect_intent" in script
    assert "StreamingDetectIntentRequest" in script
    assert "AudioInput(config=input_config)" in script
    assert "enable_partial_response" in script
    assert "GOOGLE_OAUTH_ACCESS_TOKEN" in script
    assert "quota_project_id=quota_project_id" in script
    assert "write_linear16_wav" in script
    assert "/tickets" not in script
    assert "/appointments" not in script
