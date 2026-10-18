import type { Decision, PublicConfig, RunSnapshot } from "./types";
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    cache: "no-store",
    signal: options.signal ?? AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      body?.error?.code ?? "SERVICE_UNAVAILABLE",
    );
  }
  return response.json() as Promise<T>;
}
export const api = {
  config: (signal: AbortSignal) =>
    request<PublicConfig>("/api/v1/config", { signal }),
  snapshot: (id: string, signal: AbortSignal) =>
    request<RunSnapshot>(`/api/v1/runs/${encodeURIComponent(id)}`, { signal }),
  create: (text: string, key: string) =>
    request<{ run_id: string; status: string }>("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify({ request: text, client_request_id: key }),
    }),
  decide: (id: string, actionId: string, decision: Decision) =>
    request(`/api/v1/runs/${encodeURIComponent(id)}/decision`, {
      method: "POST",
      body: JSON.stringify({ action_id: actionId, decision }),
    }),
};
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404)
      return "This investigation could not be found. Check the link or start a new one.";
    if (error.status === 409)
      return "The server already has a different state. Refreshing the saved decision.";
    if (error.status === 422)
      return "The request could not be accepted. Check your input.";
  }
  return "Connection interrupted. Your investigation link is preserved; reconnecting automatically.";
}

// getRandomValues also works on the HTTP origin used by the isolated Docker browser.
export function newRequestId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}
