# Narration synchronization review

Reviewed the rendered MP4 against the timed English script, contact sheets across the
recording and close-ups around transitions. This review concerns scene correspondence;
it does not claim an independent speech-to-text transcription or a new application test.

The initial narration anticipated evidence/card display and described the Reject result
while the card was still pending. Retimed the existing clips; no new TTS requests or browser
recording were made. The original silent WebM is unchanged.

| Topic | Final narration window | Visual check |
| --- | --- | --- |
| Introduction / scripted disclosure | 0.8-13.5 s | Workspace and scripted-mode label |
| GreenShop request | 16.5-22.3 s | Request form and GreenShop text |
| Evidence and hypothesis | 24.8-38.8 s | Evidence cards visible by 25 s |
| Immutable proposal / no write yet | 39.2-49.0 s | Pending ticket card visible at 39 s |
| Restart explanation | 50.5-64.5 s | Restart caption and pending action; host command is offscreen |
| Architecture / separate real eval | 65.0-76.5 s | Narrative context during restart wait, not a claim of a displayed eval |
| Restored action | 78.0-90.0 s | Restored pending card and matching run/action explanation from 77 s |
| Approve and verification | 91.5-110.0 s | Approval transition followed by Ticket verified; introductory cue anticipates click |
| Second investigation / Reject choice | 114.5-130.0 s | New investigation visible at 115 s, then pending card |
| Recorded rejection | 133.5-146.5 s | Decision respected visible at 133 s; no premature success/result narration |
| Closing boundary | 147.0-157.5 s | Completed rejected run and closing caption |

Technical verification of the final output:

- H.264 video and AAC audio both last 158.4 seconds; output 6,611,284 bytes.
- Eleven ordered, nonoverlapping narration slots; each rendered clip fits its slot.
- Decoded AAC waveform correlates 0.999864 with the local timed mix, confirming that the
  intended timing is present in the delivered file rather than only in the script.
- Every narration interval contains audio; measured peak -1.3 dBFS.
- AI-generated voice disclosure and the synthetic/scripted-versus-real-eval distinction remain.

Current artifact: [opspilot-demo-narrated.mp4](assets/opspilot-demo-narrated.mp4).
