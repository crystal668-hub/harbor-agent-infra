// Run the installed native recovery helper; no duplicated retry implementation.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const source = fs.readFileSync(path.join(process.argv[2], 'dist/openai-transport-stream-DdwLSFjO.js'), 'utf8');
const classifier = source.slice(source.indexOf('function isInvalidEncryptedContentError('),
  source.indexOf('function hashOptionalReplayContextValue('));
const retry = source.slice(source.indexOf('async function createResponsesStreamWithEncryptedContentRetry('),
  source.indexOf('function resolveAzureOpenAIApiVersion('));
const scope = vm.createContext({log: {warn() {}}});
vm.runInContext(classifier + retry, scope);
const observed = () => Object.assign(new Error('400 The encrypted content synthetic could not be verified. Reason: Encrypted content could not be decrypted or parsed.'),
  {status: 400, code: '400', type: 'invalid_params'});
for (const mode of ['normal', 'recovered', 'exhausted', 'no-content', 'schema', 'cancel', 'stream']) {
  const request = {model: 'fixture', reasoning: {effort: 'high'}, input: [
    {type: 'reasoning', encrypted_content: 'synthetic', summary: []},
    {type: 'function_call', call_id: 'call_fixture', name: 'exec', arguments: '{}'},
    {type: 'function_call_output', call_id: 'call_fixture', output: 'preserved'},
  ]};
  if (mode === 'no-content') delete request.input[0].encrypted_content;
  const original = JSON.stringify(request), options = {signal: new AbortController().signal};
  const first = observed(), last = new Error('final failure');
  if (mode === 'schema') first.message = 'invalid schema';
  const controller = new AbortController();
  if (mode === 'cancel') options.signal = controller.signal;
  let attempts = 0, sends = 0;
  const response = {async *[Symbol.asyncIterator]() {throw last;}};
  const pending = scope.createResponsesStreamWithEncryptedContentRetry({
    model: {provider: 'openai', api: 'openai-responses', id: 'fixture'}, request,
    requestOptions: options,
    client: {responses: {create: async (body, receivedOptions) => {
      assert.equal(receivedOptions, options);
      options.signal.throwIfAborted();
      attempts++; sends++;
      if (mode === 'normal' || mode === 'stream') return response;
      if (attempts === 1) {
        assert.equal(body, request);
        if (mode === 'cancel') controller.abort(last);
        throw first;
      }
      const expected = JSON.parse(original);
      delete expected.input[0].encrypted_content;
      assert.equal(JSON.stringify(body), JSON.stringify(expected));
      if (mode === 'exhausted') throw last;
      return response;
    }}},
  });
  if (['normal', 'recovered', 'stream'].includes(mode)) {
    assert.equal(await pending, response);
    if (mode === 'stream') await assert.rejects(async () => {
      for await (const ignored of response) void ignored;
    }, error => error === last);
  } else {
    await assert.rejects(pending, error => error === (['exhausted', 'cancel'].includes(mode) ? last : first));
  }
  assert.equal(sends, ['recovered', 'exhausted'].includes(mode) ? 2 : 1);
  assert.equal(JSON.stringify(request), original);
}
console.log(JSON.stringify({status: 'passed', cases: 7}));
