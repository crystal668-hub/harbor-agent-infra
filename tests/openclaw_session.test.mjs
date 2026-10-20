import assert from "node:assert/strict";
import {test} from "node:test";
import {setImmediate} from "node:timers/promises";
import {SessionRun} from "../adapters/openclaw/gateway_session.mjs";

const input = {sessionKey: "agent:openclaw:explicit:AbC", sessionId: "AbC", idempotencyKey: "first"};
const finalMessage = {role: "assistant", stopReason: "stop", timestamp: 40,
  content: [{type: "text", text: "FINAL ANSWER: 42"}]};
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
  const {session, client, calls} = fixture({finalAssistantVisibleText: "answer"});
  assert.equal((await session.run(client)).meta.finalAssistantVisibleText, "answer");
  assert.equal(calls.length, 1);
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
