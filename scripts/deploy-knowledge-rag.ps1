[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')][string]$ProjectId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z]+-[a-z]+[0-9]$')][string]$AgentRegion,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$AgentId,
    [string]$DataStoreLocation = 'eu',
    [ValidatePattern('^[a-z][a-z0-9-]{2,62}$')][string]$DataStoreId = 'servicepilot-knowledge',
    [string]$BucketName = "$ProjectId-servicepilot-knowledge",
    [string]$CorpusPath = (Join-Path $PSScriptRoot '..\data\knowledge')
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw 'gcloud CLI was not found on PATH.' }
$corpus = (Resolve-Path -LiteralPath $CorpusPath).Path
$manifest = Get-Content -Raw -LiteralPath (Join-Path $corpus 'corpus.json') | ConvertFrom-Json -Depth 100
if (-not $manifest.chunking.include_ancestor_headings) { throw 'Corpus must enable ancestor headings.' }
$chunkSize = [int]$manifest.chunking.chunk_size_tokens
if ($chunkSize -lt 100 -or $chunkSize -gt 500) { throw 'Agent Search layout chunk size must be between 100 and 500.' }
foreach ($document in $manifest.documents) {
    if (-not (Test-Path -LiteralPath (Join-Path $corpus $document.pdf))) { throw "Missing PDF: $($document.pdf)" }
}

$target = "projects/$ProjectId/locations/$DataStoreLocation/dataStores/$DataStoreId"
if (-not $PSCmdlet.ShouldProcess($target, 'Create/update the managed RAG store, import PDFs, and deploy the Dialogflow data-store tool')) { return }

function Invoke-Gcloud([string[]]$Arguments) {
    $value = & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud command failed: gcloud $($Arguments -join ' ')" }
    return $value
}
Invoke-Gcloud @('services','enable','discoveryengine.googleapis.com','storage.googleapis.com','dialogflow.googleapis.com',"--project=$ProjectId") | Out-Null
$projectNumber = (Invoke-Gcloud @('projects','describe',$ProjectId,'--format=value(projectNumber)') | Out-String).Trim()
$token = (Invoke-Gcloud @('auth','print-access-token') | Out-String).Trim()
$headers = @{ Authorization = "Bearer $token"; 'x-goog-user-project' = $ProjectId }

function Invoke-GoogleApi([string]$Method, [string]$Uri, [object]$Body = $null) {
    $args = @{ Method=$Method; Uri=$Uri; Headers=$headers; ContentType='application/json; charset=utf-8' }
    if ($null -ne $Body) { $args.Body = $Body | ConvertTo-Json -Depth 100 -Compress }
    try { return Invoke-RestMethod @args }
    catch { throw "Google API $Method '$Uri' failed ($($_.Exception.Response.StatusCode)): $($_.ErrorDetails.Message)" }
}

$bucketUri = "gs://$BucketName"
& gcloud storage buckets describe $bucketUri "--project=$ProjectId" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud @('storage','buckets','create',$bucketUri,"--project=$ProjectId",'--location=EU','--uniform-bucket-level-access') | Out-Null
}
Invoke-Gcloud @('storage','cp',(Join-Path $corpus 'documents\*.pdf'),"$bucketUri/documents/") | Out-Null

$metadataPath = Join-Path ([System.IO.Path]::GetTempPath()) "servicepilot-knowledge-$PID.ndjson"
try {
    $rows = foreach ($document in $manifest.documents) {
        @{
            id = $document.id
            structData = @{ title=$document.title; version=$document.version; model=$document.model; document_type=$document.document_type; language='de' }
            content = @{ mimeType='application/pdf'; uri="$bucketUri/$($document.pdf -replace '\\','/')" }
        } | ConvertTo-Json -Depth 10 -Compress
    }
    [System.IO.File]::WriteAllLines($metadataPath, $rows, [System.Text.UTF8Encoding]::new($false))
    Invoke-Gcloud @('storage','cp',$metadataPath,"$bucketUri/metadata/corpus.ndjson") | Out-Null
}
finally { Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue }

$discoveryRoot = "https://$DataStoreLocation-discoveryengine.googleapis.com/v1/projects/$ProjectId/locations/$DataStoreLocation/collections/default_collection"
try { $store = Invoke-GoogleApi 'Get' "$discoveryRoot/dataStores/$DataStoreId" }
catch {
    if ($_ -notmatch '\(NotFound\)|\(404\)') { throw }
    $storeBody = @{
        displayName='ServicePilot Knowledge'; industryVertical='GENERIC'; solutionTypes=@('SOLUTION_TYPE_SEARCH'); contentConfig='CONTENT_REQUIRED'
        documentProcessingConfig=@{
            chunkingConfig=@{ layoutBasedChunkingConfig=@{ chunkSize=$chunkSize; includeAncestorHeadings=$true } }
            defaultParsingConfig=@{ layoutParsingConfig=@{} }
        }
    }
    Invoke-GoogleApi 'Post' "$discoveryRoot/dataStores?dataStoreId=$DataStoreId" $storeBody | Out-Null
    Write-Host 'Data store creation started; waiting briefly for the resource to become available.'
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 2
        try { $store = Invoke-GoogleApi 'Get' "$discoveryRoot/dataStores/$DataStoreId"; break } catch { if ($attempt -eq 29) { throw } }
    }
}
$layout = $store.documentProcessingConfig.chunkingConfig.layoutBasedChunkingConfig
if ($layout.chunkSize -ne $chunkSize -or -not $layout.includeAncestorHeadings) {
    throw 'Existing data store does not match the required hierarchical chunking contract. Create a new data-store ID.'
}
$importBody = @{
    gcsSource=@{ inputUris=@("$bucketUri/metadata/corpus.ndjson"); dataSchema='document' }
    reconciliationMode='INCREMENTAL'
}
$import = Invoke-GoogleApi 'Post' "$discoveryRoot/dataStores/$DataStoreId/branches/default_branch/documents:import" $importBody

$agentRoot = "https://$AgentRegion-dialogflow.googleapis.com/v3/projects/$ProjectId/locations/$AgentRegion/agents/$AgentId"
$toolBody = @{
    displayName='ServicePilotKnowledge'
    description='Managed, citation-bearing retrieval over approved ServicePilot manuals. Input query must include model and error code when known.'
    dataStoreSpec=@{ dataStoreConnections=@(@{
        dataStoreType='UNSTRUCTURED'
        dataStore="projects/$projectNumber/locations/$DataStoreLocation/collections/default_collection/dataStores/$DataStoreId"
        documentProcessingMode='CHUNKS'
    }) }
}
$tools = Invoke-GoogleApi 'Get' "$agentRoot/tools?pageSize=100"
$existing = @($tools.tools) | Where-Object displayName -eq $toolBody.displayName | Select-Object -First 1
if ($null -eq $existing) { $tool = Invoke-GoogleApi 'Post' "$agentRoot/tools" $toolBody }
else { $tool = Invoke-GoogleApi 'Patch' "https://$AgentRegion-dialogflow.googleapis.com/v3/$($existing.name)?updateMask=displayName,description,dataStoreSpec" $toolBody }

[pscustomobject]@{
    data_store = "projects/$projectNumber/locations/$DataStoreLocation/collections/default_collection/dataStores/$DataStoreId"
    bucket = $bucketUri
    imported_documents = @($manifest.documents).Count
    import_operation = $import.name
    tool = $tool.name
    note = 'Indexing is asynchronous; deploy playbooks after the import operation has completed.'
}
