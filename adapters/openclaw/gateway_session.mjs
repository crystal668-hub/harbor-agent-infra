// Keep one Harbor trial attached to OpenClaw's parent session across yielded turns.
// This uses the public GatewayClient SDK shipped with the pinned OpenClaw package.
export const isPaused = (meta) => meta?.yielded === true || meta?.livenessState === "paused";

function terminalFailure(meta) {
  if (meta.error != null) return "meta_error";
  if (meta.aborted !== false) return "aborted";
  if (meta.livenessState !== "working") return "liveness_not_working";
  if (meta.stopReason !== "stop") return "stop_reason_not_stop";
  if (meta.completion?.stopReason !== "stop" || meta.completion?.finishReason !== "stop")
    return "completion_not_stop";
  if (typeof meta.finalAssistantVisibleText !== "string" || !meta.finalAssistantVisibleText.trim())
    return "final_text_missing";
  return null;
}

function requireTerminal(envelope) {
  const failure = terminalFailure(envelope.meta);
  if (failure)
    throw new Error(`OpenClaw parent ended without a valid terminal response: ${failure}`);
  return envelope;
}

export class SessionRun {
  constructor(input, record) {
    this.input = input;
    this.record = record;
    this.events = [];
    this.seen = new Set();
    this.paused = false;
    this.lastEndedAt = 0;
    this.started = new Map();
    this.initialPending = true;
    this.cronRuns = new Map();
    this.handled = new Set();
  }

  acceptCron(p) {
    const target = p?.job?.sessionTarget;
    const key = p?.sessionKey ?? p?.job?.sessionKey ??
      (target?.startsWith("session:") ? target.slice(8) : null);
    if (key?.toLowerCase() !== this.input.sessionKey.toLowerCase()) return;
    if (p.sessionId && p.sessionId !== this.input.sessionId) {
      this.events.push({failure: "OpenClaw parent session changed during execution"});
    } else if (["started", "finished"].includes(p.action) && Number.isFinite(p.runAtMs)) {
      const id = `${p.jobId}:${p.runAtMs}`;
      const cron = this.cronRuns.get(id) ?? {id, startedAt: p.runAtMs};
      this.cronRuns.set(id, cron);
      this.record("cron", p);
      if (p.action === "finished" && !cron.finished) {
        cron.finished = p;
        if (p.status !== "ok") this.events.push({cronFailure: cron});
        else if (cron.terminal) this.events.push(cron.terminal);
      }
    }
    this.wake?.();
  }

