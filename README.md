# ServicePilot

ServicePilot is a production-oriented customer-service backend that keeps business
transactions deterministic while remaining ready for later conversational-agent
integration. Phase 2 supports both application-scoped in-memory repositories and
Google Cloud Firestore behind the same service-layer interfaces.

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2
- An available local TCP port 8000 (or set `SERVICEPILOT_PORT` to another host port)

No host Python installation is required for the supported workflow.

## Configure the environment

Copy `.env.example` to `.env` to override defaults. Compose also works without
an `.env` file. Configuration uses `SERVICEPILOT_`-prefixed environment
variables; `.env` is ignored by Git and must never contain committed secrets.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SERVICEPILOT_ENVIRONMENT` | `development` | Runtime environment label |
| `SERVICEPILOT_LOG_LEVEL` | `INFO` | Application log level |
| `SERVICEPILOT_PORT` | `8000` | Host port published by Compose |
| `SERVICEPILOT_RELOAD` | `true` | Enable source reload in local Compose |
| `SERVICEPILOT_PERSISTENCE_BACKEND` | `memory` | Select `memory` or `firestore` |
| `SERVICEPILOT_FIRESTORE_PROJECT` | unset | Google Cloud project; ADC may infer it |
| `SERVICEPILOT_FIRESTORE_DATABASE` | `(default)` | Firestore database identifier |
| `SERVICEPILOT_GOOGLE_CREDENTIALS_FILE` | unset | Compose-only absolute host credential path |

Cloud Run can supply `PORT`; the image otherwise uses `SERVICEPILOT_PORT`. The
application itself is not Docker-dependent and can also run with
`uvicorn app.main:app`.

## Docker development workflow

Build the image:

```bash
docker compose build
```

Start the API:

```bash
docker compose up
```

Source and test directories are bind-mounted and Uvicorn reload is enabled by
default, so Python changes normally do not require an image rebuild. Rebuild after
changing dependencies or the Dockerfile.

Stop and remove the Compose containers and network:

```bash
docker compose down
```

Run the complete test suite inside the image:

```bash
docker compose run --rm api pytest
```

Inspect live logs:

```bash
docker compose logs --follow api
```

## Local URLs

- API base: <http://localhost:8000>
- Health: <http://localhost:8000/health>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

If `SERVICEPILOT_PORT` changes, replace `8000` with that host port.

## Business API

The validated demo dataset contains 5 customers, 8 devices, 10 tickets,
8 appointments, appointment slots, and 4 technical error-code examples. Useful
identifiers include customer `C-10023`, device `D-1007`, ticket `T-4711`,
appointment `A-0815`, and slots `S-101` and `S-102`. In-memory state resets
whenever the API process restarts.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Container and service health |
| `GET` | `/customers/{customer_id}` | Retrieve a customer |
| `GET` | `/customers/{customer_id}/devices` | List owned devices |
| `GET` | `/customers/{customer_id}/tickets` | List customer tickets |
| `GET` | `/customers/{customer_id}/appointments` | List appointments |
| `GET` | `/tickets/{ticket_id}` | Retrieve a ticket |
| `POST` | `/tickets` | Create a validated ticket |
| `GET` | `/appointments/{appointment_id}` | Retrieve an appointment |
| `GET` | `/appointments/available-slots` | List slots in a date range |
| `PUT` | `/appointments/{appointment_id}` | Confirm and reschedule |
| `POST` | `/handover` | Queue a structured handover |

Business and validation failures use a structured `error` object with `code`,
`message`, and `retryable` fields. Writes return the canonical created or
updated entity.

## Container architecture

`compose.yaml` currently defines only `api`. The service name and default
Compose network leave room for later `postgres`, `mock-services`,
`mcp-server`, and other supporting services without changing the API image.
Compose adds development bind mounts and reload; the Dockerfile defaults to a
production-oriented, non-root, single-process image suitable for Cloud Run.

## Firestore persistence

Memory mode remains the zero-configuration default for development and tests.
Firestore mode uses Application Default Credentials (ADC); no credential is copied
into the image. Create a Firestore Native Mode database, grant the runtime identity
only the required document permissions, and keep credential JSON files outside the
repository.

For local Docker Compose, set these values in the shell or `.env`:

```text
SERVICEPILOT_FIRESTORE_PROJECT=your-project-id
SERVICEPILOT_GOOGLE_CREDENTIALS_FILE=/absolute/host/path/to/adc.json
```

Then start with the credentials-only Compose override:

```bash
docker compose -f compose.yaml -f compose.firestore.yaml up
```

The override mounts the credential read-only and sets
`GOOGLE_APPLICATION_CREDENTIALS` inside the container. Cloud Run should use its
attached service account and the base image directly, without this override.

Load or restore the deterministic demo dataset explicitly:

```bash
docker compose -f compose.yaml -f compose.firestore.yaml run --rm api python -m app.seed --confirm
```

Seeding validates the JSON through the domain models and performs idempotent
document upserts for `customers`, `devices`, `tickets`, `appointments`,
`appointment_slots`, and `error_codes`. It never runs automatically on API
startup. The health response reports the selected persistence backend.

## Cloud Run deployment

Phase 3 provides structured JSON request logging and a private Cloud Run deployment
script. The deployment uses a dedicated runtime service account, Firestore through
ADC, optional Secret Manager environment injection, and explicit
`roles/run.invoker` grants. It never enables unauthenticated access.

See [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) for project preparation,
least-privilege IAM, deployment, authenticated health verification, logging, and
rollback instructions.

Preview a deployment:

```powershell
./scripts/deploy-cloud-run.ps1 -ProjectId your-project-id -Region europe-west3 -ServiceName servicepilot-api -RuntimeServiceAccount servicepilot-runtime@your-project-id.iam.gserviceaccount.com -WhatIf
```
