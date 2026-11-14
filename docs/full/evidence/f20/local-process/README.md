# F20 local process and HTTP verification

Base da32c4b. Local synthetic provider bound to 127.0.0.1 and three spawned client
processes use the same durable simulator receipt database. No Jira credential
is loaded by these tests.

Checks cover successful creation, connection close after commit, 403 denial,
429 rate limiting, 500 response, independent GET read-back, and reopening the
receipt store after process exit. Every case observes exactly one POST across
three competing processes and a subsequent replay.

A separate regression covers a late duplicate after a previously verified result.
The durable status escalates to needs_attention. Later partial/empty read-back
preserves a verified receipt, while needs_attention stays terminal and never
authorizes another write.

Run from the Full checkout:

~~~powershell
.venv/Scripts/python.exe -m pytest -q tests/unit/test_jira_process_transport.py tests/unit/test_jira_simulator_receipts.py tests/unit/test_jira_verification.py tests/unit/test_jira_preflight.py tests/test_f20_jira_payload.py --basetemp=.tools/f20-process-transport-final
~~~

33 tests passed. Ruff passed for the changed Python files. The first sandbox
attempt failed on Windows localhost socket access (WinError10013). The accepted
run used tool escalation for local sockets with the same assertions.

This evidence uses SQLite simulator receipts and plaintext localhost HTTP.
Application PostgreSQL dispatch receipts, production grant enforcement, pinned
HTTPS, manager mapping ACL, and real Jira acceptance remain open. F20 stays blocked.
