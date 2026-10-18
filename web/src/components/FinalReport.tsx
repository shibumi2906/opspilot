import type { RunSnapshot } from "../api/types";
import { EvidenceLinks, type SelectEvidence } from "./shared";
export function FinalReport({
  snapshot,
  onSelect,
}: {
  snapshot: RunSnapshot;
  onSelect: SelectEvidence;
}) {
  const report = snapshot.report;
  if (snapshot.status === "failed")
    return (
      <section className="result-panel failed" aria-label="Final report">
        <span className="eyebrow">Investigation failed</span>
        <h2>Execution needs review.</h2>
        <p>
          {snapshot.error?.message ??
            "The workflow could not finish. No verified success is available."}
        </p>
        <code>{snapshot.error?.code ?? "RUN_FAILED"}</code>
        <p className="muted">
          Keep this investigation link. Review the saved action before starting
          another run.
        </p>
      </section>
    );
  if (!report || snapshot.status !== "completed") return null;
  return (
    <section
      className={`result-panel ${report.outcome === "actions_verified" ? "success" : "caution"}`}
      aria-label="Final report"
    >
      <span className="eyebrow">
        Final report · {report.outcome.replaceAll("_", " ")}
      </span>
      <h2>
        {report.outcome === "actions_verified"
          ? "Ticket verified."
          : report.outcome === "rejected"
            ? "Decision respected."
            : "Review the findings."}
      </h2>
      <p>{report.summary}</p>
      <div className="report-divider" />
      <h3>Diagnosis</h3>
      {report.facts.length ? (
        report.facts.map((fact, index) => (
          <div className="report-fact" key={index}>
            <p>{fact.statement}</p>
            <EvidenceLinks ids={fact.evidence_ids} onSelect={onSelect} />
          </div>
        ))
      ) : (
        <p>No confirmed diagnosis is available.</p>
      )}
      <h3>Ticket creation</h3>
      <p>{report.action_summary}</p>
      {report.ticket_id && (
        <p className="ticket-id mono" data-testid="created-ticket-id">
          {report.ticket_id}
        </p>
      )}
      <h3>Verification</h3>
      <p
        className={`verification ${report.verification_status}`}
        data-testid="verification-status"
      >
        {report.verification_status.replaceAll("_", " ")}
      </p>
      {report.missing_checks.length > 0 && (
        <>
          <h3>Missing checks</h3>
          <ul>
            {report.missing_checks.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </>
      )}
      <div className="remaining">
        <strong>Still unresolved</strong>
        <p>{report.remaining_problem}</p>
      </div>
    </section>
  );
}
