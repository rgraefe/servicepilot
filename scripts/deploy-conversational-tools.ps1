[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z]+-[a-z]+[0-9]$')]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$AgentId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{0,47}[a-z0-9]$')]
    [string]$CloudRunServiceName,

    [string]$OpenApiPath = (Join-Path $PSScriptRoot '..\conversation\servicepilot-openapi.json')
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI was not found on PATH.'
}

$resolvedOpenApiPath = (Resolve-Path -LiteralPath $OpenApiPath).Path
$agentResource = "projects/$ProjectId/locations/$Region/agents/$AgentId"
$endpoint = "https://$Region-dialogflow.googleapis.com"
$toolDisplayName = 'ServicePilotBackend'

if (-not $PSCmdlet.ShouldProcess(
        "$agentResource/tools/$toolDisplayName",
        'Grant the Dialogflow service agent Cloud Run invoker and deploy the authenticated OpenAPI tool'
    )) {
    return
}

function Invoke-Gcloud {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $result = & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud command failed: gcloud $($Arguments -join ' ')"
    }
    return $result
}

$projectNumber = (Invoke-Gcloud @(
        'projects', 'describe', $ProjectId,
        '--format=value(projectNumber)'
    ) | Out-String).Trim()
if ($projectNumber -notmatch '^[0-9]+$') {
    throw 'Unable to resolve the Google Cloud project number.'
}

$backendUrl = (Invoke-Gcloud @(
        'run', 'services', 'describe', $CloudRunServiceName,
        "--project=$ProjectId",
        "--region=$Region",
        '--format=value(status.url)'
    ) | Out-String).Trim().TrimEnd('/')
if ($backendUrl -notmatch '^https://[A-Za-z0-9.-]+$') {
    throw "Cloud Run returned an invalid HTTPS service URL: '$backendUrl'."
}

$dialogflowServiceAgent = "service-$projectNumber@gcp-sa-dialogflow.iam.gserviceaccount.com"
Invoke-Gcloud @(
    'run', 'services', 'add-iam-policy-binding', $CloudRunServiceName,
    "--project=$ProjectId",
    "--region=$Region",
    "--member=serviceAccount:$dialogflowServiceAgent",
    '--role=roles/run.invoker',
    '--quiet'
) | Out-Null

$openApi = Get-Content -Raw -LiteralPath $resolvedOpenApiPath | ConvertFrom-Json -Depth 100
if ($openApi.openapi -ne '3.0.3') {
    throw 'The conversational OpenAPI document must use OpenAPI 3.0.3.'
}
if (@($openApi.servers).Count -ne 1) {
    throw 'The conversational OpenAPI document must define exactly one server.'
}
$openApi.servers[0].url = $backendUrl
$textSchema = $openApi | ConvertTo-Json -Depth 100 -Compress

$accessToken = & gcloud auth print-access-token
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($accessToken)) {
    throw 'Unable to obtain a Google Cloud access token.'
}
$headers = @{
    Authorization = "Bearer $accessToken"
    'x-goog-user-project' = $ProjectId
}

function Invoke-DialogflowApi {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Get', 'Post', 'Patch')][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body
    )

    $arguments = @{
        Method = $Method
        Uri = $Uri
        Headers = $headers
        ContentType = 'application/json; charset=utf-8'
    }
    if ($null -ne $Body) {
        $arguments.Body = $Body | ConvertTo-Json -Depth 100 -Compress
    }
    try {
        return Invoke-RestMethod @arguments
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode
        $details = $_.ErrorDetails.Message
        throw "Dialogflow API $Method request to '$Uri' failed ($statusCode): $details"
    }
}

$toolBody = @{
    displayName = $toolDisplayName
    description = 'Authenticated deterministic customer, ticket, and appointment operations for ServicePilot.'
    openApiSpec = @{
        textSchema = $textSchema
        authentication = @{
            serviceAgentAuthConfig = @{
                serviceAgentAuth = 'ID_TOKEN'
            }
        }
    }
}

$apiRoot = "$endpoint/v3/$agentResource"
$toolList = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/tools?pageSize=100"
$existingTool = @($toolList.tools) |
    Where-Object { $_.displayName -eq $toolDisplayName } |
    Select-Object -First 1

if ($null -eq $existingTool) {
    $tool = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/tools" -Body $toolBody
}
else {
    $toolUnchanged = (
        $existingTool.description -eq $toolBody.description -and
        $existingTool.openApiSpec.textSchema -eq $toolBody.openApiSpec.textSchema -and
        $existingTool.openApiSpec.authentication.serviceAgentAuthConfig.serviceAgentAuth -eq 'ID_TOKEN'
    )
    if ($toolUnchanged) {
        $tool = $existingTool
    }
    else {
        $toolUri = "$endpoint/v3/$($existingTool.name)?updateMask=displayName,description,openApiSpec"
        $tool = Invoke-DialogflowApi -Method Patch -Uri $toolUri -Body $toolBody
    }
}

$versionList = Invoke-DialogflowApi -Method Get -Uri "$endpoint/v3/$($tool.name)/versions?pageSize=100"
$matchingVersion = @($versionList.toolVersions) |
    Where-Object {
        $_.tool.displayName -eq $toolBody.displayName -and
        $_.tool.description -eq $toolBody.description -and
        $_.tool.openApiSpec.textSchema -eq $toolBody.openApiSpec.textSchema -and
        $_.tool.openApiSpec.authentication.serviceAgentAuthConfig.serviceAgentAuth -eq 'ID_TOKEN'
    } |
    Select-Object -First 1
if ($null -eq $matchingVersion) {
    $versionBody = @{
        displayName = "phase-5-$([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))"
        tool = $toolBody
    }
    $matchingVersion = Invoke-DialogflowApi -Method Post -Uri "$endpoint/v3/$($tool.name)/versions" -Body $versionBody
}

[pscustomobject]@{
    tool = $tool.name
    display_name = $tool.displayName
    backend_url = $backendUrl
    authentication = 'Dialogflow service agent ID token'
    invoker = "serviceAccount:$dialogflowServiceAgent"
    version = $matchingVersion.name
}
