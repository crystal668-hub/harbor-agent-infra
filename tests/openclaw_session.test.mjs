import assert from "node:assert/strict";
import {test} from "node:test";
import {setImmediate} from "node:timers/promises";
import {SessionRun} from "../adapters/openclaw/gateway_session.mjs";

const input = {sessionKey: "agent:openclaw:explicit:AbC", sessionId: "AbC", idempotencyKey: "first"};
const finalMessage = {role: "assistant", stopReason: "stop", timestamp: 40,
  content: [{type: "text", text: "FINAL ANSWER: 42"}]};
const finalMeta = {aborted: false, completion: {stopReason: "stop", finishReason: "stop"},
  error: null, finalAssistantVisibleText: "FINAL ANSWER: 42", livenessState: "working",
  stopReason: "stop"};
function event(runId, phase, extra = {}) {
  return {event: "agent", payload: {runId, stream: "lifecycle", sessionId: input.sessionId,
    sessionKey: input.sessionKey.toLowerCase(), ts: 20,
    data: {phase, startedAt: 20, endedAt: 50}, ...extra}};
}
function fixture(meta, payloads = []) {
  const calls = [], evidence = [];
  const session = new SessionRun(input, (kind, data) => evidence.push({kind, ...data}));
  const client = {request: async (method, params) => {
    calls.push({method, params});
    if (method === "agent") return {runId: "first", result: {payloads, meta: {...meta, agentMeta: {sessionId: "AbC"}}}};
    if (method === "agent.wait") return {status: "ok", startedAt: 20, endedAt: 50};
    if (method === "sessions.get") return {messages: [finalMessage]};
    if (method === "sessions.describe") return {session: {sessionId: "AbC", status: "done", startedAt: 20, endedAt: 50}};
    throw new Error(method);
  }};
  return {session, client, calls, evidence};
}

