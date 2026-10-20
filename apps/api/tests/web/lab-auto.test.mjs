import test from "node:test";
import assert from "node:assert/strict";

import { engineTurnAction, recommendationSummary, terminalOutcome } from "../../src/rakuxq_api/static/lab-auto.js";

const ready = {
  engineAvailable: true,
  editorActive: false,
  terminal: false,
};

test("recommendations are sibling choices and retain legacy/terminal fallbacks", () => {
  assert.equal(recommendationSummary(), "无合法着法");
  assert.equal(recommendationSummary({ best_move: { notation: "炮二平五" } }), "炮二平五");
  const analysis = {
    best_move: { iccs: "h2e2" },
    recommendations: [{ move: { notation: "炮二平五" } }, { move: { notation: "炮八平五" } }],
  };
  assert.equal(recommendationSummary(analysis), "首选：炮二平五；备选：炮八平五");
  assert.equal(analysis.best_move.iccs, "h2e2", "automatic play still executes the primary only");
});

test("single-side engine waits on the human turn and moves on its own turn", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "off" }), "none");
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
});

test("two enabled sides keep requesting sequential engine moves", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
});

test("terminal positions never request another move", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto", terminal: true }), "none");
  assert.equal(terminalOutcome({ turn: "r", checkmate: true }), "黑方胜（将死）");
  assert.equal(terminalOutcome({ turn: "b", stalemate: true }), "红方胜（困毙）");
  assert.equal(terminalOutcome({ turn: "r", draw: true }), "和棋");
});
