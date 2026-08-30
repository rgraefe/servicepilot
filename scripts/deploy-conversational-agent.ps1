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

    [string]$CatalogPath = (Join-Path $PSScriptRoot '..\conversation\catalog.json')
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI was not found on PATH.'
}

$resolvedCatalogPath = (Resolve-Path -LiteralPath $CatalogPath).Path
$catalog = Get-Content -Raw -LiteralPath $resolvedCatalogPath | ConvertFrom-Json -Depth 100
$expectedPlaybooks = @(
    'DefaultService',
    'KnowledgeSupport',
    'ServiceTicket',
    'AppointmentManagement',
    'ComplaintManagement'
)
$actualPlaybooks = @($catalog.playbooks | ForEach-Object { $_.name })
if (@(Compare-Object $expectedPlaybooks $actualPlaybooks).Count -ne 0) {
    throw 'The catalog must contain exactly the five Phase 4 playbooks.'
}

$endpoint = "https://$Region-dialogflow.googleapis.com"
$agentResource = "projects/$ProjectId/locations/$Region/agents/$AgentId"
$apiRoot = "$endpoint/v3/$agentResource"

if (-not $PSCmdlet.ShouldProcess($agentResource, 'Create or update Phase 6 tool- and flow-aware playbooks and examples')) {
    return
}

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
        [Parameter(Mandatory = $true)][ValidateSet('Get', 'Post', 'Patch', 'Delete')][string]$Method,
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
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            return Invoke-RestMethod @arguments
        }
        catch {
            $details = $_.ErrorDetails.Message
            $isPropagationDelay = $details -match 'Referenced resource.*does not exist'
            if ($isPropagationDelay -and $attempt -lt 5) {
                Start-Sleep -Seconds (2 * $attempt)
                continue
            }

            $statusCode = $_.Exception.Response.StatusCode
            throw "Dialogflow API $Method request to '$Uri' failed ($statusCode): $details"
        }
    }
}

function New-PlaybookBody {
    param([Parameter(Mandatory = $true)][object]$Definition)

    $guidelines = @(
        $catalog.global_guardrails
        "Scope: $($Definition.scope -join '; ')"
        "Tool-use rules: $($Definition.tool_use_rules -join ' ')"
        "Failure behavior: $($Definition.failure_behavior -join ' ')"
        "Escalation behavior: $($Definition.escalation_behavior -join ' ')"
    ) -join "`n"

    $body = @{
        displayName = $Definition.name
        goal = $Definition.goal
        playbookType = $Definition.type
        instruction = @{
            guidelines = $guidelines
            steps = @($Definition.instructions | ForEach-Object { @{ text = $_ } })
        }
    }
    $referencedTools = @()
    if ($Definition.PSObject.Properties.Name -contains 'tools') {
        $referencedTools = @($Definition.tools | ForEach-Object {
                $resourceName = $toolResources[$_]
                if ([string]::IsNullOrWhiteSpace($resourceName)) {
                    throw "Playbook '$($Definition.name)' references unknown tool '$_'."
                }
                $resourceName
            })
    }
    if ($referencedTools.Count -gt 0) {
        $body.referencedTools = $referencedTools
    }
    # referencedFlows is output-only in the Dialogflow API. Validate catalog
    # declarations here; Dialogflow infers the reference from ${FLOW: ...} steps.
    if ($Definition.PSObject.Properties.Name -contains 'flows') {
        @($Definition.flows | ForEach-Object {
                $resourceName = $flowResources[$_]
                if ([string]::IsNullOrWhiteSpace($resourceName)) {
                    throw "Playbook '$($Definition.name)' references unknown flow '$_'."
                }
            }) | Out-Null
    }
    return $body
}

$toolListResponse = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/tools?pageSize=100"
$toolResources = @{}
foreach ($tool in @($toolListResponse.tools)) {
    if ($null -ne $tool) {
        $toolResources[$tool.displayName] = $tool.name
    }
}
if (-not $toolResources.ContainsKey('ServicePilotBackend')) {
    throw 'ServicePilotBackend is missing. Run deploy-conversational-tools.ps1 before deploying Phase 5/6 playbooks.'
}

$flowListResponse = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/flows?pageSize=100"
$flowResources = @{}
foreach ($flow in @($flowListResponse.flows)) {
    if ($null -ne $flow) {
        $flowResources[$flow.displayName] = $flow.name
    }
}
if (-not $flowResources.ContainsKey('AppointmentReschedule')) {
    throw 'AppointmentReschedule is missing. Run deploy-appointment-reschedule-flow.ps1 before deploying Phase 6 playbooks.'
}

$listResponse = Invoke-DialogflowApi -Method Get -Uri "$apiRoot/playbooks?pageSize=100"
$playbookResources = @{}
$playbookReferencedTools = @{}
$playbookSnapshots = @{}
$reservedDefaultResource = "$agentResource/playbooks/00000000-0000-0000-0000-000000000000"
$reservedDefaultExists = $false
foreach ($playbook in @($listResponse.playbooks)) {
    if ($null -ne $playbook) {
        $playbookResources[$playbook.displayName] = $playbook.name
        $playbookReferencedTools[$playbook.displayName] = @($playbook.referencedTools)
        $playbookSnapshots[$playbook.displayName] = $playbook
        if ($playbook.name -eq $reservedDefaultResource) {
            $reservedDefaultExists = $true
        }
    }
}

