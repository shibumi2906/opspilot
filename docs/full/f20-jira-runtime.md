# F20 Jira Cloud runtime operations

The connector supports issue creation and separately approved comments in the
owner-authorized KAN sandbox. Each immutable action revision binds the connector,
customer, project, issue type, exact business fields and operation marker. Signed
service context, approval and execution grants are independently checked by MCP.
Credentials are retrieved from the manager through the connector-specific ACL.

`0022_jira_operations` adds trusted bindings and one-attempt operation receipts;
`0023_jira_audit` records receipt transitions in the protected transactional audit.
The main Full schema0019 is preserved. Migration acceptance currently uses isolated
F20 test projects, not the main database.

## Unknown outcomes and reconciliation

The durable receipt is inserted before dispatch. An unknown result does not allow
another POST, even when a search finds no object. A provider ID is stored before
additional verification reads, so a failed GET cannot erase a known destination.
Exact field and marker verification is required for verified success. Reconciliation
also searches for late duplicates after a previous verified result; conflicts require
operator attention. An absence result is never an instruction to retry creation.

The authenticated operator endpoint is
`POST /api/v2/jira/operations/{action_id}/reconcile`. It requires recent authentication,
the owning operator/tenant and a fenced execution lease. This application POST
performs Jira reads and records the result; it does not redispatch the Jira write.
The browser exposes reconciliation for Jira actions. A comment requires its own
approval and binds its parent issue destination.

Jira MCP operations have a 45-second call deadline; ordinary tools keep their
five-second deadline. Reconciliation has a bounded 40-second vendor-read window.
Fault injection belongs in the controlled vendor boundary tests, not in live Jira.

## Preserved sandbox lab

`opspilot-full-test-f20-r1` contains real receipts and unknown attempts. Preserve
its database, manager state and failed reports. Do not rerun Prepare, reseed it,
delete a report to reuse an attempt label, or run a generic worker to retry unknown
operations. `tests.f20_jira_live*` are separate, explicitly side-effecting tools;
the backend continuation does not invoke them.

To replace expired manager tokens after starting the existing manager, use:

```powershell
.venv/Scripts/python.exe scripts/refresh-full-f20-manager.py --project opspilot-full-test-f20-r1
```

This helper unseals the existing manager if necessary, waits for readiness and
issues one-hour worker/MCP tokens under the existing policies. It preserves ACLs,
signing keys and connector enrollment and performs no Jira requests. The historical
F17 bootstrap overwrites its base MCP policy, so it must not be used as this refresh.
`setup-full-f20-jira.py` is an enrollment tool, not a refresh or retry command.

## Regression environment

Use a fresh `opspilot-full-test-f20-*` project and an unused subnet. Prepare creates
only synthetic fixtures and manager grant keys; it does not enroll Jira credentials.
Run labs serially and preserve both successful and failed evidence.

```powershell
./scripts/test-full-f20.ps1 -Mode Prepare -Project opspilot-full-test-f20-r3 -Subnet 66
./scripts/test-full-f20.ps1 -Mode Backend -Project opspilot-full-test-f20-r3 -Subnet 66
```

The example r3 is already allocated; reuse its existing environment only for
inspection, or choose a new label/subnet for another fresh run. Backend starts and
checks API/MCP/database/cache/collector before pytest, uses backend admission limits,
stops after three failures and writes a unique timestamped XML report. A selected
`-TestTargets tests/integration/test_observability.py` recheck has its own report and
does not replace the full regression. [Evidence and limitations](evidence/f20/README.md).

All checks use scripted mode. The native boundary fixture replaces the vendor
transport and credential lookup, while testing actual API decisions, MCP, grants,
RLS, fencing, receipts and audit. Neither a stub pass nor a focused successful
recheck replaces the final complete regression and release security review.
