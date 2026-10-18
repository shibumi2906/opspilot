# OpsPilot demo

The recording uses synthetic data and the explicitly labeled **scripted provider**.
LangGraph, MCP transport, PostgreSQL approval/checkpoints, the API restart and ticket writes
are real. This video is separate from the paid real-provider eval report.

[Watch the browser demo](assets/opspilot-demo.webm)

The 2–3 minute walkthrough shows the request, current evidence, immutable approval,
a hard API restart on the pending interrupt, Approve and exact ticket verification,
then a new investigation with Reject. Captions explain the deterministic-core / AI-layer
boundary. There is no claim that ticket creation repairs order delivery.

Screenshots:

- [Workspace](assets/workspace.png)
- [Evidence](assets/evidence.png)
- [Pending action](assets/pending.png)
- [Verified ticket](assets/verified.png)
- [Rejected action](assets/rejected.png)

Reproduce the recording after local setup (scripted mode):

```powershell
docker compose -p opspilot-test -f compose.yaml -f compose.test.yaml build e2e
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/record-demo.ps1
```

The capture script fails if restored action ID/hash differs, verification fails, or Reject
has a ticket result. The automated process tests additionally check database uniqueness.
Do not restart an unrelated API or record real customer data.
