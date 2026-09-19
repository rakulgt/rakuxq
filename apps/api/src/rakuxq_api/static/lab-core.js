export const CLASSIC_FEN = "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w";
export const START_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w";

const pieces = new Set("KABNRCPkabnrcp".split(""));

function decodeCandidate(value) {
  const replaced = String(value || "").replace(/\+/g, " ");
  try {
    return decodeURIComponent(replaced);
  } catch {
    return replaced;
  }
}

export function normalizePublicFen(value) {
  const decoded = decodeCandidate(value).trim();
  const fields = decoded.split(/\s+/);
  if (fields.length !== 2 && fields.length !== 6) {
    throw new Error("FEN 必须包含‘棋子布局 + w/b’，或完整六字段格式");
  }
  const [placement, rawTurn] = fields;
  const turn = rawTurn === "r" ? "w" : rawTurn;
  if (turn !== "w" && turn !== "b") throw new Error("行棋方必须是 w（红方）或 b（黑方）");
  if (fields.length === 6 && (fields[2] !== "-" || fields[3] !== "-")) {
    throw new Error("中国象棋 FEN 的王车易位和吃过路兵字段必须为 -");
  }
  if (fields.length === 6) {
    const halfmove = Number(fields[4]);
    const fullmove = Number(fields[5]);
    if (!Number.isInteger(halfmove) || halfmove < 0 || !Number.isInteger(fullmove) || fullmove < 1) {
      throw new Error("FEN 回合计数必须是有效的非负整数");
    }
  }

  const ranks = placement.split("/");
  if (ranks.length !== 10) throw new Error("中国象棋 FEN 必须正好包含十行");
  let redKings = 0;
  let blackKings = 0;
  ranks.forEach((rank, index) => {
    let width = 0;
    for (const symbol of rank) {
      if (/[1-9]/.test(symbol)) width += Number(symbol);
      else if (pieces.has(symbol)) {
        width += 1;
        redKings += symbol === "K" ? 1 : 0;
        blackKings += symbol === "k" ? 1 : 0;
      } else {
        throw new Error(`第 ${index + 1} 行包含不支持的字符 ${symbol}`);
      }
    }
    if (width !== 9) throw new Error(`第 ${index + 1} 行展开后不是九路`);
  });
  if (redKings !== 1 || blackKings !== 1) throw new Error("局面必须各有一个红帅和黑将");
  return `${placement} ${turn}`;
}

export function toEngineFen(value) {
  const [placement, turn] = normalizePublicFen(value).split(" ");
  return `${placement} ${turn === "w" ? "r" : "b"} - - 0 1`;
}

export function toPublicFen(value) {
  const fields = String(value || "").trim().split(/\s+/);
  if (fields.length < 2) throw new Error("无法从引擎局面生成公开 FEN");
  const turn = fields[1] === "r" ? "w" : fields[1];
  return normalizePublicFen(`${fields[0]} ${turn}`);
}

export function canonicalFenPath(value) {
  const [placement, turn] = normalizePublicFen(value).split(" ");
  return `/fen/${placement}%20${turn}`;
}

export function fenFromLocation(locationLike) {
  const pathname = locationLike.pathname || "/";
  if (pathname.startsWith("/fen/")) {
    return normalizePublicFen(pathname.slice("/fen/".length));
  }
  const search = new URLSearchParams(locationLike.search || "");
  if (search.has("fen")) return normalizePublicFen(search.get("fen"));
  const hash = locationLike.hash || "";
  if (hash.startsWith("#/")) return normalizePublicFen(hash.slice(2));
  return null;
}

export function createGameTree(initialFen) {
  const fen = normalizePublicFen(initialFen);
  return {
    format: "rakuxq-game",
    version: 1,
    initial_fen: fen,
    current_node_id: "root",
    nodes: {
      root: {
        id: "root",
        parent_id: null,
        move: null,
        fen,
        children: [],
        preferred_child_id: null,
        analysis: null,
      },
    },
  };
}

export function currentLine(tree, nodeId = tree.current_node_id) {
  const line = [];
  let node = tree.nodes[nodeId];
  const visited = new Set();
  while (node) {
    if (visited.has(node.id)) throw new Error("棋谱变化树存在循环");
    visited.add(node.id);
    line.push(node);
    node = node.parent_id ? tree.nodes[node.parent_id] : null;
  }
  return line.reverse();
}

export function addTreeMove(tree, parentId, move, fen, idFactory = null) {
  const parent = tree.nodes[parentId];
  if (!parent) throw new Error("找不到变化分支的父节点");
  const iccs = move.iccs || `${move.from}${move.to}`;
  const existing = parent.children
    .map((id) => tree.nodes[id])
    .find((node) => node && node.move && node.move.iccs === iccs);
  if (existing) {
    parent.preferred_child_id = existing.id;
    tree.current_node_id = existing.id;
    return existing;
  }
  const makeId = idFactory || (() => `n${Object.keys(tree.nodes).length}`);
  const id = makeId();
  const node = {
    id,
    parent_id: parentId,
    move: {
      iccs,
      from: move.from,
      to: move.to,
      color: move.color,
      piece: move.piece,
      captured: move.captured || null,
    },
    fen: normalizePublicFen(fen),
    children: [],
    preferred_child_id: null,
    analysis: null,
  };
  tree.nodes[id] = node;
  parent.children.push(id);
  parent.preferred_child_id = id;
  tree.current_node_id = id;
  return node;
}

export function validateImportedTree(candidate) {
  if (!candidate || candidate.format !== "rakuxq-game" || candidate.version !== 1) {
    throw new Error("这不是受支持的 RakuXQ JSON 棋谱");
  }
  if (!candidate.nodes || typeof candidate.nodes !== "object" || !candidate.nodes.root) {
    throw new Error("RakuXQ JSON 缺少根局面");
  }
  if (Object.keys(candidate.nodes).length > 2000) throw new Error("棋谱节点超过 2000 个上限");
  normalizePublicFen(candidate.initial_fen);
  Object.values(candidate.nodes).forEach((node) => {
    normalizePublicFen(node.fen);
    if (!Array.isArray(node.children)) throw new Error("棋谱节点的分支字段无效");
    if (node.parent_id && !candidate.nodes[node.parent_id]) throw new Error("棋谱包含断裂分支");
  });
  if (!candidate.nodes[candidate.current_node_id]) throw new Error("棋谱当前节点无效");
  currentLine(candidate);
  return candidate;
}
