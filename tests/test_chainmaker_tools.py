from __future__ import annotations

from crosfed.integrations.chainmaker.e2e import find_metric, find_request_id


def test_chainmaker_recursive_result_extractors() -> None:
    request_id = "0x" + "ab" * 32
    payload = {"result": {"events": [{"request_id": request_id}], "gas_used": "42"}}
    assert find_request_id(payload) == request_id
    assert find_metric(payload, {"gasused"}) == 42
