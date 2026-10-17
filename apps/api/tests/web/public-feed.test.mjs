import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

class Element {
  children = [];
  textContent = "";
  addEventListener() {}
  append(...children) { this.children.push(...children); }
}

function renderer() {
  const context = vm.createContext({
    window: { location: { hash: "" } },
    document: { createElement: () => new Element(), getElementById: () => new Element() },
    fetch: () => new Promise(() => {}),
    setInterval() {}, URLSearchParams,
  });
  vm.runInContext(readFileSync(new URL("../../src/rakuxq_api/static/app.js", import.meta.url), "utf8"), context);
  return context.eventRow;
}

const event = {
  occurred_at: "2026-10-17T12:00:00Z", status: "accepted", location: { country: "中国" },
  fen: "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w", confidence: .99, duration_ms: 300,
};

test("public move column follows FEN and uses only the move, never the score or KO text", () => {
  const row = renderer()({
    ...event, recommended_move: "前炮进二", display_text: "前炮进二 红方 KO(2)",
  });
  assert.equal(row.children[3].textContent, event.fen);
  assert.equal(row.children[4].className, "event-recommendation");
  assert.equal(row.children[4].textContent, "前炮进二");
});

test("public move column displays a dash for records without a computed answer", () => {
  const render = renderer();
  for (const recommended_move of [null, undefined, ""]) {
    assert.equal(render({ ...event, recommended_move }).children[4].textContent, "—");
  }
});