for (const meta of [{yielded: true}, {livenessState: "paused"}, {yielded: true, livenessState: "paused"}]) {
  test(`wait for parent continuation: ${JSON.stringify(meta)}`, async () => {
    const {session, client, calls} = fixture(meta, meta.livenessState
      ? [{text: "tool warning while paused", isError: true}] : []);
    let finished = false;
    const pending = session.run(client).then((result) => {finished = true; return result;});
    await setImmediate();
    session.accept(event("child", "end", {sessionKey: "agent:openclaw:subagent:child"}));
    await setImmediate();
    assert.equal(finished, false);
    session.accept(event("resume", "start"));
    session.accept(event("resume", "end"));
    session.accept(event("resume", "end")); // Duplicate delivery cannot start another turn.
    const result = await pending;
    assert.equal(result.meta.finalAssistantVisibleText, "FINAL ANSWER: 42");
    assert.equal(calls.filter((c) => c.method === "agent").length, 1);
    assert.equal(calls.filter((c) => c.method === "agent.wait").length, 1);
  });
}
test("multiple paused turns remain pending until the final parent turn", async () => {
  const {session, client, evidence} = fixture({yielded: true});
  const original = client.request;
  client.request = async (method, p) => method === "agent.wait" && p.runId === "again"
    ? {status: "ok", yielded: true, endedAt: 25} : original(method, p);
  const pending = session.run(client);
  session.accept(event("again", "end"));
  await setImmediate();
  assert.equal(evidence.filter((e) => e.kind === "completed").length, 0);
  session.accept(event("last", "end"));
  assert.equal((await pending).payloads[0].text, "FINAL ANSWER: 42");
});
test("reconnect reconciles a missed completion without another model request", async () => {
  const {session, client, calls} = fixture({yielded: true});
  const pending = session.run(client);
  await setImmediate();
  session.reconnect();
  assert.equal((await pending).payloads[0].text, "FINAL ANSWER: 42");
  assert.equal(calls.filter((c) => c.method === "agent").length, 1);
});
test("stale paused-turn text is not a recovered answer", async () => {
  const {session, client} = fixture({yielded: true});
  const original = client.request;
  let recovered = false;
  client.request = async (method, p) => method === "sessions.get" && !recovered
    ? {messages: [{...finalMessage, timestamp: 1, stopReason: "toolUse"}]} : original(method, p);
  let finished = false;
  const pending = session.run(client).then((r) => {finished = true; return r;});
  session.reconnect();
  await setImmediate();
  assert.equal(finished, false);
  recovered = true;
  session.accept(event("resume", "end"));
  await pending;
});
test("normal final result bypasses the continuation wait", async () => {
  const {session, client, calls} = fixture(finalMeta, [{text: "FINAL ANSWER: 42"}]);
  assert.equal((await session.run(client)).meta.finalAssistantVisibleText, "FINAL ANSWER: 42");
  assert.equal(calls.length, 1);
});
for (const [caseName, reason, meta] of [
  ["meta error", "meta_error", {...finalMeta, error: {kind: "incomplete_turn"}}],
  ["aborted", "aborted", {...finalMeta, aborted: true}],
  ["non-working liveness", "liveness_not_working", {...finalMeta, livenessState: "abandoned"}],
  ["length stop reason", "stop_reason_not_stop", {...finalMeta, stopReason: "length",
    completion: {stopReason: "length", finishReason: "length"}}],
  ["length completion", "completion_not_stop",
    {...finalMeta, completion: {stopReason: "stop", finishReason: "length"}}],
  ["missing completion", "completion_not_stop", {...finalMeta, completion: undefined}],
  ["missing final text", "final_text_missing", {...finalMeta, finalAssistantVisibleText: ""}],
]) test(`invalid initial terminal fails: ${caseName}`, async () => {
  const {session, client} = fixture(meta, [{text: "intermediate output"}]);
  await assert.rejects(session.run(client), new RegExp(`valid terminal response: ${reason}$`));
});
test("a lifecycle length signal does not preempt the pending Gateway result", async () => {
  const session = new SessionRun(input, () => {});
  let resolve;
  const client = {request: (method) => {
    assert.equal(method, "agent");
    return new Promise((done) => {resolve = done;});
  }};
  let finished = false;
  const pending = session.run(client).then((result) => {finished = true; return result;});
  await setImmediate();
  session.accept(event("first", "finishing", {data: {phase: "finishing", stopReason: "length"}}));
  await setImmediate();
  assert.equal(finished, false);
  resolve({runId: "first", result: {payloads: [{text: "FINAL ANSWER: 42"}],
    meta: {...finalMeta, agentMeta: {sessionId: "AbC"}}}});
  assert.equal((await pending).meta.stopReason, "stop");
});
test("resumed final result is normalized to the terminal contract", async () => {
  const {session, client} = fixture({yielded: true});
  const pending = session.run(client);
  session.accept(event("resume", "end"));
  const result = await pending;
  assert.deepEqual(result.meta.completion, {stopReason: "stop", finishReason: "stop"});
  assert.equal(result.meta.aborted, false);
  assert.equal(result.meta.error, null);
  assert.equal(result.meta.livenessState, "working");
  assert.equal(result.meta.finalAssistantVisibleText, "FINAL ANSWER: 42");
});
test("a resumed length result fails instead of completing", async () => {
  const {session, client, evidence} = fixture({yielded: true});
  const original = client.request;
  client.request = async (method, params) => method === "sessions.get"
    ? {messages: [{...finalMessage, stopReason: "length"}]} : original(method, params);
  const pending = session.run(client);
  session.accept(event("resume", "end"));
  await assert.rejects(pending, /valid terminal response: stop_reason_not_stop$/);
  assert.equal(evidence.filter((item) => item.kind === "completed").length, 0);
});
for (const message of [
  "CLI transcript compaction failed for qwen/qwen3.8-max: Already compacted",
  "Cannot continue from message role: assistant",
]) test(`explicit OpenClaw failure remains unchanged: ${message}`, async () => {
  const {session, client} = fixture(finalMeta);
  client.request = async () => {throw new Error(message);};
  await assert.rejects(session.run(client), new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});
test("a rebound parent session fails instead of consuming another answer", async () => {
  const {session, client} = fixture({yielded: true});
  const pending = session.run(client);
  session.accept(event("resume", "end", {sessionId: "different"}));
  await assert.rejects(pending, /session changed/);
});
for (const sawStart of [true, false]) test(`agent.wait may omit startedAt (saw start: ${sawStart})`, async () => {
  const {session, client} = fixture({yielded: true});
  const original = client.request;
  client.request = async (method, p) => method === "agent.wait"
    ? {status: "ok", endedAt: 50} : original(method, p);
  const pending = session.run(client);
  if (sawStart) session.accept(event("resume", "start"));
  session.accept(event("resume", "end"));
  assert.equal((await pending).payloads[0].text, "FINAL ANSWER: 42");
});
for (const interrupted of ["agent.wait", "sessions.get", "sessions.describe"]) {
  test(`disconnect during ${interrupted} reconciles without resubmitting the task`, async () => {
    const {session, client, calls} = fixture({yielded: true});
    const original = client.request;
    let disconnect = true;
    client.request = async (method, p) => {
      if (method === interrupted && disconnect) {
        disconnect = false;
        setImmediate().then(() => session.reconnect());
        throw new Error("gateway closed (1006): connection lost");
      }
      return original(method, p);
    };
    const pending = session.run(client);
    if (interrupted === "sessions.describe") session.reconnect();
    else session.accept(event("resume", "end"));
    assert.equal((await pending).payloads[0].text, "FINAL ANSWER: 42");
    assert.equal(calls.filter((c) => c.method === "agent").length, 1);
  });
}
test("an individual agent.wait timeout does not end the Harbor trial", async () => {
  const {session, client} = fixture({yielded: true});
  const original = client.request;
  let waits = 0;
  client.request = async (method, p) => method === "agent.wait" && ++waits === 1
    ? {status: "timeout"} : original(method, p);
  const pending = session.run(client);
  session.accept(event("resume", "end"));
  assert.equal((await pending).payloads[0].text, "FINAL ANSWER: 42");
  assert.equal(waits, 2);
});
test("a failed parent recovery preserves its error", async () => {
  const {session, client} = fixture({yielded: true});
  const original = client.request;
  client.request = async (method, p) => method === "agent.wait"
    ? {status: "error", error: "parent recovery failed"} : original(method, p);
  const pending = session.run(client);
  session.accept(event("resume", "error"));
  await assert.rejects(pending, /parent recovery failed/);
});
test("reconnect observes a failed parent instead of waiting for a missed error event", async () => {
  const {session, client} = fixture({yielded: true});
  const original = client.request;
  client.request = async (method, p) => method === "sessions.describe"
    ? {session: {sessionId: "AbC", status: "failed", endedAt: 50}} : original(method, p);
  const pending = session.run(client);
  session.reconnect();
  await assert.rejects(pending, /parent recovery failed/);
});
