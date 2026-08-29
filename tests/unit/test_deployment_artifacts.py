from pathlib import Path


def test_cloud_run_deployment_is_private_and_secret_aware() -> None:
    script = Path("scripts/deploy-cloud-run.ps1").read_text(encoding="utf-8")
    assert "--no-allow-unauthenticated" in script
    assert "--service-account=" in script
    assert "--set-secrets=" in script
    assert "roles/run.invoker" in script
    assert "SERVICEPILOT_PERSISTENCE_BACKEND=firestore" in script
    assert "--ingress=$Ingress" in script
