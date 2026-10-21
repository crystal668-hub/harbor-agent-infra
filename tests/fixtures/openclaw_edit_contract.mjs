// Execute the installed edit implementation, with only its filesystem boundary replaced.
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {X: createEditToolDefinition} = await import(pathToFileURL(
  path.join(process.argv[2], 'dist/sessions-BFCD5uPV.js')));
const cases = [
  {content: 'abc', edits: [{oldText: 'abc', newText: 'abc'}], writes: 0, result: 'abc', message: /text is identical/},
  {content: 'abc', edits: [{oldText: 'ab', newText: 'a'}, {oldText: 'c', newText: 'bc'}],
    writes: 0, result: 'abc', message: /produced identical/},
  {content: 'abc', edits: [{oldText: 'ab', newText: 'AB'}], writes: 1, result: 'ABc'},
  {content: 'abc', edits: [{oldText: 'ab', newText: 'ab'}, {oldText: 'c', newText: 'C'}],
    writes: 1, result: 'abC'},
  {content: 'abc', edits: [{oldText: 'missing', newText: 'x'}], error: /Could not find/},
  {content: 'abc', edits: [{oldText: 'ab', newText: 'x'}, {oldText: 'bc', newText: 'y'}], error: /overlap/},
];
for (const entry of cases) {
  let content = entry.content, writes = 0;
  const tool = createEditToolDefinition('/workspace', {operations: {
    access: async () => {}, readFile: async () => Buffer.from(content),
    writeFile: async (_path, text) => { writes++; content = text; },
  }});
  const execute = () => tool.execute('fixture', {path: 'fixture.txt', edits: entry.edits});
  if (entry.error) {
    await assert.rejects(execute, entry.error);
    assert.equal(writes, 0);
    assert.equal(content, entry.content);
  } else {
    const result = await execute();
    assert.notEqual(result.terminate, true);
    assert.equal(content, entry.result);
    assert.equal(writes, entry.writes);
    if (entry.message) assert.match(result.content[0].text, entry.message);
  }
}
console.log(JSON.stringify({status: 'passed', cases: cases.length}));
