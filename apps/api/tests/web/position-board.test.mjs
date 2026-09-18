import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { Xiangqi } = require("xiangqi.js");

const publicFen = "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w";
const engineFen = publicFen.replace(/ w$/, " r - - 0 1");

test("classic homepage FEN loads and exposes legal red moves", () => {
  const game = new Xiangqi(engineFen);

  assert.equal(game.turn(), "r");
  assert.ok(game.moves({ square: "e2" }).includes("e2e4"));
  assert.equal(game.moves({ square: "e5" }).length, 0);
});

test("move, FEN generation, and undo stay consistent", () => {
  const game = new Xiangqi(engineFen);
  const before = game.fen();
  const move = game.move({ from: "e2", to: "e4" });

  assert.equal(move.iccs, "e2e4");
  assert.equal(game.turn(), "b");
  assert.notEqual(game.fen(), before);
  game.undo();
  assert.equal(game.fen(), before);
});

test("public FEN deep link preserves the encoded side separator", () => {
  const url = `https://xiangqiai.com/#/${publicFen.replace(" ", "%20")}`;

  assert.equal(
    url,
    "https://xiangqiai.com/#/3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4%20w",
  );
});
