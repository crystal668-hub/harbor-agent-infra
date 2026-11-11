// Execute the actual pinned dispatcher with fake runners, without starting a Gateway.
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(`${process.argv[2]}/server-cron-CbQL-0jN.js`, "utf8");
const start = source.indexOf("async function executeJobCore(state, job, abortSignal, options) {");
const end = source.indexOf("\nasync function executeMainSessionCronJob", start);
assert.ok(start > 0 && end > start);
const calls = [];
const execute = new Function("resolveAgentIdFromSessionKey", "executeDetachedCronJob",
  "executeMainSessionCronJob", "abortErrorMessage", source.slice(start, end) + ";return executeJobCore;")(
    key => key.split(":")[1],
    async (...args) => {calls.push(args); return {status: "ok", runner: "agent"};},
    async () => ({status: "ok", runner: "heartbeat"}),
    () => "cancelled",
  );
process.env.OPENCLAW_AGENT_ID = "openclaw";
process.env.OPENCLAW_SESSION_KEY = "agent:openclaw:explicit:fixture";
const job = {sessionTarget: "main", sessionKey: process.env.OPENCLAW_SESSION_KEY,
  payload: {kind: "systemEvent", text: "ORIGINAL_REMINDER"}};
const signal = new AbortController().signal;
const options = {onExecutionPhase: () => {}};
assert.equal((await execute({}, job, signal, options)).runner, "agent");
assert.equal(calls.length, 1);
assert.equal(calls[0][1].sessionTarget, "session:" + job.sessionKey);
assert.deepEqual(calls[0][1].payload, {kind: "agentTurn", message: "ORIGINAL_REMINDER"});
assert.equal(calls[0][2], signal);
assert.equal(calls[0][4], options);
assert.equal(job.payload.kind, "systemEvent");
assert.equal((await execute({}, {...job, sessionKey: "agent:openclaw:other"}, signal)).runner,
  "heartbeat");
const aborted = new AbortController();
aborted.abort();
assert.deepEqual(await execute({}, job, aborted.signal), {status: "error", error: "cancelled"});
assert.equal(calls.length, 1);
console.log("native explicit-parent cron dispatch contract passed");
