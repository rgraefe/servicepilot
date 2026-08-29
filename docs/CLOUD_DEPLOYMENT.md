# Cloud Run Deployment

## Deployment model

ServicePilot is deployed as the same non-root container used locally. Cloud Run
injects `PORT`, provides the runtime service identity through Application Default
Credentials, captures structured JSON written to stdout, and enforces caller
authentication through IAM.

The deployment script always uses `--no-allow-unauthenticated`. Do not add an
`allUsers` invoker binding. Approved humans or workloads receive
`roles/run.invoker` explicitly and call the service with a Google-signed ID
token whose audience is the service URL.

References:

- [Deploying container images to Cloud Run](https://cloud.google.com/run/docs/deploying)
- [Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Configuring Secret Manager secrets for Cloud Run](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Run structured logging](https://cloud.google.com/run/docs/logging)

## Required access details

Before a live deployment, provide or decide:

1. Google Cloud project ID
2. Cloud Run and Artifact Registry region
3. Cloud Run service name
4. Artifact Registry repository name
5. runtime service-account email
6. approved invoker principals, such as
   `serviceAccount:dialogflow-tools@example.iam.gserviceaccount.com`
7. any Secret Manager mappings in `ENV_VAR=secret-name:version` form
8. desired ingress policy: `all`, `internal`, or
   `internal-and-cloud-load-balancing`

An authenticated `gcloud` CLI is required. The deploying identity needs the
organization-approved equivalent of Cloud Run deployment, Cloud Build submission,
Artifact Registry upload, and `iam.serviceAccounts.actAs` permissions for the
runtime identity. Exact role grants should be assigned by the project administrator
under least privilege.

## One-time project preparation

Set shell variables appropriate to the target environment:

```powershell
$ProjectId = 'your-project-id'
$Region = 'europe-west3'
$Repository = 'servicepilot'
$RuntimeServiceAccount = 'servicepilot-runtime@your-project-id.iam.gserviceaccount.com'
gcloud auth login
gcloud config set project $ProjectId
```

Enable the required APIs:

```powershell
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com firestore.googleapis.com secretmanager.googleapis.com --project $ProjectId
```

Create the Docker repository if it does not exist:

```powershell
gcloud artifacts repositories create $Repository --repository-format=docker --location=$Region --project=$ProjectId
```

Create or select a dedicated runtime service account. It needs Firestore data
access. Avoid using the project default service account:

```powershell
gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$RuntimeServiceAccount" --role=roles/datastore.user
```

For each secret used by the application, grant access to that individual secret,
not all secrets in the project:

```powershell
$SecretName = 'servicepilot-integration-api-key'
gcloud secrets add-iam-policy-binding $SecretName --project=$ProjectId --member="serviceAccount:$RuntimeServiceAccount" --role=roles/secretmanager.secretAccessor
```

ServicePilot currently needs no application secret for its core API. Secret
mappings exist for later authenticated integrations and must only be added when a
consumer is implemented.

Phase 5 does not use a shared secret for Dialogflow. Its tool deployment grants
`roles/run.invoker` directly to
`service-PROJECT_NUMBER@gcp-sa-dialogflow.iam.gserviceaccount.com` and configures
Dialogflow to send a Google-signed ID token. Keep the Cloud Run service private;
do not grant `allUsers` access.

## Build and deploy

Run the complete containerized tests first:

```powershell
docker compose build
docker compose run --rm api pytest
```

Preview the deployment without making changes:

```powershell
./scripts/deploy-cloud-run.ps1 -ProjectId $ProjectId -Region $Region -ServiceName servicepilot-api -RuntimeServiceAccount $RuntimeServiceAccount -ArtifactRepository $Repository -WhatIf
```

Deploy a private service and grant one caller invocation access:

```powershell
./scripts/deploy-cloud-run.ps1 -ProjectId $ProjectId -Region $Region -ServiceName servicepilot-api -RuntimeServiceAccount $RuntimeServiceAccount -ArtifactRepository $Repository -Invoker 'serviceAccount:approved-caller@your-project-id.iam.gserviceaccount.com'
```

To inject an existing Secret Manager version as an environment variable:

```powershell
./scripts/deploy-cloud-run.ps1 -ProjectId $ProjectId -Region $Region -ServiceName servicepilot-api -RuntimeServiceAccount $RuntimeServiceAccount -Secret 'INTEGRATION_API_KEY=servicepilot-integration-api-key:latest'
```

The script:

1. verifies that the Artifact Registry repository exists
2. builds the production Dockerfile with Cloud Build
3. deploys the image with Firestore configuration and the dedicated identity
4. keeps the IAM invoker check enabled
5. attaches only explicitly supplied secrets
6. grants `roles/run.invoker` only to supplied principals
7. prints the canonical service URL

## Seed Firestore

Use the explicit Phase 2 seed command from a trusted local environment. Seeding is
not part of deployment and never runs on API startup:

```powershell
$env:SERVICEPILOT_FIRESTORE_PROJECT = $ProjectId
$env:SERVICEPILOT_GOOGLE_CREDENTIALS_FILE = 'C:/absolute/path/to/adc.json'
docker compose -f compose.yaml -f compose.firestore.yaml run --rm api python -m app.seed --confirm
```

The calling identity needs Firestore write access.

## Verify authentication and health

Read the deployed URL:

```powershell
$ServiceUrl = gcloud run services describe servicepilot-api --project=$ProjectId --region=$Region --format='value(status.url)'
```

An unauthenticated request must fail:

```powershell
Invoke-WebRequest "$ServiceUrl/health"
```

An approved principal with `roles/run.invoker` can obtain an ID token and call
the service:

```powershell
$IdentityToken = gcloud auth print-identity-token
Invoke-RestMethod "$ServiceUrl/health" -Headers @{ Authorization = "Bearer $IdentityToken" }
```

The expected response reports `environment: production` and
`persistence_backend: firestore`.

## Logging and operations

Application request logs are emitted as one-line JSON to stdout. Cloud Logging
parses them into `jsonPayload`. Fields include:

- `severity`
- `timestamp`
- `event`
- `request_id`
- sanitized route template
- `httpRequest.requestMethod`, status, protocol, and latency
- `logging.googleapis.com/trace` when Cloud Trace context is available

Request bodies, query strings, customer names, and concrete path identifiers are
not logged.

Read recent logs:

```powershell
gcloud run services logs read servicepilot-api --project=$ProjectId --region=$Region --limit=100
```

List revisions before a rollback:

```powershell
gcloud run revisions list --service=servicepilot-api --project=$ProjectId --region=$Region
```

Move traffic to a known-good revision:

```powershell
gcloud run services update-traffic servicepilot-api --project=$ProjectId --region=$Region --to-revisions=KNOWN_GOOD_REVISION=100
```
