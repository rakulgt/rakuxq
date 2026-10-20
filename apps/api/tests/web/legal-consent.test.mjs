import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const base = new URL("../../src/rakuxq_api/static/", import.meta.url);
const script = readFileSync(new URL("legal-consent.js", base), "utf8");

test("accepted browsers reuse confirmation without another prompt or post", async () => {
  let calls = 0;
  const context = { window: {}, fetch: async () => {
    calls++; return { ok: true, json: async () => ({ accepted: true, acceptance_required: true }) };
  } };
  vm.runInNewContext(script, context);
  assert.equal(await context.window.RakuXQLegal.ensure(), true);
  assert.equal(await context.window.RakuXQLegal.ensure(), true);
  assert.equal(calls, 1);
});
test("self-hosted local study does not acquire official training rights", async () => {
  const context = { window: {}, fetch: async () => ({ ok: true,
    json: async () => ({ accepted: false, acceptance_required: false }) }) };
  vm.runInNewContext(script, context);
  assert.equal(await context.window.RakuXQLegal.ensure(), true);
});
test("confirmation errors do not silently authorize", async () => {
  const context = { window: {}, fetch: async () => ({ ok: false }) };
  vm.runInNewContext(script, context);
  await assert.rejects(context.window.RakuXQLegal.ensure(), /无法核验协议/);
});
test("work surfaces expose legal links and no prechecked consent", () => {
  for (const name of ["index.html", "developers.html", "lab.html"]) {
    const page = readFileSync(new URL(name, base), "utf8");
    assert.match(page, /href="\/terms"/);
    assert.match(page, /href="\/privacy"/);
  }
  assert.match(script, /当前未启用训练采集/);
  assert.match(script, /type="checkbox" data-agree/);
  assert.doesNotMatch(script, /type="checkbox"[^>]+checked/);
  assert.match(script, /if \(!checkbox.checked \|\| submitting\) return/);
  assert.doesNotMatch(script, /localStorage\.setItem/);
  const lab = readFileSync(new URL("lab.js", base), "utf8");
  assert.ok(lab.indexOf("await window.RakuXQLegal.ensure()") < lab.indexOf('fetch("/api/lab/analyses"'));
});
