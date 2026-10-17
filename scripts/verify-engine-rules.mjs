// Local/CI verification: compare the Python UCI safety rules with pinned xiangqi.js.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { Xiangqi } = require("xiangqi.js");
const root = fileURLToPath(new URL("../", import.meta.url));
const api = fileURLToPath(new URL("../apps/api/src", import.meta.url));
const positions = [];
let seed = 20261017;
function random(count) {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed % count;
}
function record(game) {
  positions.push({
    fen: game.fen().replace(/ r /, " w "),
    in_check: game.in_check(),
    moves: game.moves().sort(),
    terminal: game.in_checkmate() ? "checkmate" : game.in_stalemate() ? "stalemate" : null,
  });
}
for (const fen of [
  "5k3/9/9/9/9/9/4r4/9/9/4K4 r - - 0 1",
  "4k4/3RR4/9/9/9/9/9/9/9/5K3 b - - 0 1",
  "4k4/3R1R3/9/9/9/9/9/9/9/3K5 b - - 0 1",
  "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 r - - 0 1",
]) record(new Xiangqi(fen));
for (let gameIndex = 0; gameIndex < 12; gameIndex++) {
  const game = new Xiangqi();
  for (let ply = 0; ply < 60; ply++) {
    record(game);
    const moves = game.moves();
    if (!moves.length) break;
    const move = moves[random(moves.length)];
    game.move({ from: move.slice(0, 2), to: move.slice(2, 4) });
  }
}
const result = spawnSync(process.env.RAKUXQ_PYTHON || (process.platform === "win32" ? "python" : "python3"), [
  "-c", `import json,sys
from rakuxq_api.engines.base import normalize_engine_fen
from rakuxq_api.engines.rules import inspect_position
results=[]
for item in json.load(sys.stdin):
    state,moves=inspect_position(normalize_engine_fen(item['fen']))
    results.append({'in_check':state.in_check,'moves':sorted(moves),'terminal':state.terminal_reason})
print(json.dumps(results))`,
], {
  cwd: root,
  env: { ...process.env, PYTHONPATH: api },
  input: JSON.stringify(positions), encoding: "utf8", maxBuffer: 8 * 1024 * 1024,
});
assert.equal(result.status, 0, result.stderr || String(result.error));
const actual = JSON.parse(result.stdout);
assert.equal(actual.length, positions.length);
positions.forEach((expected, index) => {
  assert.deepEqual(actual[index], {
    in_check: expected.in_check, moves: expected.moves, terminal: expected.terminal,
  }, `Python/xiangqi.js mismatch at ${expected.fen}`);
});
console.log(`Matched legal moves, check and terminal state on ${positions.length} positions.`);
