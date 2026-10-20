// Keep one Harbor trial attached to OpenClaw's parent session across yielded turns.
// This uses the public GatewayClient SDK shipped with the pinned OpenClaw package.
export const isPaused = (meta) => meta?.yielded === true || meta?.livenessState === "paused";

export class SessionRun {
  constructor(input, record) {
    this.input = input;
    this.record = record;
    this.events = [];
    this.seen = new Set();
    this.paused = false;
    this.lastEndedAt = 0;
    this.started = new Map();
  }

  accept(event) {
    const p = event.payload;
    if (event.event !== "agent" || p?.sessionKey?.toLowerCase() !== this.input.sessionKey.toLowerCase() ||
        p.stream !== "lifecycle") return;
    // A reset/rebound session must never supply this trial's final answer.
    if (p.sessionId && p.sessionId !== this.input.sessionId) {
      this.events.push({failure: "OpenClaw parent session changed during execution"});
    } else if (p.data.phase === "start") {
      this.started.set(p.runId, p.data.startedAt ?? p.ts);
    } else if (["end", "error"].includes(p.data.phase) && !this.seen.has(p.runId)) {
      this.seen.add(p.runId);
      this.events.push(p);
    }
    this.wake?.();
  }

  reconnect() {
    this.record("reconnected", {});
    this.events.push({reconcile: true});
    this.wake?.();
  }

  async next() {
    while (!this.events.length) await new Promise((resolve) => { this.wake = resolve; });
    return this.events.shift();
  }

  async run(client) {
    const initial = await client.request("agent", this.input, {expectFinal: true});
    let envelope = initial.result;
    if (!envelope?.meta) throw new Error("OpenClaw initial run did not return a result");
    this.record("turn", {runId: initial.runId, result: envelope});
    if (!isPaused(envelope.meta)) return envelope;
    this.paused = true;
    // Native completion announcements resume the parent; never resubmit the task.
    for (;;) {
      const event = await this.next();
      if (event.failure) throw new Error(event.failure);
      if (event.runId === this.input.idempotencyKey) {
        this.lastEndedAt = Math.max(this.lastEndedAt, event.data.endedAt ?? event.ts);
        continue;
      }
      try {
        let wait;
        if (event.reconcile) {
          const {session} = await client.request("sessions.describe", {key: this.input.sessionKey});
          if (!session || session.sessionId !== this.input.sessionId) {
            throw new Error("OpenClaw parent session unavailable after reconnect");
          }
          if (!(session.endedAt > this.lastEndedAt)) continue;
          if (["failed", "killed", "timeout"].includes(session.status))
            throw new Error(`OpenClaw parent recovery ${session.status}`);
          if (session.status !== "done") continue;
          wait = {status: "ok", startedAt: session.startedAt, endedAt: session.endedAt};
        } else {
          do {
            wait = await client.request("agent.wait", {runId: event.runId, timeoutMs: 30000});
          } while (wait.status === "timeout"); // Harbor owns the overall deadline.
          this.record("wait", {runId: event.runId, result: wait});
          if (isPaused(wait)) {
            this.lastEndedAt = Math.max(this.lastEndedAt, wait.endedAt ?? event.ts);
            continue;
          }
          if (wait.status !== "ok") throw new Error(wait.error ?? `OpenClaw recovery ${wait.status}`);
        }
        const {messages} = await client.request("sessions.get", {key: this.input.sessionKey, limit: 10});
        const last = messages?.at(-1);
        this.record("parent_response", {runId: event.runId ?? null, message: last});
        const text = last?.role === "assistant" ? (last.content ?? [])
          .filter((part) => part.type === "text").map((part) => part.text).join("\n") : "";
        // This is the resumed parent's terminal message, not a child announcement,
        // old assistant text or a tool-call preamble. No benchmark answer heuristic.
        const startedAt = wait.startedAt ?? this.started.get(event.runId) ?? event.data?.startedAt;
        if (!text?.trim() || !["stop", "end_turn", "completed"].includes(last.stopReason) ||
            !(last.timestamp >= startedAt)) {
          if (event.reconcile) continue;
          throw new Error("OpenClaw resumed parent ended without a terminal response");
        }
        envelope = {
          payloads: [{text}],
          meta: {
            ...envelope.meta, yielded: false, livenessState: "working",
            stopReason: last.stopReason, finalAssistantVisibleText: text,
            agentMeta: {...envelope.meta.agentMeta},
          },
        };
        // The initial turn's error/trace/usage must not describe the resumed turn.
        for (const key of ["error", "executionTrace", "toolSummary", "completion", "finalAssistantRawText"])
          delete envelope.meta[key];
        this.record("completed", {runId: event.runId ?? null, reconciled: !!event.reconcile, result: wait});
        return envelope;
      } catch (error) {
        // The pinned SDK rejects pending reads on disconnect, then reconnects
        // automatically. Its next hello triggers reconciliation of missed events.
        if (!/^gateway closed \(|^gateway not connected$/.test(error.message)) throw error;
        this.record("disconnected", {error: error.message});
      }
    }
  }
}
