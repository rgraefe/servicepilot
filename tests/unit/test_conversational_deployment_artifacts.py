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
    assert 'playbookState = "OUTPUT_STATE_$($example.state)"' in script
    assert "playbookState = 'OUTPUT_STATE_OK'" not in script
    assert "Dialogflow appends repeated actions during PATCH" in script
    assert 'Invoke-DialogflowApi -Method Delete -Uri "$endpoint/v3/$exampleName"' in script
    assert "Referenced resource.*does not exist" in script
    assert "SupportsShouldProcess" in script
