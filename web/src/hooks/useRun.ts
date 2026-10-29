import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage, newRequestId } from "../api/client";
import { watchRun, type StreamSnapshot } from "../api/stream";
import { AUTH_LOST } from "../api/privacy";
import type { Action, Decision, RunSnapshot } from "../api/types";
const validId = (id: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
const terminal = (status?: string) =>
  ["completed", "failed", "cancelled", "needs_attention"].includes(
    status ?? "",
  );
export function useRun() {
  const [runId, setRunId] = useState(() =>
    new URLSearchParams(location.search).get("run_id"),
  );
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const streamSnapshot = useRef<StreamSnapshot | false | null>(null);
  const streamGeneration = useRef(0);
  const snapshotListeners = useRef(new Set<() => void>());
  const wake = useRef<((version?: number) => void) | null>(null);
  const createLock = useRef(false),
    decisionLock = useRef(false),
    reconcile = useRef(false);
  const requestKey = useRef<{ text: string; key: string } | null>(null);
  const pollEpoch = useRef(0);
  const currentRun = useRef(runId);
  currentRun.current = runId;
  const refresh = useCallback(() => wake.current?.(), []);
  const changeRun = useCallback((id: string | null, push = true) => {
    currentRun.current = id;
    setRunId(id);
    setSnapshot(null);
    streamSnapshot.current = null;
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
      streamSnapshot.current = false;
      setError(
        "This investigation link is invalid. Start a new investigation.",
      );
      return;
    }
    let disposed = false,
      inFlight = false,
      forceRead = false,
      wantedVersion = -1,
      failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      if (disposed || inFlight) return;
      inFlight = true;
      forceRead = false;
      let done = false;
      const epoch = pollEpoch.current;
      try {
        const value = await api.snapshot(
          runId,
          AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
        );
        if (disposed) return;
        if (epoch !== pollEpoch.current) {
          forceRead = true;
          return;
        }
        streamSnapshot.current =
          typeof value.latest_event_id === "string" &&
          Number.isSafeInteger(value.snapshot_version)
            ? {
                cursor: value.latest_event_id,
                sequence: value.snapshot_version,
                generation: ++streamGeneration.current,
              }
            : null;
        snapshotListeners.current.forEach((notify) => notify());
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
        if (disposed) return;
        if (epoch !== pollEpoch.current) {
          forceRead = true;
          return;
        }
        if (
          reason instanceof ApiError &&
          [401, 403, 404].includes(reason.status)
        ) {
          streamSnapshot.current = false;
          snapshotListeners.current.forEach((notify) => notify());
          setSnapshot(null);
          setMutationError(null);
        }
        setError(errorMessage(reason));
        failures++;
        if (reason instanceof ApiError && [404, 422].includes(reason.status))
          done = true;
      } finally {
        inFlight = false;
        if (!disposed) {
          const current = streamSnapshot.current;
          if (done && current === false) {
            wantedVersion = -1;
            forceRead = false;
          }
          const again =
            forceRead ||
            (wantedVersion >= 0 &&
              (!current || current.sequence < wantedVersion));
          if (again || !done)
            timer = setTimeout(
              poll,
              again
                ? 1000
                : Math.min(
                    10000,
                    5000 * 2 ** Math.max(0, Math.min(failures, 2) - 1),
                  ),
            );
        }
      }
    };
    const requestRead = (version?: number) => {
      if (disposed) return;
      const current = streamSnapshot.current;
      if (current === false) return;
      if (version !== undefined && current && version <= current.sequence)
        return;
      if (version === undefined) forceRead = true;
      else wantedVersion = Math.max(wantedVersion, version);
      clearTimeout(timer);
      if (!inFlight) void poll();
    };
    wake.current = requestRead;
    void poll();
    const online = () => refresh();
    window.addEventListener("online", online);
    return () => {
      disposed = true;
      if (wake.current === requestRead) wake.current = null;
      controller.abort();
      clearTimeout(timer);
      window.removeEventListener("online", online);
    };
  }, [runId, refresh]);
  useEffect(() => {
    const lost = () => {
      pollEpoch.current++;
      changeRun(null, false);
    };
    window.addEventListener(AUTH_LOST, lost);
    return () => window.removeEventListener(AUTH_LOST, lost);
  }, [changeRun]);
  useEffect(() => {
    if (!runId || !validId(runId)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let wanted = -1,
      force = false;
    const changed = (version?: number) => {
      const current = streamSnapshot.current;
      if (current === false) return;
      if (version !== undefined && current && version <= current.sequence)
        return;
      if (version === undefined) force = true;
      else wanted = Math.max(wanted, version);
      if (timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        const current = streamSnapshot.current;
        if (force || !current || wanted > current.sequence)
          wake.current?.(force ? undefined : wanted);
        force = false;
        wanted = -1;
      }, 1000);
    };
    void watchRun(
      runId,
      controller.signal,
      changed,
      () => streamSnapshot.current,
      (notify) => {
        snapshotListeners.current.add(notify);
        return () => {
          snapshotListeners.current.delete(notify);
        };
      },
    );
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId]);
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
  const decide = async (choice: Decision, action?: Action) => {
    const selected = action ?? snapshot?.action;
    if (
      decisionLock.current ||
      !snapshot ||
      !selected ||
      snapshot.status !== "waiting_for_approval" ||
      selected.approval_status !== "pending"
    )
      return;
    decisionLock.current = true;
    setDeciding(true);
    setMutationError(null);
    const id = snapshot.run_id;
    try {
      await api.decide(
        id,
        selected.action_id,
        choice,
        selected.expected_version,
      );
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
