# Portfolio edition — completed

**Delivery status: COMPLETE. Scope selected by the owner on 20 November 2026.**

The owner clarified that this project is needed as a portfolio showcase and asked
to finish practical additions, prepare a polished README and consider that edition
finished. This supersedes the previous goal of completing every production release
gate before delivering the portfolio. The separate MVP remains finished and unchanged
by this work; it is not part of this closeout.

## Delivered

- An [English Full demonstration](demo-video.md): actual UI, offline narration,
  English captions, separate approval, verified local ticket and rejection.
- A portfolio-first [README](../../README.md): actual Full screenshots, workflow,
  engineering decisions, system architecture, measured results and navigation.
- A [guided tour](showcase-tour.md), lightweight local contract-check instructions
  and the existing reproducible GitHub Actions route.
- Updated [current architecture](architecture.md); the [F01 architecture](architecture-f01.md)
  is preserved as historical documentation.
- Four fresh [Full screenshots](../assets/full/capture.json) from the actual TLS pilot:
  OIDC/TOTP sign-in, operator/approver separation, exact approval, one local ticket,
  independent verification and persisted history. Synthetic data and scripted mode
  remain visible. The older narrated video is explicitly identified as the MVP.
- Verified [CI at79a856b](evidence/f23/operations-20261116/ci-79a856b.json): Full50/50,
  MVP12/12, Jira/readiness45, F22 units12, backup units9, security/secret gates passed
  and144 source hashes matched. Later packaging commits receive their own CI status.
- Preserved backend603/71-skip evidence, TLS/MFA and rollback records, encrypted
  backups, scheduled local operations and59-table restore verification.
- A [machine-readable scope record](portfolio-status.json) and a packaging check
  that verifies screenshots, evidence counts and documentation links.

The screenshot capture first stopped at an uppercase UI text assertion after the
local operation had already completed. Database read-back confirmed completion;
the result/history were then captured read-only. The approved operation was not
repeated. Partial attempts and diagnostic logs remain in ignored local forensics.

## Acceptance boundary

This is a completed **engineering portfolio and local synthetic demonstrator**.
The status does not certify ASVS L2, make an internet-facing deployment available,
or turn the original production F01–F24 requirements into passed checks.

The [253-row security assessment](../security/release-review-20261116/README.md),
12 documented gaps and41 additional verification items remain the production-hardening
backlog. The43 owner-reviewed N/A decisions retain their exact original local scope.
BitLocker remains deferred by the owner; host settings and recovery keys are outside
this delivery. Private configuration, credentials and backups remain ignored.

Jira unknown outcomes/receipts are preserved. The portfolio screenshot session
performed no Jira dispatch and no paid model calls. Existing MVP work was neither
staged nor edited; this work is confined to the independent Ops checkout.

## Maintaining the showcase

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/check-full-portfolio.py
.venv/Scripts/python.exe scripts/check-full-release-review.py
```

Refresh screenshots only in the isolated scripted pilot, using synthetic identities
and a separately approved local operation. Existing screenshots are preserved by
default. For resumed capture use a privately inspected completed-run reference;
never repeat an uncertain operation to obtain a better screenshot.
