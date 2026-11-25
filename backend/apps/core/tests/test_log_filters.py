import logging
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.log_filters import RequestIDLogFilter
from apps.core.request_context import reset_request_id, set_request_id


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class RequestIDLogFilterTests(SimpleTestCase):
    def test_uses_current_request_context(self):
        token = set_request_id("ctx-id")
        try:
            record = _record()
            RequestIDLogFilter().filter(record)
        finally:
            reset_request_id(token)
        self.assertEqual(record.request_id, "ctx-id")

    def test_falls_back_to_request_attached_by_django(self):
        record = _record(request=SimpleNamespace(request_id="from-request"))
        RequestIDLogFilter().filter(record)
        self.assertEqual(record.request_id, "from-request")

    def test_placeholder_outside_requests(self):
        record = _record()
        RequestIDLogFilter().filter(record)
        self.assertEqual(record.request_id, "-")
