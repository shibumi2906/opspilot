import { clearPrivateState } from "./privacy";

export interface StreamSnapshot {
  cursor: string;
  sequence: number;
  generation: number;
}

// Cookies authenticate; a cursor is sent only in a header. No mutations on reconnect.
export async function watchRun(
  id: string,
  signal: AbortSignal,
  changed: (version?: number) => void,
  readSnapshot: () => StreamSnapshot | false | null,
  subscribeSnapshot: (notify: () => void) => () => void,
): Promise<void> {
  let cursor = "";
  let sequence = -1;
  let failures = 0;
  let afterGeneration = -1;
  const path = `/api/v2/runs/${encodeURIComponent(id)}`;
  const pause = (delay = Math.min(10000, 1000 * 2 ** Math.min(failures, 4))) =>
    new Promise<void>((resolve) => {
      const done = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", done);
        resolve();
      };
      const timer = setTimeout(done, delay);
      signal.addEventListener("abort", done, { once: true });
      if (signal.aborted) done();
    });
  while (!signal.aborted) {
    try {
      if (!cursor) {
        const value = readSnapshot();
        if (value === false) return;
        if (!value || value.generation <= afterGeneration) {
          await new Promise<void>((resolve) => {
            const done = () => {
              unsubscribe();
              signal.removeEventListener("abort", done);
              resolve();
            };
            const unsubscribe = subscribeSnapshot(done);
            signal.addEventListener("abort", done, { once: true });
            if (signal.aborted) done();
          });
          continue;
        }
        cursor = value.cursor;
        sequence = value.sequence;
        afterGeneration = value.generation;
      }
      const connection = new AbortController();
      const connectionTimer = setTimeout(() => connection.abort(), 15000);
      const response = await fetch(`${path}/events`, {
        signal: AbortSignal.any([signal, connection.signal]),
        cache: "no-store",
        headers: { "Last-Event-ID": cursor, Accept: "text/event-stream" },
      }).finally(() => clearTimeout(connectionTimer));
      if ([401, 403].includes(response.status)) {
        clearPrivateState();
        return;
      }
      if (response.status === 404) {
        changed();
        return;
      }
      if (response.status === 400) {
        cursor = "";
        const current = readSnapshot();
        afterGeneration = current ? current.generation : -1;
        changed();
      }
      if (!response.ok || !response.body) throw new Error("stream unavailable");
      const reader = response.body.getReader();
      let pending = "";
      const decoder = new TextDecoder();
      let readTimer: ReturnType<typeof setTimeout> | undefined;
      try {
        while (!signal.aborted) {
          const result = await Promise.race([
            reader.read(),
            new Promise<never>((_, reject) => {
              const timer = setTimeout(
                () => reject(new Error("heartbeat timeout")),
                20000,
              );
              // A read completion cancels this timer below through the shared handle.
              readTimer = timer;
            }),
          ]).finally(() => clearTimeout(readTimer));
          if (result.done) break;
          pending += decoder.decode(result.value, { stream: true });
          if (pending.length > 1048576) throw new Error("frame limit");
          let end: number;
          while ((end = pending.indexOf("\n\n")) >= 0) {
            if (end > 16384) throw new Error("frame limit");
            const lines = pending.slice(0, end).split("\n");
            pending = pending.slice(end + 2);
            const kind = lines
              .find((line) => line.startsWith("event: "))
              ?.slice(7);
            if (kind === "access_lost") {
              clearPrivateState();
              return;
            }
            if (kind === "reset") {
              cursor = "";
              const current = readSnapshot();
              afterGeneration = current ? current.generation : -1;
              changed();
              break;
            }
            if (kind === "unavailable") throw new Error("stream unavailable");
            if (kind === "change") {
              const data = JSON.parse(
                lines.find((line) => line.startsWith("data: "))!.slice(6),
              );
              const next = lines
                .find((line) => line.startsWith("id: "))
                ?.slice(4);
              if (!Number.isSafeInteger(data.sequence) || !next)
                throw new Error("invalid event");
              if (data.sequence > sequence) {
                if (data.sequence !== sequence + 1) {
                  cursor = "";
                  const current = readSnapshot();
                  afterGeneration = current ? current.generation : -1;
                  changed();
                  break;
                }
                sequence = data.sequence;
                cursor = next;
                changed(data.sequence);
              }
            }
          }
          if (pending.length > 16384) throw new Error("frame limit");
          failures = 0;
          if (!cursor) break;
        }
      } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
      }
    } catch {
      if (signal.aborted) return;
      failures++;
    }
    await pause();
  }
}
