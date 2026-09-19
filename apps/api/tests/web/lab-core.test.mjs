import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSIC_FEN,
  addTreeMove,
  canonicalFenPath,
  createGameTree,
  currentLine,
  fenFromLocation,
  normalizePublicFen,
  toEngineFen,
  toPublicFen,
  validateImportedTree,
} from "../../src/rakuxq_api/static/lab-core.js";

const example = "2Rak4/4a4/5rn2/p3p3p/6p2/2P6/P3P1c1P/CC4N1B/4A2r1/2B1KA3 w";

test("normalizes simplified and complete Xiangqi FEN", () => {
  assert.equal(normalizePublicFen(example), example);
  assert.equal(normalizePublicFen(`${example} - - 0 1`), example);
  assert.equal(toEngineFen(example), `${example.replace(/ w$/, " r")} - - 0 1`);
  assert.equal(toPublicFen(toEngineFen(example)), example);
});

test("creates a fixed-prefix URL by appending standard FEN", () => {
  assert.equal(
    canonicalFenPath(example),
    "/fen/2Rak4/4a4/5rn2/p3p3p/6p2/2P6/P3P1c1P/CC4N1B/4A2r1/2B1KA3%20w",
  );
});

test("parses canonical, query, and competitor-compatible hash URLs", () => {
  assert.equal(fenFromLocation({ pathname: canonicalFenPath(example), search: "", hash: "" }), example);
  assert.equal(fenFromLocation({ pathname: "/lab", search: `?fen=${encodeURIComponent(example)}`, hash: "" }), example);
  assert.equal(fenFromLocation({ pathname: "/", search: "", hash: `#/${example.replace(" ", "%20")}` }), example);
});

test("rejects malformed board widths and missing kings", () => {
  assert.throws(() => normalizePublicFen("9/9/9/9/9/9/9/9/9/9 w"), /红帅和黑将/);
  assert.throws(() => normalizePublicFen("3aka3/9/9/9/9/9/9/9/9/3K6 w"), /不是九路/);
});

test("keeps alternate continuations in a variation tree", () => {
  const tree = createGameTree(CLASSIC_FEN);
  const first = addTreeMove(
    tree,
    "root",
    { iccs: "e6e8", from: "e6", to: "e8", color: "r", piece: "c" },
    CLASSIC_FEN.replace(/ w$/, " b"),
    () => "first",
  );
  const second = addTreeMove(
    tree,
    "root",
    { iccs: "e6a6", from: "e6", to: "a6", color: "r", piece: "c" },
    CLASSIC_FEN.replace(/ w$/, " b"),
    () => "second",
  );

  assert.equal(first.id, "first");
  assert.equal(second.id, "second");
  assert.deepEqual(tree.nodes.root.children, ["first", "second"]);
  assert.deepEqual(currentLine(tree).map((node) => node.id), ["root", "second"]);
  assert.equal(validateImportedTree(structuredClone(tree)).current_node_id, "second");
});
