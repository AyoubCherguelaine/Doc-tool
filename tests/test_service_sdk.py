"""SDK options must reach the public APIs without mutating global headers."""

from unittest.mock import patch

import httpx

from backend.sdk.client import DOCToolClient


def test_sdk_idempotency_and_configurable_workflows():
    calls = []

    def request(self, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"success": True}, request=httpx.Request(kwargs["method"], kwargs["url"]))

    with patch.object(httpx.Client, "request", request):
        client = DOCToolClient("test-key")
        client.match_invoice("invoice", "order", financial_options={"tax_rate": ".2"}, idempotency_key="match-1")
        client.compare_contract_versions("old", "new")
        client.translate_document(
            "document", "English", source_language="Arabic", glossary={"فاتورة": "invoice"}, preserve_names=["Acme"]
        )
        client.submit_async_job(
            "doc",
            "invoice",
            schema_override={"type": "object"},
            model="test",
            options={"financial": {"date_order": "DMY"}},
            idempotency_key="job-1",
        )
        client.check_document("doc", rules=[{"field": "total", "operator": "lte", "value": 100}])
        assert calls[0]["headers"]["Idempotency-Key"] == "match-1"
        assert calls[0]["json"]["options"]["reference_document_id"] == "order"
        assert "Idempotency-Key" not in calls[1]["headers"]
        assert calls[2]["json"]["options"]["translation"]["target_language"] == "en"
        assert calls[3]["json"]["schema_override"] == {"type": "object"}
        assert calls[3]["json"]["model"] == "test"
        assert calls[4]["json"]["options"]["rules"][0]["value"] == 100
