# Full release review — 16 November 2026

**Full / ASVS L2: NOT_MET.** This is a requirement-specific source and evidence
assessment of all 253 L1/L2 requirements against the selected scripted local
`opspilot-full-test-f23-recovery4` profile. It is not a certification or an acceptance
of all the requirements. The main Full database remains schema0019.

[Individual assessments](requirements.tsv) and [structured review](review.json)
preserve the existing backlog and its identities, owners, baseline and N/A fields.
Each row has its own assessment; existing primary stage contributions remain
traceable in the structured file. Chapter source references identify the reviewed
implementation, not a claim that every line was independently penetration-tested.
[The43 N/A decisions](not-applicable-proposals.md) were explicitly accepted by the owner
for this local profile; the [scoped approval record](owner-na-review.json) binds their exact IDs/rationales.

| Disposition | Rows | Meaning |
|---|---:|---|
| supported_in_local_scope | 157 | Source and existing scoped evidence support the control; full normative closure remains open |
| not_applicable_owner_reviewed | 43 | Owner explicitly accepted applicability for this local profile; re-review on feature/deployment change |
| verification_needed | 41 | A target/configuration/negative test or operational acceptance is missing |
| gap | 12 | A concrete unresolved implementation or deployment difference |

Normative source: [OWASP ASVS 5.0.0 release](https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release),
release commit `5cf9b032440be53ce345ab3c130fda46ba1ce7a2`.
Downloaded flat JSON SHA256:
`8201b20eec2908c3380ac600c91c8ba746346fbb808859366abb232027532311`.
The normative text is not redistributed here. Its license is CC-BY-SA-4.0;
these files contain identifiers and our own assessments.

## Confirmed gaps

| Requirement | Remaining work |
|---|---|
| 6.1.2 | Document organization/project/role context words and relevant permutations |
| 6.2.4 | Replace/extend the denylist with a provenance-backed set of at least 3000 policy-matching passwords; current97,746 entries contain only329 of length15–128 |
| 6.2.11 | Enforce the documented context-word password restrictions |
| 6.3.2 | Separate synthetic personas/bootstrap identities from a production provisioning profile |
| 6.4.1 | Use individual expiring initial credentials and require replacement; current synthetic fixture passwords are persistent and shared |
| 6.4.3 | Document and test password recovery without bypassing MFA |
| 6.4.4 | Document and test lost-factor identity proofing and authorized recovery |
| 12.2.2 | Obtain public-trust certificates for an external target, or obtain owner applicability approval for this strictly internal private-CA profile |
| 13.2.1 | Replace long-lived PostgreSQL/Redis credentials with a reviewed short-lived service authentication lifecycle |
| 13.3.1 | Extend managed secret lifecycle beyond grant keys to database/cache/IdP/bootstrap/backup secrets |
| 14.2.4 | Encrypt host storage after the owner saves an independent BitLocker recovery copy |
| 15.2.3 | Provide a deployment profile without synthetic users/fixture functionality |

For the 41 missing verifications, use the row assessments rather than turning a
chapter-level result into a blanket pass. Important examples: effective IdP client
inventory and grants, code/refresh replay, password-change/recovery fidelity,
TOTP replay, HTTP framing/duplicate parameters, complete cryptographic/logging
inventory, patch deadlines and independent alert/escalation acceptance.

The previously successful backend603, browser/MFA, image scans and remote CI are
valuable evidence with narrower scope. They do not waive these gaps. F22 owner
review was not the basis for the43 N/A decisions; they received a separate explicit
owner response on16 November2026. The other210 applicable requirements remain open
for full normative closure, including the12 gaps and41 missing verifications.

Reproduce the completeness/protection check from the repository root:

```powershell
.venv/Scripts/python.exe scripts/check-full-release-review.py
```

It verifies exact253 coverage, unique assessments, inherited backlog identity,
source reference existence and deterministic JSON. If the ignored normative JSON
is available, it also verifies its checksum and exact L1/L2 identifier set.
