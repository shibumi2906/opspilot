import { useEffect, useRef, useState } from "react";
import {
  privateRequest,
  downloadExport,
  newRequestId,
  errorMessage,
} from "./api/client";
import { useIdentity } from "./AuthGate";

type Row = Record<string, any>;
type Page = { items: Row[]; next_cursor: string | null; total?: number };
const initial: Page = { items: [], next_cursor: null };
export function WorkspaceViews({
  view,
  open,
}: {
  view: string;
  open: (id: string) => void;
}) {
  const identity = useIdentity()!;
  const [page, setPage] = useState<Page>(initial),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState("");
  const [customer, setCustomer] = useState(""),
    [since, setSince] = useState(""),
    [until, setUntil] = useState("");
  const [filters, setFilters] = useState(""),
    [cursor, setCursor] = useState<string | null>(null),
    [revision, setRevision] = useState(0);
  const [members, setMembers] = useState<Row[]>([]),
    [target, setTarget] = useState(""),
    [roles, setRoles] = useState<string[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const commandKeys = useRef(new Map<string, string>()),
    lock = useRef(false),
    epoch = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [view]);
  useEffect(() => {
    const controller = new AbortController();
    const current = ++epoch.current;
    setBusy(true);
    setError("");
    const path =
      view === "history"
        ? "/api/v2/runs?limit=20" +
          filters +
          (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")
        : view === "inbox"
          ? "/api/v2/inbox?limit=20" +
            (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")
          : view === "audit"
            ? "/api/v2/audit?limit=30" +
              (cursor ? "&cursor=" + encodeURIComponent(cursor) : "")
            : "/api/v2/admin/connectors";
    void privateRequest<Page>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted && current === epoch.current)
          setPage(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setPage(initial);
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    if (view === "admin")
      void privateRequest<Page>("/api/v2/admin/memberships", {
        signal: controller.signal,
      })
        .then((value) => {
          if (!controller.signal.aborted) setMembers(value.items);
        })
        .catch((reason) => {
          if (!controller.signal.aborted) setError(errorMessage(reason));
        });
    return () => {
      controller.abort();
    };
  }, [view, filters, cursor, revision]);
  async function mutate(path: string, method: string, body: Row) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      if (path.includes("connectors") || path.includes("/read")) {
        const key = path + JSON.stringify(body);
        if (!commandKeys.current.has(key))
          commandKeys.current.set(key, newRequestId());
        body = { ...body, command_id: commandKeys.current.get(key) };
      }
      await privateRequest(path, { method, body: JSON.stringify(body) });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      lock.current = false;
      setBusy(false);
      setRevision((r) => r + 1);
    }
  }
  const grouped = Object.entries(
    members.reduce<Record<string, string[]>>((all, m) => {
      (all[m.user_id] ??= []).push(m.role);
      return all;
    }, {}),
  );
  function chooseMember(id: string, current: string[]) {
    setTarget(id);
    setRoles([...current]);
    setSelectedRoles([...current]);
  }
  return (
    <section
      className="panel workspace-view"
      aria-label={
        view === "admin"
          ? "Tenant administration"
          : view === "history"
            ? "Investigation history"
            : view === "inbox"
              ? "Private inbox"
              : "Tenant audit"
      }
    >
      <h2 ref={heading} tabIndex={-1}>
        {view === "admin"
          ? "Tenant administration"
          : view === "history"
            ? "Investigation history"
            : view === "inbox"
              ? "Private inbox"
              : "Tenant audit"}
      </h2>
      <p>
        Actor {identity.user_id} · Current tenant {identity.tenant_id}
      </p>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading saved state…</p>}
      {view === "history" && (
        <form
          className="filter-form"
          onSubmit={(event) => {
            event.preventDefault();
            const params = new URLSearchParams();
            if (query) params.set("q", query);
            if (status) params.set("status", status);
            if (customer) params.set("customer_id", customer);
            if (since) params.set("since", new Date(since).toISOString());
            if (until) params.set("until", new Date(until).toISOString());
            setCursor(null);
            setFilters("&" + params.toString());
            setRevision((r) => r + 1);
          }}
        >
          <label>
            Search requests
            <input
              value={query}
              maxLength={200}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {[
                "queued",
                "running",
                "waiting_for_input",
                "waiting_for_approval",
                "completed",
                "cancelled",
                "failed",
                "needs_attention",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Customer ID
            <input
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              pattern="[0-9a-fA-F-]{36}"
            />
          </label>
          <label>
            Created after
            <input
              type="datetime-local"
              value={since}
              onChange={(e) => setSince(e.target.value)}
            />
          </label>
          <label>
            Created before
            <input
              type="datetime-local"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
          </label>
          <button disabled={busy}>Apply filters</button>
        </form>
      )}
      {view === "history" && (
        <>
          <p>{page.total ?? 0} matching investigations</p>
          <ul className="workspace-list">
            {page.items.map((item) => (
              <li key={item.run_id}>
                <button onClick={() => open(item.run_id)}>
                  {item.request || "Open investigation"}
                </button>
                <p>
                  {item.status} · {new Date(item.created_at).toLocaleString()} ·
                  Actor {item.actor_id}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
      {view === "inbox" && (
        <>
          <p>Only notifications addressed to you are shown.</p>
          <ul className="workspace-list">
            {page.items.map((item) => (
              <li key={item.id}>
                <p className="preserve-text">{item.body}</p>
                <p>
                  Customer {item.customer_id} ·{" "}
                  {new Date(item.created_at).toLocaleString()} ·{" "}
                  {item.read_at ? "Read" : "Unread"}
                </p>
                {item.run_id && (
                  <button onClick={() => open(item.run_id)}>
                    Open related investigation
                  </button>
                )}
                <button
                  disabled={busy || !!item.read_at}
                  onClick={() =>
                    void mutate(`/api/v2/inbox/${item.id}/read`, "POST", {})
                  }
                >
                  Mark read
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {view === "audit" && (
        <>
          <p>
            Redacted event metadata only. Each download is limited to one page.
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void downloadExport(
                "/api/v2/audit/export" +
                  (cursor ? "?cursor=" + encodeURIComponent(cursor) : ""),
              ).catch((reason) => setError(errorMessage(reason)))
            }
          >
            Download audit page
          </button>
          <ul className="workspace-list">
            {page.items.map((item) => (
              <li key={item.event_id}>
                <p>
                  {item.type} · {item.reason_code} ·{" "}
                  {new Date(item.timestamp).toLocaleString()}
                </p>
                <p>
                  Run {item.run_id} · Actor {item.actor_id || "Service"} · Event{" "}
                  {item.sequence}
                </p>
                <button onClick={() => open(item.run_id)}>
                  Open investigation
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {view === "admin" && (
        <>
          <h3>Connections</h3>
          <p>
            Execution can be enabled or disabled here. Credentials are managed
            by your identity and secrets administrators.
          </p>
          <ul className="workspace-list">
            {page.items.map((item) => (
              <li key={item.id}>
                <strong>{item.type}</strong>
                <p>
                  Customer {item.customer_id} · Connection {item.id} · Version{" "}
                  {item.version} · {item.enabled ? "Enabled" : "Disabled"}
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    void mutate(`/api/v2/admin/connectors/${item.id}`, "PUT", {
                      enabled: !item.enabled,
                      expected_version: item.version,
                    })
                  }
                >
                  {item.enabled ? "Disable" : "Enable"} connection
                </button>
              </li>
            ))}
          </ul>
          <h3>Memberships</h3>
          <p>
            Changing access affects only this tenant. Administrative changes
            require a recent sign-in. <a href="/auth/login">Sign in again</a>
          </p>
          <ul className="workspace-list">
            {grouped.map(([id, current]) => (
              <li key={id}>
                <p>
                  {id} · {current.join(", ")}
                </p>
                <button onClick={() => chooseMember(id, current)}>
                  Edit member {id.slice(0, 8)}
                </button>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void mutate(`/api/v2/admin/memberships/${target}`, "PUT", {
                roles,
                expected_roles: selectedRoles,
              });
            }}
          >
            <label>
              Member ID
              <input
                required
                pattern="[0-9a-fA-F-]{36}"
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  setSelectedRoles([]);
                }}
              />
            </label>
            <fieldset>
              <legend>Roles in this tenant</legend>
              {["operator", "approver", "auditor", "admin"].map((role) => (
                <label key={role}>
                  <input
                    type="checkbox"
                    checked={roles.includes(role)}
                    onChange={(e) =>
                      setRoles((r) =>
                        e.target.checked
                          ? [...r, role]
                          : r.filter((v) => v !== role),
                      )
                    }
                  />
                  {role}
                </label>
              ))}
            </fieldset>
            <button disabled={busy || !target}>Save membership</button>
          </form>
          <h3>Account access</h3>
          <p>
            Global account operations are available only for users exclusively
            managed by this tenant. Shared accounts must be handled by the
            identity administrator.
          </p>
          <button
            disabled={busy || !target}
            onClick={() =>
              void mutate(
                `/api/v2/admin/users/${target}/sessions/revoke-all`,
                "POST",
                {},
              )
            }
          >
            Revoke member sessions
          </button>
          <button
            disabled={busy || !target}
            onClick={() =>
              void mutate(`/api/v2/admin/users/${target}/status`, "PUT", {
                enabled: false,
              })
            }
          >
            Disable member account
          </button>
          <button
            disabled={busy || !target}
            onClick={() =>
              void mutate(`/api/v2/admin/users/${target}/status`, "PUT", {
                enabled: true,
              })
            }
          >
            Enable member account
          </button>
        </>
      )}
      {page.items.length === 0 && !busy && <p>No accessible records.</p>}
      {view !== "admin" && (
        <div className="pagination">
          <button disabled={busy || !cursor} onClick={() => setCursor(null)}>
            First page
          </button>
          <button
            disabled={busy || !page.next_cursor}
            onClick={() => setCursor(page.next_cursor)}
          >
            Next page
          </button>
        </div>
      )}
    </section>
  );
}
