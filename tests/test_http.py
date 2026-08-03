import pytest
import requests

from ea_alert.fetchers import http


class FakeResponse:
    def __init__(self, text="ok", status=200):
        self.text = text
        self.status_code = status
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_get_success(monkeypatch):
    def fake_get(url, headers, timeout):
        assert "ea-alert-line" in headers["User-Agent"]
        return FakeResponse("hello")

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get("https://example.com") == "hello"


def test_get_retries_then_succeeds(monkeypatch):
    calls = []

    def flaky_get(url, headers, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse("recovered")

    monkeypatch.setattr(http.requests, "get", flaky_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    assert http.get("https://example.com") == "recovered"
    assert len(calls) == 3


def test_get_does_not_retry_client_error(monkeypatch):
    # 403（bot対策など）は再送しても同じなので即座に投げる
    calls = []

    def forbidden_get(url, headers, timeout):
        calls.append(url)
        return FakeResponse("forbidden", status=403)

    monkeypatch.setattr(http.requests, "get", forbidden_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: pytest.fail("待たずに投げること"))
    with pytest.raises(requests.HTTPError):
        http.get("https://example.com")
    assert len(calls) == 1


def test_get_retries_server_error(monkeypatch):
    calls = []

    def flaky_get(url, headers, timeout):
        calls.append(url)
        return FakeResponse("boom", status=503) if len(calls) < 3 else FakeResponse("ok")

    monkeypatch.setattr(http.requests, "get", flaky_get)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    assert http.get("https://example.com") == "ok"
    assert len(calls) == 3


def test_get_raises_after_all_retries(monkeypatch):
    def always_fail(url, headers, timeout):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(http.requests, "get", always_fail)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        http.get("https://example.com")
