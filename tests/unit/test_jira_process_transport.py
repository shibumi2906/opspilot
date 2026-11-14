"""Exercise durable simulator receipts across real HTTP and process boundaries."""

import json
import multiprocessing
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest

from opspilot.integrations.jira_payload import SandboxMapping, issue_payload
from opspilot.integrations.jira_simulator_receipts import (
    Observation,
    SimulatedOperation,
    SimulatorReceipts,
)
from opspilot.integrations.jira_verification import Outcome

MAPPING = SandboxMapping("https://synthetic.atlassian.net", "1", "2", 1)


def send(path, tenant, marker, endpoint):
    """A fresh process reopens the receipt store before attempting a dispatch."""
    marker = UUID(marker)
    payload = issue_payload(MAPPING, marker, summary="Synthetic", description="Process drill")
    operation = SimulatedOperation(UUID(tenant), marker, MAPPING, payload)
    receipts = SimulatorReceipts(path)

    def post():
        request = Request(endpoint + "/issue", data=payload, method="POST")
        try:
            with urlopen(request, timeout=3) as response:
                response.read()
        except HTTPError:
            # A simulator denial is still an attempted dispatch.
            pass
        except OSError:
            # The peer may commit the effect and close before returning the response.
            pass

    receipts.dispatch(operation, operation.digest(), post)


@contextmanager
def provider(mode):
    state = {"attempts": 0, "objects": []}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["attempts"] += 1
                if mode in ("lost_response", "created"):
                    state["objects"].append(
                        {
                            "id": "45",
                            "fields": payload["fields"],
                            "marker": payload["properties"][0]["value"],
                        }
                    )
            if mode == "lost_response":
                self.close_connection = True
                return
            self.send_response(
                {"denied": 403, "rate_limit": 429, "server_error": 500}.get(mode, 201)
            )
            self.end_headers()

        def do_GET(self):
            with lock:
                body = json.dumps(state["objects"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "mode", ["lost_response", "denied", "rate_limit", "server_error", "created"]
)
def test_process_restart_does_not_repeat_http_dispatch(tmp_path, mode):
    path = tmp_path / "receipts.db"
    SimulatorReceipts(path)
    tenant, marker = uuid4(), uuid4()
    operation = SimulatedOperation(
        tenant,
        marker,
        MAPPING,
        issue_payload(MAPPING, marker, summary="Synthetic", description="Process drill"),
    )
    context = multiprocessing.get_context("spawn")
    with provider(mode) as (endpoint, state):
        processes = [
            context.Process(target=send, args=(path, str(tenant), str(marker), endpoint))
            for _ in range(3)
        ]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
                assert process.exitcode == 0
            # Independent HTTP read-back establishes whether the effect exists.
            with urlopen(endpoint + "/issues", timeout=3) as response:
                observed = json.load(response)
            receipts = SimulatorReceipts(path)
            records = [
                Observation(MAPPING.site, "1", row["id"], row, row["marker"]) for row in observed
            ]
            expected = Outcome.VERIFIED if mode in ("lost_response", "created") else Outcome.UNKNOWN
            assert receipts.reconcile(operation, records, complete=True) == expected
            # Reopening the client after read-back must still preserve the attempt boundary.
            send(path, str(tenant), str(marker), endpoint)
            assert state["attempts"] == 1
            assert len(state["objects"]) == (1 if expected == Outcome.VERIFIED else 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
