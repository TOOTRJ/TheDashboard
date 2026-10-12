import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("indexed source maps reject huge and invalid section offsets before mapping work", () => {
  // An independent deadline bounds even a broken dependency; never run the
  // enormous mapping walk that the older package could admit.
  const source = String.raw`
    const assert = require('node:assert/strict');
    const { SourceMapConsumer } = require('source-map-js');
    const basic = { version: 3, sources: ['input.js'], names: [], mappings: 'AAAA' };
    for (const line of [Number.MAX_SAFE_INTEGER, -1, 0.5, '1', Infinity, NaN]) {
      assert.throws(() => new SourceMapConsumer({ version: 3,
        sections: [{ offset: { line, column: 0 }, map: basic }] }));
    }
    const valid = new SourceMapConsumer({ version: 3,
      sections: [{ offset: { line: 2, column: 0 }, map: basic }] });
    const mappings = [];
    valid.eachMapping(item => mappings.push(item));
    assert.equal(mappings.length, 1);
    assert.equal(mappings[0].source, 'input.js');
    assert.equal(mappings[0].generatedLine, 3);
    assert.equal(mappings[0].originalLine, 1);
  `;
  const result = spawnSync(process.execPath, ["-e", source], {
    cwd: process.cwd(), env: {}, encoding: "utf8", timeout: 2_000, maxBuffer: 32 * 1024,
  });
  assert.equal(result.error, undefined, "source-map validation exceeded its independent deadline");
  assert.equal(result.status, 0, result.stderr);
});
