import type { Evidence, RunSnapshot } from "../api/types";
export const time = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        timeZone: "Asia/Jerusalem",
        dateStyle: "medium",
        timeStyle: "medium",
      })
    : "—";
export const shortId = (value: string) => value.slice(0, 8);
export function EvidenceLinks({
  ids,
  onSelect,
}: {
  ids: string[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="evidence-links">
      {ids.map((id, i) => (
        <button type="button" key={id} onClick={() => onSelect(id)} title={id}>
          ↗ Evidence {i + 1}
        </button>
      ))}
    </div>
  );
}
export function SectionHeader({
  number,
  title,
  label,
}: {
  number: string;
  title: string;
  label?: string;
}) {
  return (
    <div className="section-heading">
      <span className="section-number">{number}</span>
      <h2>{title}</h2>
      {label && <span className="eyebrow section-label">{label}</span>}
    </div>
  );
}
export function Status({ snapshot }: { snapshot: RunSnapshot | null }) {
  const status = snapshot?.status;
  const verified = snapshot?.outcome === "actions_verified";
  const label = verified
    ? "Ticket verified"
    : status === "waiting_for_approval"
      ? "Your approval needed"
      : status === "running" || status === "queued"
        ? "Investigating"
        : status === "failed"
          ? "Investigation failed"
          : status === "completed"
            ? snapshot?.outcome === "rejected"
              ? "Action rejected"
              : "Review result"
            : "Ready to investigate";
  return (
    <span
      className={`status-pill ${verified ? "verified" : status === "failed" ? "danger" : status === "waiting_for_approval" ? "waiting" : ""}`}
      role="status"
    >
      <i
        className={status === "running" || status === "queued" ? "pulse" : ""}
      />
      {label}
    </span>
  );
}
export type SelectEvidence = (id: string) => void;
export type EvidenceItem = Evidence;
