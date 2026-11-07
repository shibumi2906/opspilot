"""Synthetic exporter for a real Prometheus; separate HTTPS fault server for error cases."""

import hmac
import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.f19_cases import CASES

mode = "normal"
control = Path("/run/fixture/control").read_text()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, status=200, content_type="application/json", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        global mode
        if self.path != "/control" or not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + control
        ):
            self.reply(b"{}", 403)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size < 200:
            self.reply(b"{}", 400)
            return
        mode = json.loads(self.rfile.read(size))["mode"]
        self.reply(b"{}")

    def do_GET(self):
        if self.path == "/metrics":
            lines = ["# TYPE opspilot_integration_health gauge"]
            for index, case in enumerate(CASES):
                targets = (
                    [f"overflow{n}" for n in range(20)]
                    if mode == "cardinality"
                    else ["primary", "replica"]
                )
                for target in targets:
                    if mode == "absent" or (mode == "partial" and target == "replica"):
                        continue
                    value = 1 if index else 0.5
                    if mode == "healthy":
                        value = 1
                    if mode == "unavailable":
                        value = 0
                    labels = {k: case[k] for k in ("tenant_id", "customer_id", "integration_id")}
                    labels["opspilot_target"] = "primary" if mode == "cardinality" else target
                    if mode == "cardinality":
                        labels["unexpected_series"] = target
                    label_text = ",".join(f'{k}="{v}"' for k, v in labels.items())
                    stamp = f" {int((time.time() - 180) * 1000)}" if mode == "stale" else ""
                    lines.append(f"opspilot_integration_health{{{label_text}}} {value}{stamp}")
            self.reply(("\n".join(lines) + "\n").encode(), content_type="text/plain; version=0.0.4")
            return
        if mode == "redirect":
            self.reply(b"{}", 302, headers={"Location": "https://example.invalid/"})
        elif mode in {"401", "403", "429", "500", "503"}:
            self.reply(b"{}", int(mode))
        elif mode == "slow":
            time.sleep(3)
            self.reply(b"{}")
        elif mode == "drip":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "10000")
            self.end_headers()
            try:
                for _ in range(35):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif mode == "oversized":
            self.reply(b" " * 65537)
        elif mode == "duplicate_json":
            self.reply(b'{"status":"success","status":"error"}')
        elif mode == "compressed":
            self.reply(b"{}", headers={"Content-Encoding": "gzip"})
        elif mode in {"warnings", "infos"}:
            self.reply(
                json.dumps({"status": "success", mode: ["partial result"], "data": {}}).encode()
            )
        else:
            self.reply(b'{"status":"error","error":"fixture error"}')


if __name__ == "__main__":
    plain = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    tls = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain("/run/fixture/server.crt", "/run/fixture/server.key")
    tls.socket = context.wrap_socket(tls.socket, server_side=True)
    tls.serve_forever()
