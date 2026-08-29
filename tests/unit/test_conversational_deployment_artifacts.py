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
    assert "$currentToolSet -ne $desiredToolSet" in script
    assert "$body.Remove('referencedTools')" in script
    assert "Test-PlaybookAlreadyCurrent" in script
    assert "toolUse = $toolUse" in script
    assert "inputActionParameters" in script
    assert "outputActionParameters" in script
    assert 'outputParameterName = "$($example.tool.action) output"' in script
    assert "agent_before_user" in script
    assert 'playbookState = "OUTPUT_STATE_$($example.state)"' in script
    assert "playbookState = 'OUTPUT_STATE_OK'" not in script
    assert "Dialogflow appends repeated actions during PATCH" in script
    assert 'Invoke-DialogflowApi -Method Delete -Uri "$endpoint/v3/$exampleName"' in script
    assert "Referenced resource.*does not exist" in script
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
