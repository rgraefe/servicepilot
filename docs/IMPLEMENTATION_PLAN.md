# ServicePilot Implementation Plan

## Phase 1 – Local Backend

Create a FastAPI application with in-memory repositories.

Implement:

- customer retrieval
- device retrieval
- ticket retrieval
- ticket creation
- appointment retrieval
- appointment rescheduling
- handover creation

Add unit tests.

Exit criterion:

- local API runs
- OpenAPI schema is generated
- tests pass

Implementation note: Phase 1 is packaged as a Cloud Run-compatible container and
uses Docker Compose as the primary build, run, and test workflow. Persistence is
application-scoped and in-memory; no external service is required.

---

## Phase 2 – Persistent Storage

Add Firestore repository implementations.

Keep repository interfaces separate from service logic.

Seed realistic demo data:

- 5 customers
- 8 devices
- 10 tickets
- 8 appointments
- several error-code examples

Exit criterion:

- application works with Firestore
- local test mode can still use in-memory repositories

Implementation note: asynchronous Firestore repository adapters now implement the
same protocols as the in-memory adapters. A validated, explicitly invoked seed
command loads 5 customers, 8 devices, 10 tickets, 8 appointments, appointment
slots, and technical error-code examples. Memory remains the default for local
Compose and automated tests.

---

## Phase 3 – Cloud Deployment

Add:

- Dockerfile
- Cloud Run deployment instructions
- Secret Manager integration
- structured logging

Exit criterion:

- authenticated Cloud Run service is reachable from approved clients

Implementation note: the production image, private Cloud Run deployment script,
runtime service-account configuration, optional Secret Manager mappings,
structured JSON logging, trace/request correlation, IAM verification steps, and
rollback documentation are implemented. The exit criterion requires a target
project and approved credentials before it can be verified live.

---

## Phase 4 – Conversational Agent

Create:

- DefaultService Playbook
- KnowledgeSupport Playbook
- ServiceTicket Playbook
- AppointmentManagement Playbook
- ComplaintManagement Playbook

Configure clear routing and delegation.

Exit criterion:

- chat-based conversations route correctly

Implementation note: Phase 4 defines a German, playbook-first Dialogflow CX agent
as a version-controlled catalog. DefaultService is a routine router and delegates
to four narrowly scoped task playbooks. All playbooks include explicit safety,
failure, escalation, and tool-boundary rules plus at least four examples. Golden
route tests cover single intent, multi-intent, ambiguity, complaints, and explicit
human requests. An idempotent deployment script applies the catalog to an existing
playbook-first Conversational Agent without introducing Phase 5 tools.

---

## Phase 5 – Tool Integration

Expose backend operations as conversational-agent tools.

Start with:

- get_customer
- get_ticket
- create_ticket
- get_appointments
- list_available_slots
- reschedule_appointment

Exit criterion:

- agent calls backend
- missing records and validation failures are handled safely

Implementation note: Phase 5 publishes a version-controlled OpenAPI 3.0 tool
covering the six operations above. Dialogflow calls the private Cloud Run service
with a Google-signed service-agent ID token; the deployment grants only that
service agent `roles/run.invoker`. ServiceTicket uses customer and ticket reads
plus confirmed ticket creation. AppointmentManagement uses appointment and slot
reads. `reschedule_appointment` is present in the tool contract but remains
forbidden to the generative playbook until the deterministic Phase 6 flow owns it.
Structured 4xx/5xx backend errors are treated as failures, never as successful
tool results.

---

## Phase 6 – Deterministic Transaction Flow

Implement appointment rescheduling as a deterministic CX Flow.

Required sequence:

1. identify appointment
2. retrieve available slots
3. select slot
4. ask explicit confirmation
5. perform update
6. verify backend result
7. return confirmation

Exit criterion:

- no write occurs without explicit confirmation

Implementation note: Phase 6 adds the version-controlled
`AppointmentReschedule` CX Flow. AppointmentManagement performs only the
canonical appointment and slot reads, then passes the exact current and proposed
values to the flow. Only the dedicated confirmation intent invokes the
authenticated flexible webhook. The flow maps the canonical backend response,
checks appointment, customer, slot, and status before reporting success, and
returns explicit `succeeded`, `cancelled`, `failed`, or `invalid_input` outcomes.
Ambiguous answers reprompt and never call the write endpoint.

---

## Phase 7 – Knowledge / RAG

Add product manuals and service documentation.

Example documents:

- HeatPump-X200 manual
- HeatPump-X300 manual
- Warranty guide
- Error code guide
- Service FAQ

Exit criterion:

- technical answers cite or derive from managed knowledge data
- missing answers do not produce fabricated facts

Implementation status: complete. Five versioned German demo documents live
under `data/knowledge`, are rendered as PDFs, and are imported into an Agent
Search unstructured data store. Layout parsing uses 300-token child chunks with
ancestor headings. KnowledgeSupport uses the `ServicePilotKnowledge` Data Store
tool and covers cited, missing, and conflicting-result behavior.

---

## Phase 8 – Handover

Implement:

- explicit user handover
- automatic escalation after repeated failures
- complaint escalation
- technical escalation

Exit criterion:

- handover payload contains structured context and conversation summary

Implementation status: complete. `create_handover` is exposed through the
authenticated backend tool and used by KnowledgeSupport, ServiceTicket,
AppointmentManagement, and ComplaintManagement. Explicit human requests do not
require a known identity. Known customer/ticket relationships remain validated;
technical, complaint, repeated-failure, and human-request reasons are structured.
Stable request IDs make safe retries idempotent, and only a canonical `queued`
response permits the agent to report success.

---

## Phase 9 – Voice

Enable voice input/output after chat behavior is stable.

Test:

- normal speech
- slow speech
- pauses
- corrections
- interruptions
- customer IDs
- serial numbers
- backend latency

Exit criterion:

- complete voice conversation works without changing business logic

---

## Phase 10 – Regression and Failure Testing

Create at least 30 golden conversation tests.

Include:

- happy paths
- invalid identifiers
- unknown error code
- unavailable appointment slot
- backend timeout
- duplicate submission
- ambiguous confirmation
- handover
- topic switching
- repeated failure

Exit criterion:

- test suite is repeatable after prompt or flow changes

---

## Phase 11 – Optional MCP Adapter

Expose selected backend capabilities through MCP.

Use this to demonstrate interoperability, not as a replacement for clean business APIs.

---

## Phase 12 – Optional A2A

Add a separate scheduling agent or field-service-planning agent.

Use A2A only where the remote component is meaningfully autonomous.
