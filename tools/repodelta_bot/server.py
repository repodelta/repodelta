from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MAX_BODY_BYTES = 1_000_000


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _valid_signature(body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return False

    if not signature or not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


class Handler(BaseHTTPRequestHandler):
    server_version = "RepoDeltaBot/1.0"

    def _respond(self, status: int, payload: object) -> None:
        body = _json_bytes(payload)

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
            return

        self._respond(
            200,
            {
                "service": "repodelta-bot",
                "status": "running",
            },
        )

    def do_POST(self) -> None:
        if self.path != "/github/webhook":
            self._respond(404, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"error": "invalid content length"})
            return

        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._respond(413, {"error": "invalid payload size"})
            return

        body = self.rfile.read(content_length)

        if not _valid_signature(
            body,
            self.headers.get("X-Hub-Signature-256"),
        ):
            self._respond(401, {"error": "invalid signature"})
            return

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(400, {"error": "invalid json"})
            return

        event = self.headers.get("X-GitHub-Event", "unknown")
        delivery = self.headers.get("X-GitHub-Delivery", "unknown")
        action = payload.get("action") if isinstance(payload, dict) else None

        print(
            json.dumps(
                {
                    "github_event": event,
                    "delivery": delivery,
                    "action": action,
                }
            ),
            flush=True,
        )

        self._respond(
            200,
            {
                "received": True,
                "event": event,
                "delivery": delivery,
                "action": action,
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        print(
            f'{self.address_string()} - {format % args}',
            flush=True,
        )


def main() -> None:
    port = int(os.environ.get("PORT", "10000"))

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    print(
        f"RepoDelta bot server listening on 0.0.0.0:{port}",
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