function Test-PlaybookAlreadyCurrent {
    param(
        [Parameter(Mandatory = $true)][object]$Current,
        [Parameter(Mandatory = $true)][hashtable]$Desired,
        [switch]$AllowMissingGuidelines
    )

    $desiredSteps = @($Desired.instruction.steps | ForEach-Object {
            $_.text.Replace('${TOOL: ', '${TOOL:').Replace('${PLAYBOOK: ', '${PLAYBOOK:').Replace('${FLOW: ', '${FLOW:')
        })
    $currentSteps = @($Current.instruction.steps | ForEach-Object {
            $_.text.Replace('${TOOL: ', '${TOOL:').Replace('${PLAYBOOK: ', '${PLAYBOOK:').Replace('${FLOW: ', '${FLOW:')
        })
    if ($currentSteps.Count -lt $desiredSteps.Count) {
        return $false
    }
    $offset = $currentSteps.Count - $desiredSteps.Count
    for ($index = 0; $index -lt $desiredSteps.Count; $index++) {
        if ($currentSteps[$offset + $index] -ne $desiredSteps[$index]) {
            return $false
        }
    }
    $currentToolSet = (@($Current.referencedTools) | Sort-Object) -join "`n"
    $desiredToolSet = (@($Desired.referencedTools) | Sort-Object) -join "`n"
    $guidelinesMatch = (
        $Current.instruction.guidelines -eq $Desired.instruction.guidelines -or
        ($AllowMissingGuidelines -and [string]::IsNullOrWhiteSpace($Current.instruction.guidelines))
    )
    return (
        $Current.goal -eq $Desired.goal -and
        $Current.playbookType -eq $Desired.playbookType -and
        $guidelinesMatch -and
        $currentToolSet -eq $desiredToolSet
    )
}

foreach ($definition in @($catalog.playbooks | Where-Object { -not $_.default })) {
    $body = New-PlaybookBody -Definition $definition
    if ($playbookResources.ContainsKey($definition.name)) {
        if (Test-PlaybookAlreadyCurrent -Current $playbookSnapshots[$definition.name] -Desired $body) {
            continue
        }
        $resourceName = $playbookResources[$definition.name]
        # Address nested instruction fields explicitly. Masking the parent
        # message can append repeated steps instead of replacing them.
        $updateFields = @(
            'displayName',
            'goal',
            'instruction.guidelines',
            'instruction.steps',
            'playbookType'
        )
        $desiredTools = @($body.referencedTools)
        $currentTools = @($playbookReferencedTools[$definition.name])
        $currentToolSet = ($currentTools | Sort-Object) -join "`n"
        $desiredToolSet = ($desiredTools | Sort-Object) -join "`n"
        # Dialogflow re-resolves ${TOOL: ...} references whenever instruction is
        # patched. Include referencedTools even when unchanged so the resolver
        # validates against the current agent draft instead of a stale reference.
        if ($desiredTools.Count -gt 0 -or $currentTools.Count -gt 0) {
            $updateFields += 'referencedTools'
        }
        else {
            $body.Remove('referencedTools')
        }
        $uri = "$endpoint/v3/$resourceName`?updateMask=$($updateFields -join ',')"
        $updated = Invoke-DialogflowApi -Method Patch -Uri $uri -Body $body
        $playbookResources[$definition.name] = $updated.name
    }
    else {
        $created = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/playbooks" -Body $body
        $playbookResources[$definition.name] = $created.name
    }
}

