import type { Evidence, Hypothesis } from "../api/types";
import {
  EvidenceLinks,
  SectionHeader,
  time,
  type SelectEvidence,
} from "./shared";
export function EvidencePanel({
  evidence,
  hypotheses,
  missing,
  selected,
  onSelect,
}: {
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  missing: string[];
  selected: string | null;
  onSelect: SelectEvidence;
}) {
  const item = evidence.find((value) => value.evidence_id === selected);
  return (
    <section className="panel evidence-panel">
      <SectionHeader
        number="02"
        title="Evidence & interpretation"
        label={`${evidence.length} sources`}
      />
      {evidence.length === 0 ? (
        <p className="muted empty-line">
          Source observations appear here. Hypotheses stay separate from facts.
        </p>
      ) : (
        <div className="sources">
          {evidence.map((value, index) => (
            <button
              type="button"
              key={value.evidence_id}
              className={`source-button ${selected === value.evidence_id ? "selected" : ""}`}
              onClick={() => onSelect(value.evidence_id)}
              aria-expanded={selected === value.evidence_id}
            >
              <span className="source-index">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span>
                <strong>{value.source_type.replaceAll("_", " ")}</strong>
                <small>{value.tool_name}</small>
              </span>
              <span aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      )}
      {selected && !item && (
        <p role="status" className="notice">
          This evidence reference is unavailable in the current snapshot.
        </p>
      )}
      {item && (
        <article
          id="evidence-detail"
          className="evidence-detail"
          aria-label="Evidence detail"
          tabIndex={-1}
        >
          <div className="detail-heading">
            <span className="eyebrow">Source observation</span>
            <button
              type="button"
              className="text-button"
              onClick={() => onSelect("")}
            >
              Close ×
            </button>
          </div>
          <h3>{item.source_type.replaceAll("_", " ")}</h3>
          <dl className="detail-meta">
            <dt>Observed</dt>
            <dd>{time(item.observed_at)} · Asia/Jerusalem</dd>
            <dt>Source ID</dt>
            <dd className="mono">{item.source_id}</dd>
            {item.source_version && (
              <>
                <dt>Version</dt>
                <dd>{item.source_version}</dd>
              </>
            )}
            <dt>Evidence ID</dt>
            <dd className="mono">{item.evidence_id}</dd>
          </dl>
          <pre>{JSON.stringify(item.facts, null, 2)}</pre>
          <p className="source-excerpt">{item.excerpt}</p>
        </article>
      )}
      {hypotheses.map((hypothesis) => (
        <article className="hypothesis" key={hypothesis.hypothesis_id}>
          <div className="detail-heading">
            <span className="eyebrow">AI hypothesis · interpretation</span>
            <span className="confidence">
              {hypothesis.confidence_label} confidence
            </span>
          </div>
          <p>{hypothesis.summary}</p>
          <EvidenceLinks
            ids={hypothesis.supporting_evidence_ids}
            onSelect={onSelect}
          />
          {hypothesis.contradicting_evidence_ids.length > 0 && (
            <>
              <p className="muted">Contradicting evidence</p>
              <EvidenceLinks
                ids={hypothesis.contradicting_evidence_ids}
                onSelect={onSelect}
              />
            </>
          )}
        </article>
      ))}
      {missing.length > 0 && (
        <div className="notice">
          <strong>Checks still missing</strong>
          <ul>
            {missing.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
