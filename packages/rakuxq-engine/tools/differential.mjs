// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Li Guotai
// Artifact-ID: rakuxq.native.differential
// Role: Independent rules-oracle comparison; no third-party engine code enters the core.
// Inputs: candidate executable and pinned BSD xiangqi.js. Outputs: pass/fail test evidence.
// Provenance: Project-authored, AI-assisted. State: experimental verification, not Elo proof.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
const require = createRequire(import.meta.url);
const { Xiangqi } = require("xiangqi.js");
const engine = process.argv[2];
assert.ok(engine, "supply the standalone candidate executable");
let seed = 20261021;
function random(n) { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % n; }
function run(...args) {
  const p = spawnSync(engine, args, {encoding: "utf8", timeout: 10000});
  assert.equal(p.status, 0, p.stderr || String(p.error));
  return p.stdout.trim();
}
let positions = 0;
function compare(game) {
  const fen = game.fen().replace(/ r /, " w ");
  const actual = run("--legal", fen).split(/\s+/).filter(Boolean).sort();
  assert.deepEqual(actual, game.moves().sort(), `rules mismatch: ${fen}`);
  positions++;
}
for (const fen of [
  "5k3/9/9/9/9/9/4r4/9/9/4K4 r - - 0 1",
  "4k4/3RR4/9/9/9/9/9/9/9/5K3 b - - 0 1",
  "4k4/3R1R3/9/9/9/9/9/9/9/3K5 b - - 0 1",
  "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 r - - 0 1",
]) compare(new Xiangqi(fen));
for (let index = 0; index < 16; ++index) {
  const game = new Xiangqi();
  for (let ply = 0; ply < 60; ++ply) {
    compare(game);
    const moves = game.moves();
    if (!moves.length) break;
    const selected = moves[random(moves.length)];
    game.move({from: selected.slice(0,2), to: selected.slice(2,4)});
  }
}
const start = new Xiangqi();
let expected = 0;
for (const move of start.moves()) {
  start.move({from: move.slice(0,2), to: move.slice(2,4)});
  expected += start.moves().length;
  start.undo();
}
assert.equal(Number(run("--perft", "2", start.fen().replace(/ r /, " w "))), expected);
console.log(`Native rules matched pinned BSD oracle on ${positions} positions; perft(2)=${expected}.`);