function Sync-PlaybookExamples {
    param([Parameter(Mandatory = $true)][object]$Definition)

    $parent = $playbookResources[$Definition.name]
    $examplesResponse = Invoke-DialogflowApi -Method Get -Uri "$endpoint/v3/$parent/examples?pageSize=100"
    $exampleResources = @{}
    foreach ($existingExample in @($examplesResponse.examples)) {
        if ($null -ne $existingExample) {
            $exampleResources[$existingExample.displayName] = $existingExample.name
        }
    }

    foreach ($example in @($Definition.examples)) {
        $actions = @()
        if ($null -ne $example.agent_before_user) {
            $actions += @{ agentUtterance = @{ text = $example.agent_before_user } }
        }
        $actions += @{ userUtterance = @{ text = $example.user } }
        if ($null -ne $example.route_to) {
            $target = $playbookResources[$example.route_to]
            if ([string]::IsNullOrWhiteSpace($target)) {
                throw "Example '$($example.name)' references unknown playbook '$($example.route_to)'."
            }
            $invocation = @{
                playbook = $target
                playbookState = "OUTPUT_STATE_$($example.state)"
            }
            if ($null -ne $example.summary) {
                $invocation.playbookInput = @{ precedingConversationSummary = $example.summary }
            }
            if ($null -ne $example.output_summary) {
                $invocation.playbookOutput = @{ executionSummary = $example.output_summary }
            }
            $actions += @{ playbookInvocation = $invocation }
        }
        elseif ($null -ne $example.tool) {
            $toolResource = $toolResources[$example.tool.name]
            if ([string]::IsNullOrWhiteSpace($toolResource)) {
                throw "Example '$($example.name)' references unknown tool '$($example.tool.name)'."
            }
            $outputParameterName = "$($example.tool.action) output"
            $outputActionParameters = @{}
            $outputActionParameters[$outputParameterName] = $example.tool.output
            $toolUse = @{
                tool = $toolResource
                action = $example.tool.action
                inputActionParameters = $example.tool.input
                outputActionParameters = $outputActionParameters
            }
            $actions += @{ toolUse = $toolUse }
            if ($null -ne $example.agent) {
                $actions += @{ agentUtterance = @{ text = $example.agent } }
            }
        }
        elseif ($null -ne $example.flow) {
            $flowResource = $flowResources[$example.flow.name]
            if ([string]::IsNullOrWhiteSpace($flowResource)) {
                throw "Example '$($example.name)' references unknown flow '$($example.flow.name)'."
            }
            $actions += @{
                flowInvocation = @{
                    flow = $flowResource
                    inputActionParameters = $example.flow.input
                    outputActionParameters = $example.flow.output
                    flowState = "OUTPUT_STATE_$($example.state)"
                }
            }
            if ($null -ne $example.agent) {
                $actions += @{ agentUtterance = @{ text = $example.agent } }
            }
        }
        elseif ($null -ne $example.agent) {
            $actions += @{ agentUtterance = @{ text = $example.agent } }
        }
        else {
            throw "Example '$($example.name)' must contain route_to or agent."
        }

        $exampleBody = @{
            displayName = $example.name
            description = "ServicePilot routing, tool, and safety example."
            actions = $actions
            conversationState = "OUTPUT_STATE_$($example.state)"
            languageCode = $catalog.agent.default_language_code
        }
        if ($null -ne $example.output_summary) {
            $exampleBody.playbookOutput = @{ executionSummary = $example.output_summary }
        }
        if ($null -ne $example.input_summary) {
            $exampleBody.playbookInput = @{
                precedingConversationSummary = $example.input_summary
            }
        }

        if ($exampleResources.ContainsKey($example.name)) {
            $exampleName = $exampleResources[$example.name]
            # Dialogflow appends repeated actions during PATCH instead of replacing
            # them. Recreate the example to keep ordered actions deterministic.
            Invoke-DialogflowApi -Method Delete -Uri "$endpoint/v3/$exampleName" | Out-Null
        }
        Invoke-DialogflowApi -Method Post -Uri "$endpoint/v3/$parent/examples" -Body $exampleBody | Out-Null
    }
}

# Examples make newly created task playbooks fully resolvable before DefaultService
# references them. This also avoids eventual-consistency failures in Dialogflow.
foreach ($definition in @($catalog.playbooks | Where-Object { -not $_.default })) {
    Sync-PlaybookExamples -Definition $definition
}

$defaultDefinition = $catalog.playbooks | Where-Object { $_.default } | Select-Object -First 1
$defaultBody = New-PlaybookBody -Definition $defaultDefinition
if ($playbookResources.ContainsKey($defaultDefinition.name) -and
    $playbookResources[$defaultDefinition.name] -ne $reservedDefaultResource) {
    throw "A non-default playbook already uses the reserved name '$($defaultDefinition.name)'."
}
if ($reservedDefaultExists) {
    $defaultResource = $reservedDefaultResource
    if (-not (Test-PlaybookAlreadyCurrent -Current $playbookSnapshots[$defaultDefinition.name] -Desired $defaultBody -AllowMissingGuidelines)) {
        $defaultUri = "$endpoint/v3/$reservedDefaultResource`?updateMask=displayName,goal,instruction.guidelines,instruction.steps,playbookType,referencedTools"
        $updatedDefault = Invoke-DialogflowApi -Method Patch -Uri $defaultUri -Body $defaultBody
        $defaultResource = $updatedDefault.name
    }
}
else {
    $defaultBody.name = $reservedDefaultResource
    $createdDefault = Invoke-DialogflowApi -Method Post -Uri "$apiRoot/playbooks" -Body $defaultBody
    $defaultResource = $createdDefault.name
}
$playbookResources[$defaultDefinition.name] = $defaultResource

$agentBody = @{ name = $agentResource; startPlaybook = $defaultResource }
$agentUri = "$apiRoot`?updateMask=startPlaybook"
Invoke-DialogflowApi -Method Patch -Uri $agentUri -Body $agentBody | Out-Null
Sync-PlaybookExamples -Definition $defaultDefinition

[pscustomobject]@{
    agent = $agentResource
    playbooks = @($playbookResources.Keys | Sort-Object)
    tools = @($toolResources.Keys | Sort-Object)
    flows = @($flowResources.Keys | Sort-Object)
    examples = (@($catalog.playbooks | ForEach-Object { $_.examples.Count }) | Measure-Object -Sum).Sum
}
