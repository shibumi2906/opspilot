import { useEffect, useRef, useState } from "react";
import { useIdentity } from "./AuthGate";
import {
  privateRequest,
  downloadExport,
  newRequestId,
  errorMessage,
} from "./api/client";
import type { Action, RunSnapshot } from "./api/types";
export function RunControls({
  snapshot,
  refresh,
}: {
  snapshot: RunSnapshot;
  refresh: () => void;
}) {
  const identity = useIdentity()!,
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [choice, setChoice] = useState("");
  const lock = useRef(false),
    keys = useRef(new Map<string, string>());
  const owner =
    identity.roles.includes("operator") &&
    snapshot.actor_id === identity.user_id;
  const form = snapshot.clarification;
  useEffect(() => {
    setChoice("");
    setError("");
  }, [form?.id]);
  async function send(path: string, body: any) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    const key = path + JSON.stringify(body);
    if (!keys.current.has(key)) keys.current.set(key, newRequestId());
    try {
      await privateRequest(path, {
        method: "POST",
        body: JSON.stringify({ ...body, command_id: keys.current.get(key) }),
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      lock.current = false;
      setBusy(false);
      refresh();
    }
  }
  const active = [
    "queued",
    "running",
    "waiting_for_input",
    "waiting_for_approval",
  ].includes(snapshot.status);
  return (
    <section className="panel run-controls" aria-label="Investigation controls">
      <h2>Investigation controls</h2>
      <p>
        Actor {snapshot.actor_id} · {snapshot.status}
      </p>
      {error && <p role="alert">{error}</p>}
      {owner &&
        form &&
        !form.answered &&
        snapshot.status === "waiting_for_input" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(`/api/v2/runs/${snapshot.run_id}/clarifications`, {
                clarification_id: form.id,
                expected_version: form.version,
                kind: form.kind,
                choice,
              });
            }}
          >
            <h3>More information needed</h3>
            <p>
              Answer before {new Date(form.expires_at).toLocaleString()}. Round{" "}
              {form.version}.
            </p>
            <label>
              Choose {form.kind}
              {form.options.length ? (
                <select
                  required
                  value={choice}
                  onChange={(e) => setChoice(e.target.value)}
                >
                  <option value="" disabled>
                    Select an option
                  </option>
                  {form.options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  required
                  maxLength={100}
                  value={choice}
                  onChange={(e) => setChoice(e.target.value)}
                />
              )}
            </label>
            <button
              disabled={
                busy || !choice || Date.now() >= Date.parse(form.expires_at)
              }
            >
              Submit clarification
            </button>
          </form>
        )}
      {owner && active && (
        <button
          disabled={busy}
          onClick={() =>
            void send(`/api/v2/runs/${snapshot.run_id}/cancel`, {})
          }
        >
          Cancel investigation
        </button>
      )}
      {snapshot.status === "cancelling" && (
        <p role="status">
          Cancellation requested. Committed or uncertain effects are retained.
        </p>
      )}
      <button
        disabled={busy}
        onClick={() =>
          void downloadExport(`/api/v2/runs/${snapshot.run_id}/export`).catch(
            (reason) => setError(errorMessage(reason)),
          )
        }
      >
        Download investigation metadata
      </button>
      {(snapshot.status === "needs_attention" ||
        snapshot.outcome === "unknown_outcome" ||
        snapshot.action?.execution_status === "unknown" ||
        snapshot.actions?.some((a) => a.execution_status === "unknown")) && (
        <div role="status">
          <h3>Reconciliation required</h3>
          <p>
            Review the saved operation IDs and verification status below.
            Unknown effects must be checked with the destination owner; do not
            repeat a write.
          </p>
          <button onClick={refresh}>Check saved reconciliation state</button>
        </div>
      )}
    </section>
  );
}
export function RevisionControls({
  action,
  snapshot,
  refresh,
}: {
  action: Action;
  snapshot: RunSnapshot;
  refresh: () => void;
}) {
  const identity = useIdentity()!,
    [editing, setEditing] = useState(false),
    [draft, setDraft] = useState(action.arguments),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const owner =
    identity.roles.includes("operator") &&
    snapshot.actor_id === identity.user_id;
  useEffect(() => {
    setEditing(false);
    setDraft(action.arguments);
    setError("");
  }, [action.action_id]);
  async function send(path: string, body: any) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await privateRequest(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setEditing(false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      lock.current = false;
      setBusy(false);
      refresh();
    }
  }
  return (
    <section
      className="revision-controls"
      aria-label={`Revision controls ${action.key ?? action.action_id}`}
    >
      {error && <p role="alert">{error}</p>}
      {owner &&
        action.execution_status === "not_started" &&
        action.expected_version < 2 &&
        ["pending", "approved"].includes(action.approval_status) &&
        snapshot.status === "waiting_for_approval" && (
          <button disabled={busy} onClick={() => setEditing((v) => !v)}>
            Edit proposed revision
          </button>
        )}
      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(`/api/v2/actions/${action.logical_action_id}/revisions`, {
              expected_version: action.expected_version,
              arguments: draft,
            });
          }}
        >
          <p>
            A saved edit creates a new revision and requires a separate
            decision. Customer and evidence remain bound to this investigation.
          </p>
          {"title" in draft ? (
            <>
              <label>
                Revision title
                <input
                  required
                  maxLength={200}
                  value={draft.title}
                  onChange={(e) =>
                    setDraft({ ...draft, title: e.target.value })
                  }
                />
              </label>
              <label>
                Revision description
                <textarea
                  required
                  maxLength={6000}
                  value={draft.description}
                  onChange={(e) =>
                    setDraft({ ...draft, description: e.target.value })
                  }
                />
              </label>
              <label>
                Revision priority
                <select
                  value={draft.priority}
                  onChange={(e) =>
                    setDraft({ ...draft, priority: e.target.value })
                  }
                >
                  {["low", "medium", "high"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <>
              <label>
                Revision body
                <textarea
                  required
                  maxLength={6000}
                  value={draft.body}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                />
              </label>
              <label>
                {action.tool_name === "add_ticket_comment"
                  ? "Revision ticket ID"
                  : "Revision recipient ID"}
                <input
                  required
                  pattern="[0-9a-fA-F-]{36}"
                  value={draft.ticket_id ?? draft.recipient_id ?? ""}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      [action.tool_name === "add_ticket_comment"
                        ? "ticket_id"
                        : "recipient_id"]: e.target.value,
                    })
                  }
                />
              </label>
            </>
          )}
          <button disabled={busy}>Save new revision</button>
          <button type="button" onClick={() => setEditing(false)}>
            Discard edit
          </button>
        </form>
      )}
      {identity.roles.includes("approver") &&
        action.approval_status === "approved" &&
        action.execution_status === "not_started" && (
          <button
            disabled={busy}
            onClick={() =>
              void send(`/api/v2/actions/${action.action_id}/revoke`, {
                expected_version: action.expected_version,
              })
            }
          >
            Revoke this approval
          </button>
        )}
    </section>
  );
}
