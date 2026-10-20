import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL("../../src/rakuxq_api/static/", import.meta.url);
const html = readFileSync(new URL("lab.html", root), "utf8");
const js = readFileSync(new URL("lab.js", root), "utf8");

test("Lab defaults to auto/one and exposes explicit two and longer budgets", () => {
  assert.match(html, /id="engine-candidates"><option value="auto" selected>/);
  assert.match(html, /<option value="2">最多 2 招<\/option>/);
  assert.match(html, /<option value="3000" selected>3 秒/);
  assert.match(html, /<option value="9000">9 秒/);
  assert.match(js, /max_candidates: byId\("engine-candidates"\).value/);
  assert.match(js, /"engine-candidates"\]\.forEach/);
  assert.match(js, /clearPendingAnalysis\(\); render\(\); maybeAssist\(\)/);
});
