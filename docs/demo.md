# OpsPilot demo

The recording uses synthetic data and the explicitly labeled **scripted provider**.
LangGraph, MCP transport, PostgreSQL approval/checkpoints, the API restart and ticket writes
are real. This video is separate from the paid real-provider eval report.

[Watch the demo with English narration](assets/opspilot-demo-narrated.mp4)

[Original silent recording](assets/opspilot-demo.webm)

The English voice is **AI-generated**, using OpenAI Speech API, model
`gpt-4o-mini-tts`, built-in voice `cedar`. Eleven narration clips were aligned to
the existing scenes; the browser session was not re-recorded. The final MP4 uses
H.264 video and AAC audio, 1440x1000, 158.4 seconds. The silent WebM is preserved.
[Timed narration](assets/narration-en.json) and [media checks](assets/narration-en-metadata.json)
are included. Raw generated WAV clips stay in the ignored local `.tools/narration` cache.

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

To assemble from the local voice cache, run `.venv/Scripts/python.exe scripts/narrate-demo.py`.
An explicit `--generate` enables paid Speech API calls for missing clips, using the local
ignored `.env` key. This media task requires ffmpeg/ffprobe on PATH and the project Python
environment. The API receives narration text only; video assembly is local.

Narration timing was subsequently checked against contact sheets and transition close-ups
from the rendered MP4. Early evidence/card narration and the Reject outcome were retimed
using cached speech, with zero new API calls. See [synchronization review](narration-sync-review.md).
