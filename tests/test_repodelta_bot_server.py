from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from repodelta_bot.server import Handler, ThreadingHTTPServer, _valid_signature  # noqa: E402


@pytest.fixture
def server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    host, port = httpd.server_address

    try:
        yield httpd, f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_valid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")

    body = b'{"action":"opened"}'
    signature = "sha256=" + hmac.new(
        b"test-secret",
        body,
        hashlib.sha256,
    ).hexdigest()

    assert _valid_signature(body, signature) is True
    assert _valid_signature(body, "sha256=bad") is False


def test_health_endpoint(server: tuple[ThreadingHTTPServer, str]) -> None:
    _, base_url = server

    with urllib.request.urlopen(f"{base_url}/health") as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok"}


def test_webhook_accepts_valid_github_signature(
    server: tuple[ThreadingHTTPServer, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = server
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")

    body = json.dumps({"action": "opened"}).encode()
    signature = "sha256=" + hmac.new(
        b"test-secret",
        body,
        hashlib.sha256,
    ).hexdigest()

    request = urllib.request.Request(
        f"{base_url}/github/webhook",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "test-delivery",
            "X-Hub-Signature-256": signature,
        },
    )

    with urllib.request.urlopen(request) as response:
        payload = json.load(response)

    assert payload == {
        "received": True,
        "event": "pull_request",
        "delivery": "test-delivery",
        "action": "opened",
    }


def test_webhook_rejects_invalid_signature(
    server: tuple[ThreadingHTTPServer, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, base_url = server
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")

    request = urllib.request.Request(
        f"{base_url}/github/webhook",
        method="POST",
        data=b'{"action":"opened"}',
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=wrong",
        },
    )

    with pytest.raises(urllib.error.HTTPError) as captured:
        urllib.request.urlopen(request)

    assert captured.value.code == 401
