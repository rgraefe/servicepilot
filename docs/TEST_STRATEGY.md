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
