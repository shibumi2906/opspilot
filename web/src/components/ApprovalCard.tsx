import type { Action, Decision } from "../api/types";
import { EvidenceLinks, SectionHeader, type SelectEvidence } from "./shared";
export function ApprovalCard({
  canApprove = true,
  action,
  waiting,
  busy,
  onDecision,
  onSelect,
}: {
  canApprove?: boolean;
  action: Action;
  waiting: boolean;
  busy: boolean;
  onDecision: (decision: Decision) => Promise<void>;
  onSelect: SelectEvidence;
}) {
  const pending = action.approval_status === "pending";
  const expired = Date.parse(action.expires_at) <= Date.now();
  return (
    <section className="approval-panel" data-testid="approval-card">
      <SectionHeader
        number="03"
        title="One proposed action"
        label="Human authority"
      />
      <div className="approval-intro">
        <span className="ticket-icon" aria-hidden="true">
          ▤
        </span>
        <div>
          <h3>{{create_ticket: "Create an internal ticket", add_ticket_comment: "Add a ticket comment", notify_manager: "Notify an internal recipient"}[action.tool_name]}</h3>
          <p>
            Records the issue for follow-up. Credentials and the integration
            stay unchanged.
          </p>
        </div>
        <span
          className={`decision-badge ${action.approval_status}`}
          data-testid="approval-status"
        >
          {action.approval_status}
        </span>
      </div>
      <p>Revision {action.expected_version} · Approval expires <time dateTime={action.expires_at}>{new Date(action.expires_at).toLocaleString()}</time>{expired && pending ? " · Expired; refresh the saved decision." : ""}</p>
      <dl className="payload">
        <dt>Customer ID</dt>
        <dd className="mono" data-testid="ticket-customer">
          {action.arguments.customer_id}
        </dd>
        {"title" in action.arguments ? <>
          <dt>Title</dt>
          <dd data-testid="ticket-title">{action.arguments.title}</dd>
          <dt>Description</dt>
          <dd className="description" data-testid="ticket-description">{action.arguments.description}</dd>
          <dt>Priority</dt>
          <dd data-testid="ticket-priority"><span className="priority">{action.arguments.priority}</span></dd>
        </> : <>
          <dt>{action.tool_name === "add_ticket_comment" ? "Ticket ID" : "Recipient ID"}</dt>
          <dd className="mono">{action.arguments.ticket_id ?? action.arguments.recipient_id}</dd>
          <dt>Body</dt>
          <dd className="description" data-testid="operation-body">{action.arguments.body}</dd>
        </>}
        <dt>Evidence IDs</dt>
        <dd>
          <ul className="exact-evidence">
            {action.arguments.evidence_ids.map((id) => (
              <li key={id} className="mono">
                {id}
              </li>
            ))}
          </ul>
          <EvidenceLinks
            ids={action.arguments.evidence_ids}
            onSelect={onSelect}
          />
        </dd>
      </dl>
      <details className="integrity">
        <summary>Saved action & integrity</summary>
        <dl>
          <dt>Action ID</dt>
          <dd className="mono" data-testid="action-id">
            {action.action_id}
          </dd>
          <dt>Tool</dt>
          <dd className="mono">{action.tool_name}</dd>
          <dt>Payload SHA-256</dt>
          <dd className="mono">{action.arguments_hash}</dd>
          <dt>Execution</dt>
          <dd>{action.execution_status}</dd>
        </dl>
      </details>
      {pending ? (
        <>
          <div className="approval-note">
            <span aria-hidden="true">◇</span>
            <p>
              The core is paused. Your decision applies to exactly the saved
              fields above.
            </p>
          </div>
          <div className="decision-buttons">
            <button
              type="button"
              className="button secondary"
              disabled={!canApprove || !waiting || busy || expired}
              onClick={() => void onDecision("reject")}
            >
              Reject action
            </button>
            <button
              type="button"
              className="button primary"
              disabled={!canApprove || !waiting || busy || expired}
              onClick={() => void onDecision("approve")}
            >
              {busy ? "Checking saved decision…" : {create_ticket: "Approve & create ticket", add_ticket_comment: "Approve & add comment", notify_manager: "Approve & notify recipient"}[action.tool_name]}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
        </>
      ) : (
        <p className="decision-saved" role="status">
          Decision saved: {action.approval_status}. The exact card remains
          available for review.
        </p>
      )}
    </section>
  );
}
