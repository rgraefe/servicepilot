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

    [string]$DefinitionPath = (Join-Path $PSScriptRoot '..\conversation\appointment-reschedule-flow.json')
)

$ErrorActionPreference = 'Stop'

$definition = Get-Content -Raw -LiteralPath (Resolve-Path -LiteralPath $DefinitionPath) |
    ConvertFrom-Json -Depth 100
$endpoint = "https://$Region-dialogflow.googleapis.com"
$agentResource = "projects/$ProjectId/locations/$Region/agents/$AgentId"
$apiRoot = "$endpoint/v3/$agentResource"

if (-not $PSCmdlet.ShouldProcess(
        "$agentResource/flows/$($definition.flow.display_name)",
        'Deploy the deterministic appointment-reschedule flow, intents, and authenticated flexible webhook'
    )) {
    return
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI was not found on PATH.'
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
$backendUrl = (Invoke-Gcloud @(
        'run', 'services', 'describe', $CloudRunServiceName,
        "--project=$ProjectId",
        "--region=$Region",
        '--format=value(status.url)'
    ) | Out-String).Trim().TrimEnd('/')
if ($projectNumber -notmatch '^[0-9]+$' -or $backendUrl -notmatch '^https://[A-Za-z0-9.-]+$') {
    throw 'Unable to resolve the project number or canonical Cloud Run URL.'
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

function New-TextMessage {
    param([Parameter(Mandatory = $true)][string]$Text)
    return @{ text = @{ text = @($Text) } }
}

function New-StringParameterDefinition {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Description
    )
    return @{
        name = $Name
        description = $Description
        typeSchema = @{ inlineSchema = @{ type = 'STRING' } }
    }
}

$intentList = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/intents?pageSize=1000&languageCode=de"
$intentResources = @{}
foreach ($intent in @($intentList.intents)) {
    if ($null -ne $intent) {
        $intentResources[$intent.displayName] = $intent.name
    }
}
foreach ($intentDefinition in @($definition.intents)) {
    $intentBody = @{
        displayName = $intentDefinition.display_name
        trainingPhrases = @($intentDefinition.training_phrases | ForEach-Object {
                @{ parts = @(@{ text = $_ }); repeatCount = 1 }
            })
    }
    if ($intentResources.ContainsKey($intentDefinition.display_name)) {
        $intentName = $intentResources[$intentDefinition.display_name]
        $intent = Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$intentName`?updateMask=displayName,trainingPhrases&languageCode=de" -Body $intentBody
    }
    else {
        $intent = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/intents?languageCode=de" -Body $intentBody
    }
    $intentResources[$intentDefinition.display_name] = $intent.name
}

$requestBody = $definition.webhook.request_body | ConvertTo-Json -Depth 20 -Compress
$webhookBody = @{
    displayName = $definition.webhook.display_name
    timeout = $definition.webhook.timeout
    disabled = $false
    genericWebService = @{
        uri = "$backendUrl$($definition.webhook.path)"
        webhookType = $definition.webhook.type
        httpMethod = $definition.webhook.method
        requestBody = $requestBody
        parameterMapping = $definition.webhook.response_mapping
        serviceAgentAuth = $definition.webhook.authentication
    }
}
$webhookList = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/webhooks?pageSize=100"
$existingWebhook = @($webhookList.webhooks) |
    Where-Object { $_.displayName -eq $definition.webhook.display_name } |
    Select-Object -First 1
if ($null -eq $existingWebhook) {
    $webhook = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/webhooks" -Body $webhookBody
}
else {
    $webhook = Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$($existingWebhook.name)?updateMask=displayName,timeout,disabled,genericWebService" -Body $webhookBody
}

$flowList = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/flows?pageSize=100"
$existingFlow = @($flowList.flows) |
    Where-Object { $_.displayName -eq $definition.flow.display_name } |
    Select-Object -First 1
$parameterDescriptions = @{
    customer_id = 'Canonical customer identifier verified before entering the flow.'
    appointment_id = 'Canonical scheduled appointment identifier selected by the customer.'
    current_start = 'Canonical current appointment start timestamp shown for confirmation.'
    current_end = 'Canonical current appointment end timestamp shown for confirmation.'
    slot_id = 'Backend-confirmed available slot identifier selected by the customer.'
    proposed_start = 'Backend-confirmed proposed slot start timestamp shown for confirmation.'
    proposed_end = 'Backend-confirmed proposed slot end timestamp shown for confirmation.'
    reschedule_outcome = 'One of succeeded, cancelled, failed, or invalid_input.'
    updated_appointment_id = 'Canonical appointment identifier returned by the write.'
    updated_customer_id = 'Canonical customer identifier returned by the write.'
    updated_slot_id = 'Canonical slot identifier returned by the write.'
    updated_start = 'Canonical updated start timestamp returned by the write.'
    updated_end = 'Canonical updated end timestamp returned by the write.'
    updated_status = 'Canonical appointment status returned by the write.'
}
$flowBaseBody = @{
    displayName = $definition.flow.display_name
    description = $definition.flow.description
    inputParameterDefinitions = @($definition.flow.required_inputs | ForEach-Object {
            New-StringParameterDefinition -Name $_ -Description $parameterDescriptions[$_]
        })
    outputParameterDefinitions = @($definition.flow.outputs | ForEach-Object {
            New-StringParameterDefinition -Name $_ -Description $parameterDescriptions[$_]
        })
}
if ($null -eq $existingFlow) {
    $flow = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/flows?languageCode=de" -Body $flowBaseBody
}
else {
    $flow = Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$($existingFlow.name)?updateMask=displayName,description,inputParameterDefinitions,outputParameterDefinitions&languageCode=de" -Body $flowBaseBody
}

$pageList = Invoke-DialogflowApi -Method Get -Uri "$endpoint/v3/$($flow.name)/pages?pageSize=100&languageCode=de"
$pageResources = @{}
foreach ($page in @($pageList.pages)) {
    if ($null -ne $page) {
        $pageResources[$page.displayName] = $page.name
    }
}
foreach ($pageDefinition in @($definition.pages.PSObject.Properties.Value)) {
    if (-not $pageResources.ContainsKey($pageDefinition.display_name)) {
        $createdPage = Invoke-DialogflowApi -Method Post -Uri "$endpoint/v3/$($flow.name)/pages?languageCode=de" -Body @{
            displayName = $pageDefinition.display_name
        }
        $pageResources[$pageDefinition.display_name] = $createdPage.name
    }
}

$endFlow = "$($flow.name)/pages/END_FLOW"
$endFlowCancelled = "$($flow.name)/pages/END_FLOW_WITH_CANCELLATION"
$endFlowFailed = "$($flow.name)/pages/END_FLOW_WITH_FAILURE"
$confirmPage = $pageResources[$definition.pages.confirm.display_name]
$verifyPage = $pageResources[$definition.pages.verify.display_name]
$failureFulfillment = @{
    messages = @(New-TextMessage -Text $definition.pages.verify.failure_message)
    setParameterActions = @(@{ parameter = 'reschedule_outcome'; value = $definition.safety.error_outcome })
}

$confirmPageBody = @{
    displayName = $definition.pages.confirm.display_name
    description = 'The only page allowed to invoke the reschedule write after a matched explicit-confirmation intent.'
    entryFulfillment = @{
        messages = @(New-TextMessage -Text $definition.pages.confirm.prompt)
        setParameterActions = @(@{ parameter = 'write_attempted'; value = $false })
    }
    transitionRoutes = @(
        @{
            intent = $intentResources[$definition.pages.confirm.confirm_intent]
            triggerFulfillment = @{
                webhook = $webhook.name
                tag = 'reschedule-confirmed-appointment'
                setParameterActions = @(@{ parameter = 'write_attempted'; value = $true })
            }
        },
        @{
            intent = $intentResources[$definition.pages.confirm.decline_intent]
            triggerFulfillment = @{
                messages = @(New-TextMessage -Text 'Verstanden. Der Termin wurde nicht verändert.')
                setParameterActions = @(@{ parameter = 'reschedule_outcome'; value = $definition.safety.decline_outcome })
            }
            targetPage = $endFlowCancelled
        },
        @{
            condition = $definition.pages.verify.success_condition
            targetPage = $verifyPage
        },
        @{
            condition = '$session.params.write_attempted = true'
            triggerFulfillment = $failureFulfillment
            targetPage = $endFlowFailed
        }
    )
    eventHandlers = @(
        @{
            event = 'webhook.error.timeout'
            triggerFulfillment = $failureFulfillment
            targetPage = $endFlowFailed
        },
        @{
            event = 'webhook.error'
            triggerFulfillment = $failureFulfillment
            targetPage = $endFlowFailed
        },
        @{
            event = 'sys.no-match-default'
            triggerFulfillment = @{
                messages = @(New-TextMessage -Text 'Bitte bestätigen Sie die genau zusammengefasste Terminänderung eindeutig oder lehnen Sie sie ab. Ohne eindeutige Bestätigung wird nichts geändert.')
            }
        }
    )
}
Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$confirmPage`?updateMask=displayName,description,entryFulfillment,transitionRoutes,eventHandlers&languageCode=de" -Body $confirmPageBody | Out-Null

$verifyPageBody = @{
    displayName = $definition.pages.verify.display_name
    description = 'Verifies the canonical backend response before reporting success.'
    entryFulfillment = @{
        messages = @(New-TextMessage -Text $definition.pages.verify.success_message)
        setParameterActions = @(@{ parameter = 'reschedule_outcome'; value = $definition.safety.success_outcome })
    }
    transitionRoutes = @(@{ condition = 'true'; targetPage = $endFlow })
}
Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$verifyPage`?updateMask=displayName,description,entryFulfillment,transitionRoutes&languageCode=de" -Body $verifyPageBody | Out-Null

$requiredCondition = ($definition.flow.required_inputs | ForEach-Object {
        "`$session.params.$_ != null"
    }) -join ' AND '
$flowBody = @{
    displayName = $definition.flow.display_name
    description = $definition.flow.description
    inputParameterDefinitions = $flowBaseBody.inputParameterDefinitions
    outputParameterDefinitions = $flowBaseBody.outputParameterDefinitions
    transitionRoutes = @(
        @{ condition = $requiredCondition; targetPage = $confirmPage },
        @{
            condition = 'true'
            triggerFulfillment = @{
                messages = @(New-TextMessage -Text 'Die Terminänderung kann nicht gestartet werden, weil bestätigte Termin- oder Slotdaten fehlen. Es wurde nichts geändert.')
                setParameterActions = @(@{ parameter = 'reschedule_outcome'; value = 'invalid_input' })
            }
            targetPage = $endFlowFailed
        }
    )
}
Invoke-DialogflowApi -Method Patch -Uri "$endpoint/v3/$($flow.name)?updateMask=displayName,description,inputParameterDefinitions,outputParameterDefinitions,transitionRoutes&languageCode=de" -Body $flowBody | Out-Null
Invoke-DialogflowApi -Method Post -Uri "$endpoint/v3/$($flow.name):train" -Body @{} | Out-Null

[pscustomobject]@{
    flow = $flow.name
    webhook = $webhook.name
    intents = @($definition.intents.display_name | Sort-Object)
    pages = @($pageResources.Keys | Sort-Object)
    backend_url = $backendUrl
    authentication = 'Dialogflow service agent ID token'
    invoker = "serviceAccount:$dialogflowServiceAgent"
}
