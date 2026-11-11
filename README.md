# OpsPilot Full

OpsPilot investigates operational incidents, builds evidence-linked action plans, and
requires explicit approval before executing authorized changes. The Full implementation
adds tenant isolation, OIDC and role-based access, durable workers and audit history,
signed execution grants, a role-based workspace, and scoped observability integrations.

## Implementation status

- **F01–F19 complete.** F19 includes a Prometheus integration verified in temporary AWS staging.
- **F20 blocked.** Jira write and reconciliation checks are pending.
- **F21–F22 partially complete.** Local resilience checks and scripted evaluations are documented.
  The latest real F22 evaluation report records 68 of 90 runs. The remaining acceptance checks are open.
- **F23–F24 pending.** Pilot deployment and release are still ahead.

## Code and documentation

- [Local workspace and setup](START-HERE.md)
- [Implementation tracker and evidence](docs/full-version-status.md)
- [Full specification](OpsPilot_Full_Project_Specification.md)
- [F21 resilience evidence](docs/full/evidence/f21/README.md)
- [F22 evaluation results](docs/full/evidence/f22/continuation/README.md)
- [Portfolio MVP and its quickstart](https://github.com/shibumi2906/opspilot/tree/opspilot-portfolio-mvp-v1.0)