  accept(event) {
    const p = event.payload;
    if (event.event === "cron") return this.acceptCron(p);
    if (event.event !== "agent" || p?.sessionKey?.toLowerCase() !== this.input.sessionKey.toLowerCase() ||
        p.stream !== "lifecycle") return;
    // A reset/rebound session must never supply this trial's final answer.
    if (p.sessionId && p.sessionId !== this.input.sessionId) {
      this.events.push({failure: "OpenClaw parent session changed during execution"});
    } else if (p.data.phase === "start") {
      const starts = this.started.get(p.runId) ?? [];
      const at = p.data.startedAt ?? p.ts;
      if (!starts.some((s) => s.at === at)) starts.push({at,
        initial: this.initialPending && p.runId === this.input.idempotencyKey && !starts.length});
      this.started.set(p.runId, starts);
    } else if (["end", "error"].includes(p.data.phase)) {
      const endedAt = p.data.endedAt ?? p.ts;
      const start = (this.started.get(p.runId) ?? []).filter((s) => s.at <= endedAt &&
        (p.data.startedAt == null || s.at === p.data.startedAt)).sort((a, b) => b.at - a.at)[0];
      const startedAt = p.data.startedAt ?? start?.at;
      const round = `${p.runId}:${startedAt ?? endedAt}`;
      if (this.seen.has(round)) return;
      this.seen.add(round);
      const activeCron = [...this.cronRuns.values()].filter((c) => c.startedAt <=
        (startedAt ?? endedAt) && (!c.finished || endedAt <= c.finished.runAtMs + c.finished.durationMs));
      const cron = activeCron.length === 1 ? activeCron[0] : undefined;
      const terminal = {...p, round, roundStartedAt: startedAt, roundEndedAt: endedAt,
        initial: start?.initial ?? (this.initialPending && p.runId === this.input.idempotencyKey), cron};
      if (cron) cron.terminal = terminal;
      this.events.push(terminal);
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
    this.initialPending = false;
    let envelope = initial.result;
    if (!envelope?.meta) throw new Error("OpenClaw initial run did not return a result");
    this.record("turn", {runId: initial.runId, result: envelope});
    if (!isPaused(envelope.meta)) return requireTerminal(envelope);
    this.paused = true;
    // Native completion announcements resume the parent; never resubmit the task.
    for (;;) {
      const event = await this.next();
      if (event.failure) throw new Error(event.failure);
      if (event.cronFailure) {
        const result = event.cronFailure.finished;
        if (Number.isFinite(result.nextRunAtMs)) continue; // Native retry owns recovery.
        throw new Error(`OpenClaw cron recovery ${result.status}: ${result.error ?? "unknown"}`);
      }
      if (event.initial) {
        this.lastEndedAt = Math.max(this.lastEndedAt, event.roundEndedAt);
        continue;
      }
      if (event.cron && (!event.cron.finished || event.cron.finished.status !== "ok")) continue;
      if (event.round && this.handled.has(event.round)) continue;
      try {
        let wait;
        if (event.reconcile) {
          // Reconcile cron outcome first: session summaries can retain an old
          // 'done' state even when the resumed cron turn ultimately failed.
          for (const cron of this.cronRuns.values()) {
            if (cron.finished) continue;
            const {entries} = await client.request("cron.runs", {id: cron.id.split(":")[0], limit: 100});
            const result = entries?.find((r) => r.runAtMs === cron.startedAt);
            if (result) this.acceptCron({...result, action: "finished", sessionKey: this.input.sessionKey});
          }
          if ([...this.cronRuns.values()].some((c) => !c.finished || c.finished.status !== "ok"))
            continue;
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
          if (event.data.phase === "error")
            throw new Error(event.data.error ?? "OpenClaw parent recovery failed");
          do {
            wait = await client.request("agent.wait", {runId: event.runId, timeoutMs: 30000});
          } while (wait.status === "timeout"); // Harbor owns the overall deadline.
          this.record("wait", {runId: event.runId, result: wait});
          // The native runId cache can still contain the initial yielded turn.
          // A later lifecycle boundary is authoritative only with explicit metadata.
          if (!(wait.endedAt >= event.roundEndedAt) ||
              (wait.startedAt != null && event.roundStartedAt != null &&
               wait.startedAt !== event.roundStartedAt)) {
            this.record("stale_wait", {runId: event.runId, result: wait,
              startedAt: event.roundStartedAt, endedAt: event.roundEndedAt});
            if (!Number.isFinite(event.roundStartedAt) ||
                (!isPaused(event.data) && (event.data.aborted !== false ||
                 event.data.livenessState !== "working" || event.data.stopReason !== "stop")))
              throw new Error("OpenClaw resumed round cannot be verified against stale run cache");
            wait = {...event.data, status: "ok", startedAt: event.roundStartedAt,
              endedAt: event.roundEndedAt};
          }
          if (isPaused(wait)) {
            this.lastEndedAt = Math.max(this.lastEndedAt, wait.endedAt ?? event.ts);
            continue;
          }
          if (wait.status !== "ok") throw new Error(wait.error ?? `OpenClaw recovery ${wait.status}`);
        }
        const {messages} = await client.request("sessions.get", {key: this.input.sessionKey, limit: 10});
        const last = messages?.at(-1);
        this.record("parent_response", {runId: event.runId ?? null, message: last});
        // This is the resumed parent's terminal message, not a child announcement,
        // old assistant text or a tool-call preamble. No benchmark answer heuristic.
        const startedAt = event.roundStartedAt ?? wait.startedAt;
        const endedAt = event.roundEndedAt ?? wait.endedAt;
        if (last?.role !== "assistant" || !(last.timestamp >= startedAt && last.timestamp <= endedAt)) {
          if (event.reconcile) continue;
          throw new Error("OpenClaw resumed parent ended without a terminal response");
        }
        const text = (last.content ?? [])
          .filter((part) => part.type === "text").map((part) => part.text).join("\n");
        envelope = {
          payloads: [{text}],
          meta: {
            ...envelope.meta, yielded: false, livenessState: "working",
            stopReason: last.stopReason,
            completion: {stopReason: last.stopReason, finishReason: last.stopReason},
            aborted: false, error: null, finalAssistantVisibleText: text,
            agentMeta: {...envelope.meta.agentMeta},
          },
        };
        // The initial turn's error/trace/usage must not describe the resumed turn.
        for (const key of ["executionTrace", "toolSummary", "finalAssistantRawText"])
          delete envelope.meta[key];
        envelope = requireTerminal(envelope);
        if (event.round) this.handled.add(event.round);
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
