"""Measure actual owned HTTP staging services; never generate fixture health values.

service PORT: bounded HTTP application with a real writable-disk health check.
observer CONFIG: scrape each configured service via HTTP and export measured health.
Only the observer binds metrics; all three services bind loopback on the EC2 host.
"""

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer


class Application(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        try:
            # Check actual filesystem IO, not a configured constant health label.
            with tempfile.TemporaryFile(dir="/var/lib/opspilot-f19") as stream:
                value = os.urandom(32)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
                stream.seek(0)
                if stream.read() != value:
                    raise OSError("IO mismatch")
            body, code = b'{"health":"ready","check":"disk-roundtrip"}', 200
        except OSError:
            body, code = b'{"health":"unavailable"}', 503
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Observer(BaseHTTPRequestHandler):
    config = {}

    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        lines = ["# TYPE opspilot_integration_health gauge"]
        for target, port in self.config["targets"].items():
            if target not in {"primary", "replica"} or port not in {8080, 8081}:
                self.send_error(500)
                return
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=0.25
                ) as response:
                    body = response.read(1024)
                    healthy = response.status == 200 and json.loads(body).get("health") == "ready"
            except (OSError, ValueError, urllib.error.URLError):
                healthy = False
            labels = {**self.config["scope"], "opspilot_target": target}
            rendered = ",".join(f"{k}={json.dumps(v)}" for k, v in labels.items())
            lines.append(f"opspilot_integration_health{{{rendered}}} {int(healthy)}")
        body = ("\n".join(lines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if sys.argv[1] == "service":
        HTTPServer(("127.0.0.1", int(sys.argv[2])), Application).serve_forever()
    elif sys.argv[1] == "observer":
        Observer.config = json.loads(open(sys.argv[2], encoding="utf-8").read())
        if set(Observer.config["scope"]) != {"tenant_id", "customer_id", "integration_id"}:
            raise ValueError("Exact scope required")
        HTTPServer(("127.0.0.1", 9100), Observer).serve_forever()
    else:
        raise ValueError("Expected service or observer")
