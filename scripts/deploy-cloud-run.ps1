[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z]+-[a-z]+[0-9]$')]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{0,47}[a-z0-9]$')]
    [string]$ServiceName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$')]
    [string]$RuntimeServiceAccount,

    [ValidatePattern('^[a-z][a-z0-9._-]{0,62}$')]
    [string]$ArtifactRepository = 'servicepilot',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')]
    [string]$ImageTag = (Get-Date -Format 'yyyyMMdd-HHmmss'),
    [ValidateRange(0, 100)]
    [int]$MinInstances = 0,
    [ValidateRange(1, 1000)]
    [int]$MaxInstances = 10,
    [ValidateRange(1, 1000)]
    [int]$Concurrency = 40,
    [ValidateRange(128, 32768)]
    [int]$MemoryMi = 512,
    [ValidateSet('all', 'internal', 'internal-and-cloud-load-balancing')]
    [string]$Ingress = 'all',

    [string[]]$Secret = @(),
    [string[]]$Invoker = @()
)

$ErrorActionPreference = 'Stop'

function Invoke-Gcloud {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud command failed: gcloud $($Arguments -join ' ')"
    }
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI was not found on PATH.'
}
if ($MinInstances -gt $MaxInstances) {
    throw 'MinInstances cannot be greater than MaxInstances.'
}

foreach ($mapping in $Secret) {
    if ($mapping -notmatch '^[A-Z][A-Z0-9_]*=[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+$') {
        throw "Invalid secret mapping '$mapping'. Expected ENV_VAR=secret-name:version."
    }
}

$image = "$Region-docker.pkg.dev/$ProjectId/$ArtifactRepository/" + $ServiceName + ":" + $ImageTag
$environmentVariables = @(
    'SERVICEPILOT_ENVIRONMENT=production'
    'SERVICEPILOT_LOG_LEVEL=INFO'
    'SERVICEPILOT_PERSISTENCE_BACKEND=firestore'
    "SERVICEPILOT_FIRESTORE_PROJECT=$ProjectId"
    'SERVICEPILOT_FIRESTORE_DATABASE=(default)'
) -join ','

if ($PSCmdlet.ShouldProcess($image, 'Build and deploy ServicePilot to private Cloud Run')) {
    Invoke-Gcloud @(
        'artifacts', 'repositories', 'describe', $ArtifactRepository,
        "--location=$Region",
        "--project=$ProjectId"
    )
    Invoke-Gcloud @(
        'builds', 'submit', '.',
        "--tag=$image",
        "--project=$ProjectId"
    )

    $deployArguments = @(
        'run', 'deploy', $ServiceName,
        "--image=$image",
        "--project=$ProjectId",
        "--region=$Region",
        "--service-account=$RuntimeServiceAccount",
        '--no-allow-unauthenticated',
        "--ingress=$Ingress",
        '--execution-environment=gen2',
        '--cpu=1',
        "--memory=$($MemoryMi)Mi",
        "--concurrency=$Concurrency",
        "--min-instances=$MinInstances",
        "--max-instances=$MaxInstances",
        '--timeout=30s',
        "--set-env-vars=$environmentVariables",
        '--quiet'
    )
    if ($Secret.Count -gt 0) {
        $deployArguments += "--set-secrets=$($Secret -join ',')"
    }
    Invoke-Gcloud $deployArguments

    foreach ($principal in $Invoker) {
        Invoke-Gcloud @(
            'run', 'services', 'add-iam-policy-binding', $ServiceName,
            "--project=$ProjectId",
            "--region=$Region",
            "--member=$principal",
            '--role=roles/run.invoker',
            '--quiet'
        )
    }

    Invoke-Gcloud @(
        'run', 'services', 'describe', $ServiceName,
        "--project=$ProjectId",
        "--region=$Region",
        '--format=value(status.url)'
    )
}
