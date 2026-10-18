import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage, newRequestId } from "../api/client";
import type { Decision, RunSnapshot } from "../api/types";
const validId = (id: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
const terminal = (status?: string) =>
  status === "completed" || status === "failed";
export function useRun() {
  const [runId, setRunId] = useState(() =>
    new URLSearchParams(location.search).get("run_id"),
  );
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [nonce, setNonce] = useState(0);
  const createLock = useRef(false),
    decisionLock = useRef(false),
    reconcile = useRef(false);
  const requestKey = useRef<{ text: string; key: string } | null>(null);
  const pollEpoch = useRef(0);
  const currentRun = useRef(runId);
  currentRun.current = runId;
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  const changeRun = useCallback((id: string | null, push = true) => {
    currentRun.current = id;
    setRunId(id);
    setSnapshot(null);
    setError(null);
    setMutationError(null);
    decisionLock.current = false;
    reconcile.current = false;
    setDeciding(false);
    if (push) {
      const url = new URL(location.href);
      id
        ? url.searchParams.set("run_id", id)
        : url.searchParams.delete("run_id");
      history.pushState(null, "", url);
    }
  }, []);
  useEffect(() => {
    const pop = () =>
      changeRun(new URLSearchParams(location.search).get("run_id"), false);
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, [changeRun]);
  useEffect(() => {
    if (!runId) return;
    if (!validId(runId)) {
      setError(
        "This investigation link is invalid. Start a new investigation.",
      );
      return;
    }
    let disposed = false,
      failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      let done = false;
      const epoch = pollEpoch.current;
      try {
        const value = await api.snapshot(
          runId,
          AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
        );
        if (disposed || epoch !== pollEpoch.current) return;
        setSnapshot(value);
        setError(null);
        failures = 0;
        done = terminal(value.status);
        if (reconcile.current) {
          reconcile.current = false;
          decisionLock.current = false;
          setDeciding(false);
          if (value.action?.approval_status !== "pending")
            setMutationError(null);
        }
      } catch (reason) {
        if (disposed || epoch !== pollEpoch.current) return;
        setError(errorMessage(reason));
        failures++;
        if (reason instanceof ApiError && [404, 422].includes(reason.status))
          done = true;
      }
      if (!disposed && !done)
        timer = setTimeout(
          poll,
          Math.min(5000, 1000 * 2 ** Math.min(failures, 3)),
        );
    };
    void poll();
    const online = () => refresh();
    window.addEventListener("online", online);
    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(timer);
      window.removeEventListener("online", online);
    };
  }, [runId, nonce, refresh]);
  const start = async (text: string) => {
    if (createLock.current) return;
    createLock.current = true;
    setCreating(true);
    setMutationError(null);
    try {
      if (requestKey.current?.text !== text)
        requestKey.current = { text, key: newRequestId() };
      const value = await api.create(text, requestKey.current.key);
      changeRun(value.run_id);
    } catch (reason) {
      setMutationError(errorMessage(reason));
    } finally {
      createLock.current = false;
      setCreating(false);
    }
  };
  const decide = async (choice: Decision) => {
    if (
      decisionLock.current ||
      !snapshot?.action ||
      snapshot.status !== "waiting_for_approval" ||
      snapshot.action.approval_status !== "pending"
    )
      return;
    decisionLock.current = true;
    setDeciding(true);
    setMutationError(null);
    const id = snapshot.run_id;
    try {
      await api.decide(id, snapshot.action.action_id, choice);
    } catch {
      if (currentRun.current === id)
        setMutationError(
          "The decision response was interrupted. Checking the saved server state before allowing a retry.",
        );
    } finally {
      if (currentRun.current === id) {
        pollEpoch.current++;
        reconcile.current = true;
        refresh();
      }
    }
  };
  const reset = () => {
    requestKey.current = null;
    changeRun(null);
  };
  return {
    runId,
    snapshot,
    error,
    mutationError,
    creating,
    deciding,
    start,
    decide,
    reset,
    refresh,
    terminal: terminal(snapshot?.status),
  };
}
