import type { Step } from "../api/types";
import { SectionHeader, time } from "./shared";
const names: Record<string, string> = {
  classify: "Understand the request",
  resolve_customer: "Resolve customer and integration",
  investigate: "Choose diagnostic checks",
  execute_reads: "Collect evidence through MCP",
  reason: "Assess facts and hypotheses",
  plan: "Propose a grounded action",
  risk_check: "Validate proposal and policy",
  prepare_approval: "Save immutable action",
  approval: "Human approval",
  execute: "Execute approved ticket",
  verify: "Verify exact ticket fields",
  report: "Build final report",
};
export function RunTimeline({
  steps,
  running,
}: {
  steps: Step[];
  running: boolean;
}) {
  return (
    <section className="panel timeline-panel" aria-label="Investigation trail">
      <SectionHeader
        number="01"
        title="Investigation trail"
        label="Recorded by the core"
      />
      {steps.length === 0 ? (
        <p className="muted empty-line">
          {running
            ? "The workflow is starting. Steps appear as they complete."
            : "Your investigation will leave a visible trail here."}
        </p>
      ) : (
        <ol className="timeline" aria-label="Investigation steps">
          {[...steps]
            .sort((a, b) => a.sequence - b.sequence)
            .map((step) => (
              <li
                key={step.id}
                className={
                  ["failed", "incomplete"].includes(step.status)
                    ? "step-failed"
                    : step.status === "waiting_for_approval"
                      ? "step-waiting"
                      : ""
                }
              >
                <span className="step-mark" aria-hidden="true">
                  {["failed", "incomplete"].includes(step.status)
                    ? "!"
                    : step.status === "waiting_for_approval"
                      ? "·"
                      : "✓"}
                </span>
                <div>
                  <div className="step-top">
                    <span>{names[step.node] ?? step.summary}</span>
                    <span
                      className={`layer-tag ${step.type === "ai" ? "ai" : "core"}`}
                    >
                      {step.type === "ai"
                        ? "AI layer"
                        : step.node === "approval"
                          ? "Human"
                          : "Core"}
                    </span>
                  </div>
                  <div className="step-meta">
                    <time>{time(step.started_at)}</time>
                    {step.duration_ms != null && (
                      <span>{(step.duration_ms / 1000).toFixed(2)}s</span>
                    )}
                    {["failed", "incomplete"].includes(step.status) && (
                      <span>Check incomplete</span>
                    )}
                  </div>
                </div>
              </li>
            ))}
        </ol>
      )}
      {running && (
        <div className="working">
          <span className="spinner" />
          Workflow active · waiting for the next saved update
        </div>
      )}
    </section>
  );
}
