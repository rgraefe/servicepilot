import json
import logging

from app.observability import (
    REQUEST_ID,
    TRACE_RESOURCE,
    CloudJsonFormatter,
    cloud_trace_resource,
)


def test_cloud_json_formatter_adds_structured_context() -> None:
    request_token = REQUEST_ID.set("request-123")
    trace_token = TRACE_RESOURCE.set("projects/demo/traces/abc")
    try:
        record = logging.LogRecord(
            "servicepilot",
            logging.INFO,
            __file__,
            1,
            "request completed",
            (),
            None,
        )
        record.event = "request_completed"
        record.httpRequest = {"status": 200}
        payload = json.loads(CloudJsonFormatter().format(record))
    finally:
        TRACE_RESOURCE.reset(trace_token)
        REQUEST_ID.reset(request_token)

    assert payload["severity"] == "INFO"
    assert payload["request_id"] == "request-123"
    assert payload["logging.googleapis.com/trace"] == "projects/demo/traces/abc"
    assert payload["event"] == "request_completed"
    assert payload["httpRequest"]["status"] == 200


def test_cloud_trace_resource_validates_header() -> None:
    trace = "0123456789abcdef0123456789abcdef/123;o=1"
    assert cloud_trace_resource(trace, "demo-project") == (
        "projects/demo-project/traces/0123456789abcdef0123456789abcdef"
    )
    assert cloud_trace_resource("not-a-trace", "demo-project") is None
    assert cloud_trace_resource(trace, None) is None
