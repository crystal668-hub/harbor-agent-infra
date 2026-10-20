import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {spawn} from "node:child_process";
import {randomBytes} from "node:crypto";
import {SessionRun} from "./gateway_session.mjs";

const logs = "/logs/agent";
const input = JSON.parse(fs.readFileSync(`${logs}/openclaw-run.json`, "utf8"));
const state = process.env.OPENCLAW_STATE_DIR;
const entry = fs.realpathSync(process.argv[2]);
const {GatewayClient} = await import(pathToFileURL(path.join(path.dirname(entry), "dist/plugin-sdk/gateway-runtime.js")));
const record = (kind, data) => fs.appendFileSync(`${logs}/openclaw-turns.jsonl`, JSON.stringify({kind, at: Date.now(), ...data}) + "\n");
const status = (value) => {
  fs.writeFileSync(`${logs}/openclaw-status.json.tmp`, JSON.stringify(value));
  fs.renameSync(`${logs}/openclaw-status.json.tmp`, `${logs}/openclaw-status.json`);
};
const session = new SessionRun(input, record);
const token = randomBytes(32).toString("hex");
const gatewayLog = fs.openSync(`${logs}/openclaw-gateway.log`, "a");
const gateway = spawn(process.execPath, [entry, "gateway", "run", "--bind", "loopback"], {
  env: {...process.env, OPENCLAW_GATEWAY_TOKEN: token, OPENCLAW_SKIP_CHANNELS: "1"},
  stdio: ["ignore", gatewayLog, gatewayLog], detached: true,
});
fs.writeFileSync(`${logs}/openclaw-driver.pid`, String(process.pid));
status({state: "running", sessionId: input.sessionId});
let client, ready = false, stopping = false, interrupted = false;
let rejectExecution;
const failed = new Promise((_, reject) => { rejectExecution = reject; });
gateway.on("error", rejectExecution);
gateway.on("exit", (code) => { if (!stopping) rejectExecution(new Error(`OpenClaw gateway exited (${code})`)); });
const gatewayExited = new Promise((resolve) => {
  gateway.once("exit", resolve);
  gateway.once("error", resolve);
});

function snapshot() {
  const sessions = path.join(state, "agents", input.agentId, "sessions");
  const source = path.join(sessions, `${input.sessionId}.jsonl`);
  if (fs.existsSync(source)) fs.copyFileSync(source, `${logs}/openclaw.session.jsonl`);
  // Preserve child evidence without copying auth/configuration files.
  if (fs.existsSync(sessions)) {
    const target = `${logs}/openclaw-sessions`;
    fs.mkdirSync(target, {recursive: true});
    for (const name of fs.readdirSync(sessions))
      if (name.endsWith(".jsonl")) fs.copyFileSync(path.join(sessions, name), path.join(target, name));
  }
}
let shutdown;
function stop() {
  if (shutdown) return shutdown;
  stopping = true;
  client?.stop();
  shutdown = (async () => {
    // Finish the snapshot before Harbor downloads logs; bound shutdown even if
    // a child process does not respond to TERM.
    let timer;
    const deadline = new Promise((resolve) => {
      timer = setTimeout(() => {
        try { process.kill(-gateway.pid, "SIGKILL"); } catch {}
        resolve();
      }, 3000);
    });
    try { process.kill(-gateway.pid, "SIGTERM"); } catch {}
    await Promise.race([gatewayExited, deadline]);
    clearTimeout(timer);
    snapshot();
    fs.rmSync(`${logs}/openclaw-driver.pid`, {force: true});
    fs.closeSync(gatewayLog);
  })();
  return shutdown;
}
for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, async () => {
  interrupted = true;
  status({state: "interrupted", paused: session.paused});
  await stop();
  process.exit(130);
});
const startup = setTimeout(() => rejectExecution(new Error("OpenClaw gateway startup timed out")), 60000);
try {
  const connected = new Promise((resolve) => {
    client = new GatewayClient({
      url: "ws://127.0.0.1:18789", token, clientName: "cli", mode: "cli",
      scopes: ["operator.admin", "operator.read", "operator.write"],
      requestTimeoutMs: 2147483647,
      onEvent: (event) => {
        const p = event.payload;
        if (event.event === "agent" && p?.stream === "lifecycle") record("lifecycle", p);
        session.accept(event);
      },
      onHelloOk: () => {
        if (ready) session.reconnect();
        ready = true; clearTimeout(startup); resolve();
      },
    });
    client.start();
  });
  const execute = async () => {
    await connected;
    const result = await session.run(client);
    if (interrupted) return;
    snapshot();
    // The transcript is cumulative across resumed turns; account for it once.
    const transcript = `${logs}/openclaw.session.jsonl`;
    if (fs.existsSync(transcript)) {
      const usage = {input: 0, output: 0, cacheRead: 0, cacheWrite: 0};
      for (const line of fs.readFileSync(transcript, "utf8").trim().split("\n")) {
        const message = JSON.parse(line).message;
        if (message?.role === "assistant")
          for (const key of Object.keys(usage)) usage[key] += message.usage?.[key] ?? 0;
      }
      result.meta.agentMeta.usage = usage;
      delete result.meta.agentMeta.lastCallUsage;
    }
    fs.writeFileSync(`${logs}/openclaw.txt`, JSON.stringify(result, null, 2) + "\n");
    status({state: "completed", sessionId: input.sessionId, paused: session.paused});
  };
  await Promise.race([execute(), failed]);
} catch (error) {
  // stop() rejects pending SDK requests; preserve the initiating cancellation.
  if (!interrupted) status({state: "failed", paused: session.paused, error: error.message});
  process.exitCode = interrupted ? 130 : 1;
} finally {
  clearTimeout(startup);
  await stop();
}
