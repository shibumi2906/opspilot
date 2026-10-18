import { useEffect, useState } from "react";
import { api, errorMessage } from "./api/client";
import type { PublicConfig } from "./api/types";
import { useRun } from "./hooks/useRun";
import { ApprovalCard } from "./components/ApprovalCard";
import { EvidencePanel } from "./components/EvidencePanel";
import { FinalReport } from "./components/FinalReport";
import { RequestForm } from "./components/RequestForm";
import { RunTimeline } from "./components/RunTimeline";
import { shortId, Status, time } from "./components/shared";
export default function App() {
  const run = useRun();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configNonce, setConfigNonce] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api
      .config(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
      .then((value) => {
        setConfig(value);
        setConfigError(null);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setConfigError(errorMessage(reason));
      });
    return () => controller.abort();
  }, [configNonce]);
  useEffect(() => {
    setSelected(null);
  }, [run.runId]);
  const selectEvidence = (id: string) => {
    setSelected(id || null);
    if (id)
      setTimeout(() => {
        const detail = document.getElementById("evidence-detail");
        detail?.focus({ preventScroll: true });
        detail?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 0);
  };
  const snapshot = run.snapshot;
  const mode = snapshot?.mode ?? config?.mode;
  const active = !!run.runId && !run.terminal;
  return (
    <>
      <header className="app-header">
        <a
          className="brand"
          href="/"
          onClick={(event) => {
            if (active) event.preventDefault();
          }}
          aria-label="OpsPilot home"
        >
          <span className="brand-mark" aria-hidden="true">
            ↗
          </span>
          <span>
            OpsPilot<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="header-context">
          <span className="local-dot" />
          LOCAL WORKSPACE<span className="header-separator">/</span>
          <span>SYNTHETIC DATA</span>
        </div>
        <span
          className={`mode-pill ${mode === "real" ? "real" : ""}`}
          data-testid="model-mode"
        >
          {mode === "real"
            ? "Real model"
            : mode === "scripted"
              ? "Scripted model"
              : "Loading mode…"}
        </span>
      </header>
      <main>
        <div className="workspace-heading">
          <div>
            <div className="eyebrow">Operations / Incident workspace</div>
            <h1>Clarity before action.</h1>
            <p>Investigate with AI. Execute with control.</p>
          </div>
          <Status snapshot={snapshot} />
        </div>
        <div className="architecture-strip">
          <span>
            <i className="layer-symbol">✦</i>
            <strong>AI layer</strong> interprets & proposes
          </span>
          <span className="strip-arrow" aria-hidden="true">
            →
          </span>
          <span>
            <i className="layer-symbol core-symbol">◇</i>
            <strong>Deterministic core</strong> validates & verifies
          </span>
          <span className="strip-arrow" aria-hidden="true">
            →
          </span>
          <span>
            <i className="layer-symbol human-symbol">◎</i>
            <strong>You</strong> authorize the write
          </span>
        </div>
        {(run.error || run.mutationError || (!config && configError)) && (
          <div className="connection-banner" role="alert">
            <div>
              <strong>
                {run.error
                  ? "Snapshot unavailable"
                  : run.mutationError
                    ? "Action needs a state check"
                    : "Workspace connection unavailable"}
              </strong>
              <p>{run.error ?? run.mutationError ?? configError}</p>
            </div>
            <button
              className="button secondary"
              type="button"
              onClick={() => {
                run.refresh();
                setConfigNonce((n) => n + 1);
              }}
            >
              Retry connection
            </button>
          </div>
        )}
        <div className="workspace-grid">
          <aside className="request-column">
            <section className="panel request-panel">
              <div className="eyebrow">Start with the problem</div>
              <h2>
                An incident.
                <br />A traceable decision.
              </h2>
              <p className="muted">
                Describe what you observe. OpsPilot collects evidence before
                proposing one bounded action.
              </p>
              {run.runId ? (
                <div className="saved-request">
                  <span className="eyebrow">Your request</span>
                  <p>{snapshot?.request ?? "Loading saved investigation…"}</p>
                  <div className="run-reference">
                    <span>RUN / {shortId(run.runId)}</span>
                    <span>
                      {snapshot?.created_at
                        ? time(snapshot.created_at)
                        : "Saved in URL"}
                    </span>
                  </div>
                  {run.terminal && (
                    <button
                      type="button"
                      className="button secondary"
                      onClick={run.reset}
                    >
                      New investigation <span aria-hidden="true">+</span>
                    </button>
                  )}
                  {run.error && !snapshot && (
                    <button
                      type="button"
                      className="text-button"
                      onClick={run.reset}
                    >
                      Start a new investigation
                    </button>
                  )}
                </div>
              ) : (
                <RequestForm
                  onStart={run.start}
                  busy={run.creating}
                  locked={!config}
                />
              )}
              <div className="scope-note">
                <span aria-hidden="true">◇</span>
                <p>
                  One internal ticket, with your approval. No automatic repairs
                  or credential changes.
                </p>
              </div>
            </section>
            {snapshot && (
              <FinalReport snapshot={snapshot} onSelect={selectEvidence} />
            )}
            <section className="runtime-note">
              <div className="eyebrow">Transparent by design</div>
              <dl>
                <dt>Model mode</dt>
                <dd>{mode ?? "Unavailable"}</dd>
                <dt>Provider</dt>
                <dd>
                  {snapshot?.model_id ??
                    config?.model_id ??
                    (mode === "scripted" ? "Scripted fixture provider" : "—")}
                </dd>
                <dt>Environment</dt>
                <dd>Local · synthetic integrations</dd>
                {snapshot && (
                  <>
                    <dt>Read attempts</dt>
                    <dd>{snapshot.usage.read_calls}</dd>
                    <dt>Model attempts</dt>
                    <dd>{snapshot.usage.llm_calls}</dd>
                    <dt>Input / output tokens</dt>
                    <dd>{snapshot.usage.input_tokens ?? "unknown"} / {snapshot.usage.output_tokens ?? "unknown"}</dd>
                    <dt>Human wait</dt>
                    <dd>{(snapshot.usage.human_wait_ms / 1000).toFixed(1)} s</dd>
                    <dt>Active time</dt>
                    <dd>{(snapshot.usage.active_ms / 1000).toFixed(1)} s</dd>
                  </>
                )}
              </dl>
              <p>
                “Verified” confirms the saved ticket fields. It does not confirm
                order recovery.
              </p>
            </section>
          </aside>
          <div className="investigation-column">
            <RunTimeline
              steps={snapshot?.timeline ?? []}
              running={
                snapshot?.status === "running" ||
                snapshot?.status === "queued" ||
                (!!run.runId && !snapshot && !run.error)
              }
            />
            <EvidencePanel
              evidence={snapshot?.evidence ?? []}
              hypotheses={snapshot?.hypotheses ?? []}
              missing={snapshot?.missing_checks ?? []}
              selected={selected}
              onSelect={selectEvidence}
            />
            {snapshot?.action ? (
              <ApprovalCard
                action={snapshot.action}
                waiting={
                  snapshot.status === "waiting_for_approval" && !run.error
                }
                busy={run.deciding}
                onDecision={run.decide}
                onSelect={selectEvidence}
              />
            ) : (
              <section className="empty-action">
                <span className="outline-symbol" aria-hidden="true">
                  ◇
                </span>
                <div>
                  <h3>Human approval, built in.</h3>
                  <p>
                    A saved action appears only when the evidence and policy
                    checks allow it.
                  </p>
                </div>
              </section>
            )}
          </div>
        </div>
        <footer>
          <span>OPSPILOT / PORTFOLIO MVP</span>
          <span>
            {snapshot
              ? `Last saved ${time(snapshot.updated_at)} · Asia/Jerusalem`
              : "Evidence → approval → verified execution"}
          </span>
        </footer>
      </main>
    </>
  );
}
