# Test Strategy

## Test Pyramid

### Unit Tests

Test:

- Pydantic models
- validation rules
- authorization rules
- service-layer behavior
- repository behavior
- state transitions

### Integration Tests

Test:

- API endpoints
- repository integration
- structured error responses
- idempotency
- backend failure handling

Phase 2 additionally tests Firestore serialization, queries, canonical writes,
transactional slot reservation, adapter selection, seed-data integrity, and safe
Google API failure mapping with local fakes. The default suite requires neither
credentials nor a live Google Cloud project.

Phase 3 tests the JSON log schema, request-ID handling, Cloud Trace correlation,
route-template redaction, retry-safe existing APIs, and security-critical
deployment flags. The production image is also smoke-tested locally before a live
Cloud Run deployment.

### Conversation Tests

Maintain golden conversations covering expected agent behavior.

Phase 4 adds a version-controlled German routing corpus and validates it against
a deterministic ownership contract in Docker. These fast checks cover every
specialist, default clarification, routing precedence, and multi-intent cases.
They do not replace Dialogflow simulator tests: after deploying the catalog, run
representative messages in isolated sessions and inspect the selected playbook
and retained invocation summary. Backend tool assertions begin in Phase 5.

Phase 5 validates the conversational OpenAPI document against the real FastAPI
route table, exact operation IDs, structured non-2xx responses, private Cloud Run
authentication configuration, and playbook tool boundaries. Tool examples cover
successful reads, confirmed writes, not-found errors, empty lists, and the rule
that appointment rescheduling is not called generatively before Phase 6. Live
acceptance tests use fresh Dialogflow sessions and canonical seeded identifiers.

Phase 6 contract tests verify required canonical flow inputs, the exact
confirmation prompt, the single write boundary, `confirmed: true`, service-agent
ID-token authentication, canonical response verification, cancellation, ambiguous
confirmation, and webhook failure outcomes. Live acceptance uses isolated
sessions and compares backend state before and after a declined confirmation;
the appointment must remain unchanged.

---

## Minimum Golden Conversations

1. known customer asks ticket status
2. unknown ticket
3. customer asks technical FAQ
4. known error code
5. unknown error code
6. technical issue requires technician
7. ticket creation accepted
8. ticket creation declined
9. duplicate active ticket
10. appointment lookup
11. appointment reschedule
12. appointment reschedule cancelled
13. requested slot unavailable
14. ambiguous "yes"
15. backend timeout
16. backend 500
17. tool returns malformed data
18. customer changes topic
19. multiple requests in one message
20. explicit human request
21. complaint
22. identity ambiguity
23. customer asks about another customer's data
24. missing device
25. device/customer ownership mismatch
26. repeated tool failure
27. invalid appointment state
28. RAG returns no result
29. conflicting knowledge documents
30. handover creation failure

Phase 7 additionally validates the local hierarchy contract, generated PDF
presence, managed ingestion configuration (`layoutParsingConfig`, 300-token
chunks, ancestor headings), cited answers, empty retrievals, and model-dependent
conflicts. Live indexing/query acceptance runs after the asynchronous Agent
Search import completes.

Phase 8 validates explicit handover with and without identity, every structured
reason, neutral summaries and context, customer/ticket ownership, deterministic
priority, stable-request idempotency, conflicting retries, escalation after two
consecutive failures, and the rule that a failed handover never produces a false
success or invented handover number.

Phase 9 contract tests validate the versioned German speech profile, privacy
defaults, 16 kHz mono LINEAR16 input, chunking, session-ID safety, streaming
detect-intent usage and the absence of business endpoints in the voice adapter.
The acceptance catalog covers normal and slow speech, mid-utterance pauses,
corrections, barge-in, customer IDs, serial numbers and backend latency. Live
acceptance uses one persistent Dialogflow session, reviews final transcripts and
24 kHz response audio, and verifies that voice never changes a backend business
rule or bypasses confirmation.

---

## Assertions

Conversation tests should verify:

- selected playbook
- selected tool
- tool arguments
- whether a write occurred
- confirmation requirement
- error handling path
- handover path
- final speech transcript and synthesized response
- critical-identifier read-back and correction replacement
- interruption cancellation without a write
- latency response without an invented result
- final response semantics

Avoid asserting exact natural-language wording unless necessary.

---

## Failure Injection

Provide test doubles that can simulate:

- timeout
- connection error
- HTTP 500
- malformed JSON
- stale appointment slot
- duplicate write request
- empty RAG result
