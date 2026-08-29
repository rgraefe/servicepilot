# Tool Contracts

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

## list_available_slots

Input:

```json
{
  "customer_id": "C-10023",
  "from_date": "2026-08-17",
  "to_date": "2026-08-21"
}
```

Output:

```json
{
  "slots": [
    {
      "slot_id": "S-101",
      "start": "2026-08-19T14:00:00+02:00",
      "end": "2026-08-19T15:00:00+02:00"
    }
  ]
}
```

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

---

## create_handover

Input:

```json
{
  "customer_id": "C-10023",
  "reason": "technical_escalation",
  "summary": "Customer reports recurring E37.",
  "ticket_id": "T-9321"
}
```

Output:

```json
{
  "handover_id": "H-1001",
  "status": "queued"
}
```
