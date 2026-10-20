// Test-only preload: change only the fixture hostname's native DNS result.
import dns from 'node:dns/promises';
import {syncBuiltinESMExports} from 'node:module';
import fs from 'node:fs';
const lookup = dns.lookup;
let failures = 0;
dns.lookup = async (hostname, options) => {
  if (hostname !== 'retry.fixture.test') return lookup(hostname, options);
  const mode = fs.readFileSync('/tmp/network-mode', 'utf8');
  const armed = fs.existsSync('/workspace/retry-marker');
  const shouldFail = armed && !['normal', 'stream'].includes(mode) &&
    (!['recovered', 'paused'].includes(mode) || failures < 2);
  if (shouldFail) failures++;
  fs.appendFileSync('/logs/agent/fixture-dns.jsonl', JSON.stringify({
    at: Date.now(), hostname, failed: shouldFail, failures
  }) + '\n');
  if (shouldFail) throw Object.assign(new Error('fixture DNS failure'), {
    code: 'ENOTFOUND', syscall: 'getaddrinfo', hostname
  });
  return options?.all ? [{address: '127.0.0.1', family: 4}] : {address: '127.0.0.1', family: 4};
};
syncBuiltinESMExports();
