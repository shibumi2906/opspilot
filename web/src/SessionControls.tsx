import { useState } from "react";
import { clearPrivateState } from "./api/privacy";

type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
};
export function SessionControls({ csrf }: { csrf: string }) {
  const [items, setItems] = useState<Session[] | null>(null);
  const [current, setCurrent] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      const r = await fetch("/auth/sessions", {
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if ([401, 403].includes(r.status)) {
        clearPrivateState();
        return;
      }
      if (!r.ok) throw new Error();
      const body = (await r.json()) as { items: Session[]; current: string };
      setItems(body.items);
      setCurrent(body.current);
      setError("");
    } catch {
      setError("Could not load sessions. Retry when connected.");
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id?: string) {
    setBusy(true);
    try {
      const r = await fetch(
        id ? `/auth/sessions/${id}` : "/auth/sessions/revoke-all",
        {
          method: id ? "DELETE" : "POST",
          cache: "no-store",
          signal: AbortSignal.timeout(5000),
          headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json" },
          body: "{}",
        },
      );
      if (r.status === 401) {
        clearPrivateState();
        return;
      }
      if (!r.ok) throw new Error();
      if (!id || id === current) {
        clearPrivateState();
        return;
      }
      await load();
    } catch {
      setError("Session revocation was not confirmed. Retry or sign in again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        disabled={busy}
        onClick={() => (items ? setItems(null) : void load())}
      >
        Sessions
      </button>
      {items && (
        <section aria-label="Active sessions">
          <h2>Active sessions</h2>
          <p>
            Revocation requires a recent sign-in.{" "}
            <a href="/auth/login">Sign in again</a>
          </p>
          <ul>
            {items.map((s) => (
              <li key={s.id}>
                {s.id === current
                  ? "This session"
                  : `Session ${s.id.slice(0, 8)}`}{" "}
                · Last activity {new Date(s.last_seen_at).toLocaleString()}
                <button disabled={busy} onClick={() => void revoke(s.id)}>
                  Revoke {s.id === current ? "this session" : s.id.slice(0, 8)}
                </button>
              </li>
            ))}
          </ul>
          <button disabled={busy} onClick={() => void revoke()}>
            Revoke all sessions
          </button>
        </section>
      )}
      {error && <p role="alert">{error}</p>}
    </>
  );
}
