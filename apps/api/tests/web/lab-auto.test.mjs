import test from "node:test";
import assert from "node:assert/strict";

import { engineTurnAction, terminalOutcome } from "../../src/rakuxq_api/static/lab-auto.js";

const ready = {
  engineAvailable: true,
  editorActive: false,
  terminal: false,
  authenticationRequired: true,
  hasCredentials: true,
};

test("single-side engine waits on the human turn and moves on its own turn", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "off" }), "none");
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
});

test("two enabled sides keep requesting sequential engine moves", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto" }), "analyze-and-move");
});

test("hosted automatic play asks for credentials before analysis", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto", hasCredentials: false }), "credentials");
});

test("terminal positions never request another move", () => {
  assert.equal(engineTurnAction({ ...ready, assistMode: "auto", terminal: true }), "none");
  assert.equal(terminalOutcome({ turn: "r", checkmate: true }), "黑方胜（将死）");
  assert.equal(terminalOutcome({ turn: "b", stalemate: true }), "红方胜（困毙）");
  assert.equal(terminalOutcome({ turn: "r", draw: true }), "和棋");
});
