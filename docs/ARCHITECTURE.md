# ServicePilot Architecture

## 1. Purpose

ServicePilot is a production-oriented conversational customer-service system for technical field-service organizations.

The system combines generative AI with deterministic workflows and backend services.

---

## 2. Core Principle

LLMs are used for:

- natural-language understanding
- routing
- flexible dialogue
- summarization
- knowledge retrieval orchestration
- human-friendly response generation

Deterministic application logic is used for:

- identity validation
- authorization
- record retrieval
- appointment availability
- state transitions
- ticket creation
- appointment changes
- transaction confirmation
- error handling

---

## 3. Main Components

### Conversational Layer

Google Conversational Agents / Dialogflow CX.

Components:

- Default Service Playbook
- Knowledge Support Playbook
- Service Ticket Playbook
- Appointment Management Playbook
- Complaint Management Playbook
- deterministic CX Flows for transactional operations

### Tool Layer

The conversational layer accesses business capabilities through explicit tools.

Examples:

- get_customer
- get_customer_devices
- get_ticket
- list_customer_tickets
- create_ticket
- get_appointment
- list_customer_appointments
- list_available_slots
- reschedule_appointment
- create_handover

### Backend Layer

Python/FastAPI service deployed to Google Cloud Run.

Responsibilities:

- API contracts
- validation
- business rules
- database access
- authorization
- audit-friendly error responses

### Persistence

Firestore for the initial implementation.

Collections:

- customers
- devices
- tickets
- appointments
- handovers

Each entity is accessed through a repository protocol. Phase 2 provides both
application-scoped in-memory adapters and asynchronous Firestore adapters; the
service layer is unchanged between them. The backend is selected through
`SERVICEPILOT_PERSISTENCE_BACKEND`, with memory as the safe local/test default.

Firestore uses top-level `customers`, `devices`, `tickets`, `appointments`,
`appointment_slots`, `handovers`, and `error_codes` collections. Domain IDs
are also Firestore document IDs. Appointment rescheduling runs in a Firestore
transaction which reads the canonical appointment and slots before reserving the
new slot, updating the appointment, and releasing the previous slot. Google API
failures are exposed as retryable structured 503 responses without backend detail.

### Containerization

The FastAPI image is the deployment unit for both local Compose and future Cloud
Run deployment. It runs as a non-root user, accepts environment configuration,
listens on `0.0.0.0`, and handles termination through Uvicorn. Local Compose adds
only developer conveniences (bind mounts, reload, and a healthcheck); no
Docker-specific behavior is embedded in application code.

### Cloud Deployment and Observability

Cloud Run is the production execution environment. The service is private by
default: Cloud Run IAM performs caller authentication and only explicit
`roles/run.invoker` principals may invoke it. The application does not duplicate
platform token validation. Its dedicated runtime service account accesses
Firestore through ADC and receives Secret Manager values only through explicit
Cloud Run secret mappings.

Application logs are structured JSON written to stdout for Cloud Logging ingestion.
Request records contain correlation ID, route template, method, status, protocol,
and latency. Concrete identifiers, query strings, request bodies, and customer
names are excluded. A valid Cloud Trace header is correlated through
`logging.googleapis.com/trace`.

### Knowledge Layer

Technical manuals, warranty information, FAQs, service procedures, and error-code documentation.

Initial implementation may use Google managed Data Stores.

---

## 4. Transaction Pattern

Critical actions must follow:

```text
User request
   ↓
LLM understands intent
   ↓
Read current backend state
   ↓
Validate requested action
   ↓
Present exact action
   ↓
Explicit user confirmation
   ↓
Perform deterministic write
   ↓
Verify backend response
   ↓
Respond with canonical result
```

---

## 5. Example: Appointment Rescheduling

```text
User:
"Verschieben Sie meinen Termin auf Mittwoch."

AppointmentManagement
   ↓
get_customer_appointments
   ↓
identify appointment
   ↓
list_available_slots
   ↓
offer exact Wednesday slot
   ↓
customer confirms
   ↓
deterministic CX Flow
   ↓
reschedule_appointment
   ↓
backend validates slot
   ↓
backend returns updated appointment
   ↓
agent confirms
```

---

## 6. Example: Technical Error

```text
User:
"Meine Wärmepumpe zeigt E37."

DefaultService
   ↓
KnowledgeSupport
   ↓
identify device
   ↓
retrieve documentation
   ↓
explain error
   ↓
if technician required:
       check active ticket
   ↓
offer ticket creation
   ↓
confirmation
   ↓
create_ticket
```

---

## 7. Human Handover

Create a structured handover object.

Example:

```json
{
  "customer_id": "C-10023",
  "reason": "technical_escalation",
  "conversation_summary": "Customer reports recurring E37 on HeatPump-X200.",
  "ticket_id": "T-9321",
  "priority": "normal"
}
```

The goal is to avoid forcing a human agent to restart the conversation.

---

## 8. Voice Considerations

Voice adds requirements beyond chat:

- streaming STT
- streaming TTS
- endpointing
- interruptions / barge-in
- latency management
- speech recognition for IDs and serial numbers
- partial transcripts
- call termination
- human transfer

Agent business logic should remain reusable across chat and voice channels.
