[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$DataStoreLocation = 'eu',
    [string]$DataStoreId = 'servicepilot-knowledge'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw 'gcloud CLI was not found on PATH.' }
$projectNumber = (& gcloud projects describe $ProjectId '--format=value(projectNumber)' | Out-String).Trim()
$token = (& gcloud auth print-access-token | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'Unable to obtain a Google Cloud access token.' }
$headers = @{ Authorization="Bearer $token"; 'x-goog-user-project'=$ProjectId }
$uri = "https://$DataStoreLocation-discoveryengine.googleapis.com/v1/projects/$projectNumber/locations/$DataStoreLocation/collections/default_collection/dataStores/$DataStoreId/servingConfigs/default_search`:search"

function Search-Knowledge([string]$Query) {
    $body = @{
        query=$Query
        pageSize=5
        contentSearchSpec=@{ snippetSpec=@{ returnSnippet=$true } }
    } | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Method Post -Headers $headers -ContentType 'application/json' -Uri $uri -Body $body
}

$x200 = Search-Knowledge 'HeatPump-X200 Fehler E37 Volumenstrom'
$titles = @($x200.results | ForEach-Object { $_.document.derivedStructData.title })
if ($titles[0] -ne 'HeatPump-X200 Bedienungs- und Servicehandbuch') {
    throw "Unexpected top result for X200 E37: '$($titles[0])'."
}
if ($x200.results[0].document.derivedStructData.snippets[0].snippet -notmatch 'Volumenstrom') {
    throw 'Top X200 result does not contain the expected E37 snippet.'
}

$conflict = Search-Knowledge 'Fehler E37 Bedeutung Gerätemodell'
$conflictTitles = @($conflict.results | ForEach-Object { $_.document.derivedStructData.title })
if ('HeatPump-X200 Bedienungs- und Servicehandbuch' -notin $conflictTitles -or
    'HeatPump-X300 Bedienungs- und Servicehandbuch' -notin $conflictTitles) {
    throw 'The model-ambiguous E37 query did not retrieve both model manuals.'
}

[pscustomobject]@{
    x200_top_result = $titles[0]
    x200_snippet_verified = $true
    ambiguous_e37_retrieves_both_models = $true
    edition = 'standard (no extractive/enterprise search features)'
}
