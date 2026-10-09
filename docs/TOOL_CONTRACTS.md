# Tool Contracts

## `ServicePilotKnowledge`

Dialogflow tool type: Data Store (`UNSTRUCTURED`) with document processing mode
`CHUNKS`. The mode must match the layout-aware chunked Agent Search data store;
omitting it falls back to legacy `DOCUMENTS` processing and can make Dialogflow
return an empty search result even while direct Agent Search queries succeed.
Input example:

```json
{"requestBody": {"query": "HeatPump-X200 Fehler E37 sichere Erstmaßnahmen"}}
```

The query includes exact model, code, and symptom when known. Output is accepted
as factual support only when it contains a matching snippet and verifiable
document title/source URI. Empty, fallback, or conflicting results never
authorize a technical claim. For conflicts across models, KnowledgeSupport asks
for the model. This tool performs no business transaction and is safe to retry
once with a meaningfully corrected query.

For model-dependent error-code questions, an explicit or previously verified
model is a precondition for the tool call. KnowledgeSupport must not infer a
model from the code, retrieval ranking, demo data, or the first result. If the
model is missing, it asks for the exact model and ends the turn without calling
the tool.

## General Rules

Tools must:

- have narrow responsibilities
- use explicit schemas
- return canonical backend data
- return machine-readable errors
- never hide failed writes behind HTTP 200 responses
- avoid natural-language-only responses

## Phase 1 HTTP Mapping

The Phase 1 FastAPI endpoints expose these contracts directly. Collection-list
responses are JSON arrays. All failures use a structured `error` object with
`code`, `message`, and `retryable` fields. Schema failures use
`VALIDATION_ERROR` and include machine-readable `details`. Firestore/API
availability failures use HTTP 503 with `PERSISTENCE_UNAVAILABLE` and
`retryable: true`; provider details are not returned to callers.

## Phase 5 Dialogflow mapping

`conversation/servicepilot-openapi.json` exposes the existing HTTP contracts as
the authenticated `ServicePilotBackend` OpenAPI tool. The server URL in source is
a non-routable placeholder and is replaced with the canonical Cloud Run URL only
during deployment. Authentication is configured outside the OpenAPI document as
Dialogflow service-agent `ID_TOKEN`; the schema contains no credentials.

| Tool action | HTTP operation | Phase 5 caller |
| --- | --- | --- |
| `get_customer` | `GET /customers/{customer_id}` | ServiceTicket |
| `get_ticket` | `GET /tickets/{ticket_id}` | ServiceTicket |
| `create_ticket` | `POST /tickets` | ServiceTicket after explicit confirmation |
| `get_appointments` | `GET /customers/{customer_id}/appointments` | AppointmentManagement |
| `get_appointment` | `GET /appointments/{appointment_id}` | AppointmentManagement |
| `list_available_slots` | `GET /appointments/available-slots` | AppointmentManagement |
| `get_appointment_slot` | `GET /appointments/slots/{slot_id}` | AppointmentManagement before reschedule flow |
| `reschedule_appointment` | `PUT /appointments/{appointment_id}` | Phase 6 `AppointmentReschedule` flow only |
| `create_handover` | `POST /handover` | All specialist playbooks when an escalation condition is met |

List operations return JSON arrays because they map directly to the FastAPI
contracts. An empty array is a successful result with no matching records. Any
non-2xx response remains a structured failure and must not be interpreted as
successful tool output.

---

## get_customer

Input:

```json
{
  "customer_id": "C-10023"
}
```

Output:

```json
{
  "customer_id": "C-10023",
  "name": "Max Mustermann",
  "postal_code": "80331"
}
```

Errors:

- CUSTOMER_NOT_FOUND

---

## get_customer_devices

Input:

```json
{
  "customer_id": "C-10023"
}
```

Output:

```json
{
  "devices": [
    {
      "device_id": "D-1007",
      "model": "HeatPump-X200",
      "serial_number": "SN-4711"
    }
  ]
}
```

---

## get_ticket

`DefaultService` passes an explicitly supplied ticket identifier to
`ServiceTicket` as the structured `ticket_id` playbook input. When this input is
present, `ServiceTicket` calls `get_ticket` in the same conversation turn. It
must not insert an acknowledgement-only turn, call the operation twice, or add
a second response after the canonical result. The task remains active after the
single response so a ticket correction or direct follow-up stays with the
specialist instead of returning control to the parent in the same turn.

Input:

```json
{
  "ticket_id": "T-4711"
}
```

Output:

```json
{
  "ticket_id": "T-4711",
  "customer_id": "C-10023",
  "device_id": "D-1007",
  "status": "technician_assigned",
  "priority": "normal"
}
```

---

## create_ticket

Input:

```json
{
  "customer_id": "C-10023",
  "device_id": "D-1007",
  "problem_code": "E37",
  "description": "Recurring E37 error"
}
```

Output:

```json
{
  "ticket_id": "T-9321",
  "status": "created"
}
```

Errors:

- CUSTOMER_NOT_FOUND
- DEVICE_NOT_FOUND
- DEVICE_NOT_OWNED_BY_CUSTOMER
- DUPLICATE_ACTIVE_TICKET
- VALIDATION_ERROR

---

## get_appointments

Input:

```json
{
  "customer_id": "C-10023"
}
```

HTTP/tool output:

```json
[
  {
    "appointment_id": "A-0815",
    "customer_id": "C-10023",
    "device_id": "D-1007",
    "status": "scheduled",
    "start": "2026-09-02T10:00:00+02:00",
    "end": "2026-09-02T11:00:00+02:00",
    "slot_id": "S-100"
  }
]
```

Errors:

