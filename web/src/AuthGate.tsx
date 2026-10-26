import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { setCsrf } from "./api/client";
type Me = {
  user_id: string;
  tenant_id: string | null;
  roles: string[];
  memberships: { tenant_id: string; name: string; roles: string[] }[];
  csrf_token: string;
  demo_self_approval: boolean;
};
const Identity = createContext<Me | null>(null);
export const useIdentity = () => useContext(Identity);
export function AuthGate({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mutating = useRef(false);
  useEffect(() => {
    void fetch("/auth/me", { cache: "no-store" })
      .then(async (r) => {
        if (r.ok) {
          const value = (await r.json()) as Me;
          setCsrf(value.csrf_token);
          setMe(value);
        }
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
        setError("Identity service unavailable. Reload to retry.");
      });
  }, []);
  async function mutate(path: string, body?: object) {
    if (mutating.current) return;
    mutating.current = true;
    setBusy(true);
    const r = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": me?.csrf_token ?? "",
      },
      body: JSON.stringify(body ?? {}),
    });
    if (!r.ok) {
      mutating.current = false;
      setBusy(false);
      setError("Access denied. Refresh your session and permissions.");
      return;
    }
    sessionStorage.clear();
    location.href = "/";
  }
  if (!loaded)
    return (
      <main>
        <p>Loading session…</p>
      </main>
    );
  if (!me)
    return (
      <main>
        <h1>OpsPilot Full</h1>
        <p>Sign in to your operations workspace.</p>
        {error && <p role="alert">{error}</p>}
        <a className="button primary" href="/auth/login">
          Sign in
        </a>
      </main>
    );
  return (
    <Identity.Provider value={me}>
      <div className="identity-bar">
        <span>
          Actor {me.user_id.slice(0, 8)} ·{" "}
          {me.roles.join(", ") || "No tenant selected"}
        </span>
        <label>
          Tenant{" "}
          <select
            disabled={busy}
            aria-label="Tenant"
            value={me.tenant_id ?? ""}
            onChange={(e) =>
              void mutate("/auth/tenant", { tenant_id: e.target.value })
            }
          >
            <option value="" disabled>
              Select a tenant
            </option>
            {me.memberships.map((m) => (
              <option key={m.tenant_id} value={m.tenant_id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy} onClick={() => void mutate("/auth/logout")}>
          Sign out
        </button>
        {me.demo_self_approval && (
          <strong data-testid="demo-self-approval">
            DEMO: self-approval permitted for operator + approver
          </strong>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {me.memberships.length === 0 ? (
        <main>
          <h1>No authorized memberships</h1>
          <p>Contact your tenant administrator.</p>
        </main>
      ) : me.tenant_id ? (
        children
      ) : (
        <main>
          <h1>Select an authorized tenant</h1>
        </main>
      )}
    </Identity.Provider>
  );
}
