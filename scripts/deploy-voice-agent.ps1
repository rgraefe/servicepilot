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

    [string]$ProfilePath = (Join-Path $PSScriptRoot '..\conversation\voice-profile.json')
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'gcloud CLI was not found on PATH.'
}

$resolvedProfilePath = (Resolve-Path -LiteralPath $ProfilePath).Path
$profile = Get-Content -Raw -LiteralPath $resolvedProfilePath | ConvertFrom-Json -Depth 20
if ($profile.schema_version -ne 1 -or $profile.language_code -ne 'de') {
    throw 'The Phase 9 voice profile must use schema version 1 and language de.'
}

$agentResource = "projects/$ProjectId/locations/$Region/agents/$AgentId"
if (-not $PSCmdlet.ShouldProcess($agentResource, 'Apply ServicePilot Phase 9 speech settings')) {
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

$language = $profile.language_code
$synthesizeSpeechConfigs = @{}
$synthesizeSpeechConfigs[$language] = @{
    speakingRate = [double]$profile.output.speaking_rate
    pitch = [double]$profile.output.pitch
    volumeGainDb = [double]$profile.output.volume_gain_db
}
$models = @{}
$models[$language] = [string]$profile.recognition.model

$body = @{
    name = $agentResource
    speechToTextSettings = @{
        enableSpeechAdaptation = [bool]$profile.recognition.enable_speech_adaptation
    }
    textToSpeechSettings = @{
        synthesizeSpeechConfigs = $synthesizeSpeechConfigs
    }
    advancedSettings = @{
        speechSettings = @{
            endpointerSensitivity = [int]$profile.recognition.endpointer_sensitivity
            noSpeechTimeout = "$([int]$profile.recognition.no_speech_timeout_seconds)s"
            useTimeoutBasedEndpointing = [bool]$profile.recognition.use_timeout_based_endpointing
            models = $models
        }
        loggingSettings = @{
            enableStackdriverLogging = [bool]$profile.privacy.enable_stackdriver_logging
            enableInteractionLogging = [bool]$profile.privacy.enable_interaction_logging
        }
    }
}

$endpoint = "https://$Region-dialogflow.googleapis.com"
$updateMask = 'speechToTextSettings,textToSpeechSettings,advancedSettings.speechSettings,advancedSettings.loggingSettings'
$uri = "$endpoint/v3/$agentResource`?updateMask=$updateMask"
$result = Invoke-RestMethod -Method Patch -Uri $uri -Headers $headers `
    -ContentType 'application/json; charset=utf-8' `
    -Body ($body | ConvertTo-Json -Depth 20 -Compress)

Write-Host "Voice settings applied to $($result.name)."
Write-Host "Language: $language; STT model: $($profile.recognition.model); output: LINEAR16 $($profile.output.sample_rate_hertz) Hz."
Write-Host 'Interaction/audio logging remains disabled by the version-controlled privacy profile.'