- CUSTOMER_NOT_FOUND
- VALIDATION_ERROR
- PERSISTENCE_UNAVAILABLE

---

## get_appointment

Input:

```json
{
  "appointment_id": "A-0815"
}
```

HTTP/tool output:

```json
{
  "appointment_id": "A-0815",
  "customer_id": "C-10023",
  "device_id": "D-1007",
  "status": "scheduled",
  "start": "2026-09-02T10:00:00+02:00",
  "end": "2026-09-02T11:00:00+02:00",
  "slot_id": "S-100"
}
```

The action is read-only and is used only when the customer explicitly supplied
the appointment identifier. Status and time must be taken from this canonical
response, never from conversation text.

Errors:

- APPOINTMENT_NOT_FOUND
- VALIDATION_ERROR
- PERSISTENCE_UNAVAILABLE

---

## list_available_slots

Input:

```json
{
  "customer_id": "C-10023",
  "from_date": "2026-08-17",
  "to_date": "2026-08-21"
}
```

HTTP/tool output:

```json
[
  {
    "slot_id": "S-101",
    "start": "2026-08-19T14:00:00+02:00",
    "end": "2026-08-19T15:00:00+02:00",
    "available": true
  }
]
```

---

## get_appointment_slot

Input:

```json
{
  "slot_id": "S-101",
  "customer_id": "C-10023"
}
```

HTTP/tool output:

```json
{
  "slot_id": "S-101",
  "start": "2026-09-09T14:00:00+02:00",
  "end": "2026-09-09T15:00:00+02:00",
  "available": true
}
```

`customer_id` must come from the canonical appointment response. This read is
required when a customer supplies only a slot identifier: the identifier alone
does not prove that the slot exists, is available, or has the dates remembered
by an example. An unavailable slot is returned with `available=false`; the
playbook must not invoke the reschedule flow in that case.

Errors:

- APPOINTMENT_SLOT_NOT_FOUND
- CUSTOMER_NOT_FOUND
- VALIDATION_ERROR
- PERSISTENCE_UNAVAILABLE

---

## reschedule_appointment

Input:

```json
{
  "appointment_id": "A-0815",
  "customer_id": "C-10023",
  "slot_id": "S-101",
  "confirmed": true
}
```

Rules:

- confirmed must be true
- slot must still be available
- appointment must belong to customer
- state transition must be valid

Output:

```json
{
  "appointment_id": "A-0815",
  "status": "scheduled",
  "start": "2026-08-19T14:00:00+02:00",
  "end": "2026-08-19T15:00:00+02:00"
}
```

Errors:

- APPOINTMENT_NOT_FOUND
- SLOT_UNAVAILABLE
- CONFIRMATION_REQUIRED
- INVALID_STATE_TRANSITION
- APPOINTMENT_NOT_OWNED_BY_CUSTOMER

`customer_id` is required by the Phase 1 HTTP contract so ownership is checked
in deterministic service code rather than inferred by a caller.

### Phase 6 flow mapping

AppointmentManagement first retrieves the canonical appointment and the
selected slot through read-only `get_appointment` and `get_appointment_slot`
actions. A date-range search may instead begin with `list_available_slots`. It passes `customer_id`,
`appointment_id`, the current start/end, and the selected slot's ID and
start/end to `AppointmentReschedule`.

The flow's confirmation page presents every one of those values. Only
`ConfirmAppointmentReschedule` invokes the flexible webhook:

```http
PUT /appointments/$session.params.appointment_id
```

```json
{
  "customer_id": "$session.params.customer_id",
  "slot_id": "$session.params.slot_id",
  "confirmed": true
}
```

Dialogflow authenticates using its service-agent ID token. Successful response
fields are mapped to separate `updated_*` session parameters. A success response
is emitted only when a write was attempted and the returned appointment,
customer, slot, and status match the requested canonical values. Decline,
ambiguous confirmation, missing inputs, timeout, non-success response, or a
mismatched response cannot produce a success outcome.

---

## create_handover

Input:

```json
{
  "handover_request_id": "HO-TECH-001",
  "customer_id": "C-10023",
  "reason": "technical_escalation",
  "conversation_summary": "Customer reports recurring E37.",
  "ticket_id": "T-9321",
  "context": {
    "device_model": "HeatPump-X200",
    "error_code": "E37",
    "failure_count": 2
  }
}
```

Output:

```json
{
  "handover_id": "H-1001",
  "handover_request_id": "HO-TECH-001",
  "customer_id": "C-10023",
  "reason": "technical_escalation",
  "conversation_summary": "Customer reports recurring E37.",
  "ticket_id": "T-9321",
  "context": {
    "device_model": "HeatPump-X200",
    "error_code": "E37",
    "failure_count": 2
  },
  "status": "queued",
  "priority": "high"
}
```

`customer_id` and `ticket_id` are optional so an explicit human request is never
blocked by missing identity. When supplied, customer existence, ticket existence,
and ticket ownership are validated. Reasons are `human_request`,
`technical_escalation`, `complaint`, and `repeated_failure`. Priority is backend
derived: technical escalations and complaints are `high`; human requests and
repeated failures are `normal`.

`handover_request_id` is optional for ordinary API callers but required by the
conversational contract. Reusing it with identical content returns the canonical
existing handover. Reusing it with different content returns HTTP 409
`HANDOVER_REQUEST_CONFLICT`. A timeout or unclear response may therefore be
retried once only with the identical request ID and payload.

Errors:

- `CUSTOMER_NOT_FOUND`
- `TICKET_NOT_FOUND`
- `TICKET_NOT_OWNED_BY_CUSTOMER`
- `HANDOVER_REQUEST_CONFLICT`
- `PERSISTENCE_UNAVAILABLE`
