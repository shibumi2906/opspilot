import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { SessionControls } from "./SessionControls";
import { setCsrf } from "./api/client";
import { AUTH_LOST, clearPrivateState } from "./api/privacy";
type Me = {
  user_id: string;
  tenant_id: string | null;
  roles: string[];
  memberships: { tenant_id: string; name: string; roles: string[] }[];
  csrf_token: string;
  demo_self_approval: boolean;
  session_expires_at: string | null;
  session_idle_expires_at: string | null;
  session_idle_seconds: number;
};
const Identity = createContext<Me | null>(null);
export const useIdentity = () => useContext(Identity);
export function AuthGate({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [switchingTenant, setSwitchingTenant] = useState(false);
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
  useEffect(() => {
    const clear = () => {
      setMe(null);
      setCsrf("");
      setBusy(false);
      mutating.current = false;
    };
    window.addEventListener(AUTH_LOST, clear);
    return () => window.removeEventListener(AUTH_LOST, clear);
  }, []);
  useEffect(() => {
    if (!me) return;
    let expiry = Math.min(
      Date.parse(me.session_expires_at ?? ""),
      Date.parse(me.session_idle_expires_at ?? ""),
    );
    let lastBeat = 0,
      sending = false,
      disposed = false;
    const activity = async (event: Event) => {
      if (!event.isTrusted || sending || Date.now() - lastBeat < 30000) return;
      sending = true;
      lastBeat = Date.now();
      try {
        const r = await fetch("/auth/activity", {
          method: "POST",
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": me.csrf_token,
          },
          body: "{}",
          signal: AbortSignal.timeout(5000),
        });
        if (!disposed && r.ok) {
          const value: Me = await r.json();
          expiry = Math.min(
            Date.parse(value.session_expires_at ?? ""),
            Date.parse(value.session_idle_expires_at ?? ""),
          );
        } else if (!disposed && [401, 403].includes(r.status))
          clearPrivateState();
      } catch {
        /* Offline never extends the last server-authorized deadline. */
      } finally {
        sending = false;
      }
    };
    const events = ["pointerdown", "keydown", "scroll"];
    events.forEach((name) =>
      window.addEventListener(name, activity, { passive: true }),
    );
    const timer = window.setInterval(() => {
      if (Number.isFinite(expiry) && Date.now() >= expiry) clearPrivateState();
    }, 1000);
    return () => {
      disposed = true;
      clearInterval(timer);
      events.forEach((name) => window.removeEventListener(name, activity));
    };
  }, [me]);
  async function mutate(path: string, body?: object) {
    if (mutating.current) return;
    mutating.current = true;
    setBusy(true);
    const token = me?.csrf_token ?? "";
    if (path === "/auth/tenant") setSwitchingTenant(true);
    if (path === "/auth/logout") {
      setSigningOut(true);
      clearPrivateState();
    }
    let r: Response;
    try {
      r = await fetch(path, {
        method: "POST",
        signal: AbortSignal.timeout(5000),
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify(body ?? {}),
      });
    } catch {
      setSigningOut(false);
      setSwitchingTenant(false);
      mutating.current = false;
      setBusy(false);
      setError(
        path === "/auth/logout"
          ? "Private data cleared locally. Server sign-out could not be confirmed; retry when online."
          : "Connection unavailable.",
      );
      return;
    }
    if (!r.ok) {
      setSigningOut(false);
      setSwitchingTenant(false);
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
        {signingOut ? (
          <p role="status">Signing out…</p>
        ) : (
          <a className="button primary" href="/auth/login">
            Sign in
          </a>
        )}
      </main>
    );
  return (
    <Identity.Provider value={me}>
      <div className="identity-bar">
        <span>
          Actor {me.user_id} · {me.roles.join(", ") || "No tenant selected"}
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
        <SessionControls csrf={me.csrf_token} />
        {me.demo_self_approval && (
          <strong data-testid="demo-self-approval">
            DEMO: self-approval permitted for operator + approver
          </strong>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {switchingTenant ? (
        <main role="status">Switching tenant...</main>
      ) : me.memberships.length === 0 ? (
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
