# Review of the first 53 real runs

The three original reports remain the source of record. The pending human
review packet is [real-review-53.json](real-review-53.json). Each row points to
its source report, which contains the evidence used for the claims. Reviewer
and judgment fields remain unset.

| Runs | Observed failure | Finding |
| --- | --- | --- |
| F14 repeats 1–3, F18 repeat 1, F22 repeat 1 | Budget exhaustion before resolving conflicting evidence | Each stopped after 5 rounds and 6 LLM attempts. Settled usage alone was below 30,000 tokens. The old report does not distinguish a denied reservation from another budget stop. |
| F15 repeat 3 | UnboundLocalError at the global stop boundary | The harness formerly referenced the action before assignment when the snapshot contained no action. That branch already records EXPECTED_ACTION_MISSING in subsequent segments. The historical exception had no stack location. |
| F24 repeat 1, F30 repeat 2 | Partial report with no approval action | Both stopped after 2 rounds with one unknown usage entry in the workflow budget. The global ledgers settled their dispatched calls. The original reports did not preserve the workflow error code. |
| F25 repeat 2 | Partial report with no approval action | One classification attempt, zero investigation rounds. The evidence does not establish whether classification failed validation or selected a different route. |

Future harness reports retain the workflow node and error code from the
checkpoint, plus the run identifier as soon as a run is created. The corpus,
approval rules, budget limits and historical pass/fail records are unchanged.
