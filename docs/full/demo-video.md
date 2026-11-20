# Full — English demonstration

[Watch the Full demo, 3 minutes](../assets/full/opspilot-full-demo-en.mp4)
· [English SRT](../assets/full/opspilot-full-demo-en.srt)
· [Transcript](../assets/full/demo-en-script.json)
· [Media metadata and SHA-256](../assets/full/demo-en-metadata.json)

Recorded on 20 November 2026 from the running isolated Full TLS pilot, with
synthetic data and the scripted model. The UI, durable worker, database, MCP calls,
approval and ticket verification are real local application behavior. This is a
portfolio demonstration; it makes no production or ASVS certification claim.

The operator investigates GreenShop failures, inspects sources and hypotheses,
and reopens the same persisted action and payload hash. A different authenticated
approver authorizes exactly one local ticket. The report verifies the ticket; it
does not claim that orders have recovered. A second investigation is rejected and
creates no ticket. Database counts before/after show one additional local ticket.
No Jira operations or paid provider calls were made.

| Time | Demonstration |
| --- | --- |
| 00:00 | Introduction |
| 00:09 | Tenant and role context |
| 00:27 | Investigation |
| 00:44 | Evidence and hypotheses |
| 01:06 | Exact approval boundary |
| 01:23 | Reopen the saved action |
| 01:38 | Separate approver |
| 01:54 | Execute and verify the ticket |
| 02:14 | Persisted investigation history |
| 02:31 | Reject a second action |
| 02:48 | Closing overview |

## Recording and narration

Title cards and the chapter sidebar are presentation graphics. Nine UI segments
were recorded with Playwright at 1280×720 and placed in a 1920×1080 frame. Navigation
setup is trimmed between chapters; this is an edited walkthrough. No UI outcomes
are fabricated. OIDC/password/TOTP entry happens in unrecorded contexts. Session
state is transferred only in memory; credentials, tokens and login screens are
excluded. Work files and partial attempts remain ignored locally.

Narration uses the installed **Microsoft Zira Desktop — English (United States)**
voice through offline Windows SAPI, played at 1.08× with pitch preserved. No cloud
TTS requests were made. English captions are burned in, embedded as a selectable
track and supplied as SRT. Timing is estimated per spoken paragraph rather than
word-aligned transcription. The H.264/AAC MP4 uses fast-start.

The first capture stopped while the model label was loading, before approval.
The same pending investigation and two finished clips were preserved. A guarded
resume continued from evidence without recreating the run or repeating a write.

## Reproduction tools

- [Offline narration](../../scripts/synthesize-full-demo.ps1) creates private WAVs
  and a timed plan using an installed English voice.
- [UI recording](../../scripts/record-full-demo.mjs) is restricted to the retained
  scripted `opspilot-full-test-f23-recovery4` pilot. It checks certificate pins,
  roles and the local ticket tool. Private `/lab` and `/video` mounts are required.
  Existing capture state is refused except for the guarded evidence resume.
- [Assembly](../../scripts/assemble-full-demo.py) validates capture and database
  proof, then uses local ffmpeg and Segoe UI fonts. From this checkout:
  `python scripts/assemble-full-demo.py .tools/full-demo-video-20261120`.
  The ignored title preview is rendered from the committed Full hero SVG.

These tools use the prepared Full pilot; they do not initialize a lab or touch the
completed MVP. Inspect partial state before resuming. Never repeat an unknown
approval or external operation to obtain a cleaner take.
