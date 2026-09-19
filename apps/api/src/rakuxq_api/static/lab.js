import {
  CLASSIC_FEN,
  START_FEN,
  addTreeMove,
  canonicalFenPath,
  createGameTree,
  currentLine,
  fenFromLocation,
  normalizePublicFen,
  toEngineFen,
  toPublicFen,
  validateImportedTree,
} from "/static/lab-core.js?v=0.4.0a1";

const svgNamespace = "http://www.w3.org/2000/svg";
const files = "abcdefghi";
const storageKey = "rakuxq.lab.session.v1";
const pieceNames = {
  r: { k: "帅", a: "仕", b: "相", n: "马", r: "车", c: "炮", p: "兵" },
  b: { k: "将", a: "士", b: "象", n: "馬", r: "車", c: "炮", p: "卒" },
};

const byId = (id) => document.getElementById(id);
const piecesLayer = byId("lab-pieces");
const highlightsLayer = byId("lab-highlights");
const hitareasLayer = byId("lab-hitareas");
const fenOutput = byId("lab-fen");
const turnOutput = byId("lab-turn");
const positionState = byId("lab-position-state");
const feedbackTitle = byId("lab-feedback-title");
const feedbackMessage = byId("lab-feedback-message");
const undoButton = byId("lab-undo");
const redoButton = byId("lab-redo");
const alertBox = byId("lab-alert");

let tree;
let game;
let selectedSquare = null;
let legalMoves = [];
let flipped = false;
let transientMessage = "所有落点都经过规则引擎验证";
let analysisArrow = null;
let analysisController = null;
let analysisGeneration = 0;
let engineAvailable = false;
let autoTimer = null;

function showAlert(message) {
  alertBox.textContent = message;
  alertBox.hidden = !message;
}

function node() {
  return tree.nodes[tree.current_node_id];
}

function makeId() {
  if (globalThis.crypto?.randomUUID) return `n_${globalThis.crypto.randomUUID()}`;
  return `n_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(svgNamespace, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function pointForSquare(square) {
  const file = files.indexOf(square[0]);
  const rank = Number(square[1]);
  return flipped
    ? { x: (8 - file) * 100, y: rank * 100 }
    : { x: file * 100, y: (9 - rank) * 100 };
}

function squareForCell(row, file) {
  if (flipped) return `${files[8 - file]}${row}`;
  return `${files[file]}${9 - row}`;
}

function pieceDescription(piece, square) {
  if (!piece) return `${square} 空位`;
  const side = piece.color === "r" ? "红" : "黑";
  return `${square} ${side}${pieceNames[piece.color][piece.type]}`;
}

function currentFen() {
  return toPublicFen(game.fen());
}

function currentAssistMode() {
  return game.turn() === "r" ? byId("red-assist").value : byId("black-assist").value;
}

function renderPieces() {
  const elements = [];
  game.board().forEach((row, rowIndex) => {
    row.forEach((piece, fileIndex) => {
      if (!piece) return;
      const square = `${files[fileIndex]}${9 - rowIndex}`;
      const point = pointForSquare(square);
      const group = svgElement("g", {
        class: `piece ${piece.color === "r" ? "red" : "black"}`,
        transform: `translate(${point.x} ${point.y})`,
      });
      group.append(svgElement("circle", { r: "40" }), svgElement("circle", { r: "33" }));
      const label = svgElement("text");
      label.textContent = pieceNames[piece.color][piece.type];
      group.append(label);
      elements.push(group);
    });
  });
  piecesLayer.replaceChildren(...elements);
}

function renderHighlights() {
  const elements = [];
  const lastMove = node().move;
  if (lastMove) {
    [lastMove.from, lastMove.to].forEach((square) => {
      const point = pointForSquare(square);
      elements.push(svgElement("circle", { class: "board-last-move", cx: point.x, cy: point.y, r: "45" }));
    });
  }
  if (analysisArrow && currentAssistMode() !== "score") {
    const from = pointForSquare(analysisArrow.slice(0, 2));
    const to = pointForSquare(analysisArrow.slice(2, 4));
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy) || 1;
    const padding = 48;
    elements.push(svgElement("circle", { class: "engine-origin", cx: from.x, cy: from.y, r: "45" }));
    elements.push(svgElement("line", {
      class: "engine-arrow",
      x1: from.x + dx / length * padding,
      y1: from.y + dy / length * padding,
      x2: to.x - dx / length * padding,
      y2: to.y - dy / length * padding,
    }));
  }
  if (selectedSquare) {
    const point = pointForSquare(selectedSquare);
    elements.push(svgElement("circle", { class: "board-selection", cx: point.x, cy: point.y, r: "45" }));
  }
  legalMoves.forEach((move) => {
    const point = pointForSquare(move.to);
    elements.push(svgElement("circle", {
      class: move.captured ? "board-target capture" : "board-target",
      cx: point.x,
      cy: point.y,
      r: move.captured ? "44" : "11",
    }));
  });
  highlightsLayer.replaceChildren(...elements);
}

function describeState() {
  const side = game.turn() === "r" ? "红方" : "黑方";
  turnOutput.textContent = `${side}走`;
  if (game.in_checkmate()) return `${side}被将死`;
  if (game.in_stalemate()) return "无子可走，和棋";
  if (game.in_draw()) return "当前局面为和棋";
  if (game.in_check()) return `${side}被将军`;
  return `${side}行棋`;
}

function renderAnalysis() {
  const analysis = node().analysis;
  if (!analysis) {
    byId("analysis-score").textContent = "—";
    byId("analysis-state").textContent = engineAvailable ? "点击分析，获取当前局面建议" : "当前服务未配置解题引擎";
    byId("analysis-best").textContent = "等待分析";
    byId("analysis-pv").textContent = "主要变化将在这里显示";
    ["depth", "nodes", "time", "engine"].forEach((key) => { byId(`analysis-${key}`).textContent = "—"; });
    analysisArrow = null;
    return;
  }
  byId("analysis-score").textContent = analysis.score?.display || "—";
  byId("analysis-state").textContent = "评分始终采用红方固定视角";
  const mode = currentAssistMode();
  byId("analysis-best").textContent = mode === "score" ? "仅评分模式" : (analysis.best_move?.iccs || "无合法着法");
  byId("analysis-pv").textContent = analysis.pv?.length ? analysis.pv.join("  ") : "引擎未返回主要变化";
  byId("analysis-depth").textContent = analysis.depth ?? "—";
  byId("analysis-nodes").textContent = analysis.nodes == null ? "—" : new Intl.NumberFormat("zh-CN").format(analysis.nodes);
  byId("analysis-time").textContent = `${analysis.time_ms ?? 0} ms`;
  byId("analysis-engine").textContent = analysis.engine?.version || analysis.engine?.name || "已配置引擎";
  analysisArrow = analysis.best_move?.iccs || null;
}

function renderMoves() {
  const line = currentLine(tree).slice(1);
  const list = byId("move-list");
  byId("move-empty").hidden = line.length > 0;
  list.replaceChildren(...line.map((item) => {
    const row = document.createElement("li");
    if (item.id === tree.current_node_id) row.className = "current";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.move.iccs;
    button.addEventListener("click", () => loadNode(item.id));
    const score = document.createElement("small");
    score.textContent = item.analysis?.score?.display || "";
    row.append(button, score);
    return row;
  }));
}

function renderVariations() {
  const container = byId("variation-list");
  const current = node();
  const candidates = current.children.map((id) => tree.nodes[id]).filter(Boolean);
  if (!candidates.length) {
    const empty = document.createElement("p");
    empty.className = "lab-empty";
    empty.textContent = "这个节点还没有后续分支。";
    container.replaceChildren(empty);
    return;
  }
  container.replaceChildren(...candidates.map((child, index) => {
    const item = document.createElement("div");
    item.className = "variation-item";
    const description = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = child.move.iccs;
    const detail = document.createElement("span");
    detail.textContent = `${child.analysis?.score?.display || "未分析"}${child.id === current.preferred_child_id ? " · 当前首选" : ""}`;
    description.append(title, detail);
    const open = document.createElement("button");
    open.type = "button";
    open.textContent = index === 0 ? "继续" : "切换";
    open.addEventListener("click", () => loadNode(child.id));
    item.append(description, open);
    return item;
  }));
}

function buildHitareas() {
  const elements = [];
  for (let row = 0; row < 10; row += 1) {
    for (let file = 0; file < 9; file += 1) {
      const square = squareForCell(row, file);
      const hitarea = svgElement("circle", {
        class: "board-hit",
        cx: file * 100,
        cy: row * 100,
        r: "46",
        tabindex: "0",
        role: "button",
        "aria-label": pieceDescription(game.get(square), square),
      });
      hitarea.addEventListener("click", () => selectSquare(square));
      hitarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectSquare(square);
        }
      });
      elements.push(hitarea);
    }
  }
  hitareasLayer.replaceChildren(...elements);
}

function render() {
  renderAnalysis();
  renderHighlights();
  renderPieces();
  buildHitareas();
  renderMoves();
  renderVariations();
  const fen = currentFen();
  fenOutput.textContent = fen;
  positionState.textContent = describeState();
  feedbackTitle.textContent = selectedSquare ? `已选择 ${selectedSquare}` : "选择棋子开始走棋";
  feedbackMessage.textContent = transientMessage;
  undoButton.disabled = !node().parent_id;
  redoButton.disabled = node().children.length === 0;
  byId("lab-external-link").href = `https://xiangqiai.com/#/${fen.replace(" ", "%20")}`;
}

function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(tree));
    byId("lab-save-state").textContent = "已自动保存在本机";
  } catch {
    byId("lab-save-state").textContent = "浏览器未允许本地保存";
  }
}

function clearPendingAnalysis() {
  analysisGeneration += 1;
  analysisController?.abort();
  analysisController = null;
  if (autoTimer) window.clearTimeout(autoTimer);
  autoTimer = null;
}

function loadNode(id, { analyze = true } = {}) {
  if (!tree.nodes[id]) return;
  clearPendingAnalysis();
  tree.current_node_id = id;
  game = new Xiangqi(toEngineFen(tree.nodes[id].fen));
  selectedSquare = null;
  legalMoves = [];
  analysisArrow = tree.nodes[id].analysis?.best_move?.iccs || null;
  transientMessage = id === "root" ? "已回到初始局面" : `已定位到 ${tree.nodes[id].move.iccs}`;
  persist();
  render();
  if (analyze) maybeAssist();
}

function recordMove(move) {
  const newNode = addTreeMove(tree, tree.current_node_id, move, currentFen(), makeId);
  tree.current_node_id = newNode.id;
  selectedSquare = null;
  legalMoves = [];
  analysisArrow = null;
  transientMessage = `${pieceNames[move.color][move.piece.toLowerCase()]} ${move.from} → ${move.to}${move.captured ? "，完成吃子" : ""}`;
  persist();
  render();
  maybeAssist();
}

function makeMove(from, to) {
  const move = game.move({ from, to });
  if (!move) return false;
  recordMove(move);
  return true;
}

function selectSquare(square) {
  const piece = game.get(square);
  if (selectedSquare === square) {
    selectedSquare = null;
    legalMoves = [];
    transientMessage = "已取消选择";
    render();
    return;
  }
  const selectedMove = legalMoves.find((move) => move.to === square);
  if (selectedSquare && selectedMove) {
    makeMove(selectedSquare, square);
    return;
  }
  if (piece && piece.color === game.turn()) {
    selectedSquare = square;
    legalMoves = game.moves({ square, verbose: true });
    transientMessage = legalMoves.length ? `已选择${pieceNames[piece.color][piece.type]}，绿色标记为合法落点` : "这个棋子当前没有合法着法";
  } else {
    selectedSquare = null;
    legalMoves = [];
    transientMessage = piece ? "现在还没轮到这个棋子" : "请先选择当前行棋方的棋子";
  }
  render();
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(value);
  const input = document.createElement("textarea");
  input.value = value;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

async function flashCopy(button, value, success = "已复制") {
  const original = button.textContent;
  try {
    await copyText(value);
    button.textContent = success;
  } catch {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => { button.textContent = original; }, 1500);
}

function headersForEngine() {
  const headers = { "Content-Type": "application/json", Accept: "application/json" };
  const key = byId("engine-key").value.trim();
  if (key) headers.Authorization = `Bearer ${key}`;
  return headers;
}

function friendlyEngineError(status, payload) {
  const code = payload?.detail?.code;
  if (status === 401 || code === "API_KEY_REQUIRED") return "当前服务需要 API Key；可在设置中仅为本次会话填写。";
  if (status === 403) return "API Key 已过期或不可用。";
  if (status === 503) return "当前服务没有配置可用的解题引擎。";
  return payload?.detail?.message || payload?.detail || `引擎请求失败（HTTP ${status}）`;
}

function updateEngineControls() {
  const button = byId("analysis-run");
  button.disabled = !engineAvailable;
  button.textContent = engineAvailable ? "分析当前局面" : "托管引擎尚未开放";
  ["red-assist", "black-assist", "engine-time", "engine-key"].forEach((id) => {
    byId(id).disabled = !engineAvailable;
  });
}

async function analyzeCurrent({ manual = false } = {}) {
  if (!engineAvailable) {
    transientMessage = "当前服务未配置解题引擎，棋盘研究、导入和导出仍可正常使用。";
    render();
    return;
  }
  if (game.in_checkmate() || game.in_draw() || game.in_stalemate()) return;
  clearPendingAnalysis();
  const generation = analysisGeneration;
  const targetNode = tree.current_node_id;
  const targetFen = currentFen();
  analysisController = new AbortController();
  const button = byId("analysis-run");
  button.disabled = true;
  button.textContent = "正在思考…";
  byId("analysis-state").textContent = `搜索预算 ${byId("engine-time").value} ms`;
  try {
    const response = await fetch("/v1/analyses", {
      method: "POST",
      headers: headersForEngine(),
      body: JSON.stringify({ fen: targetFen, movetime_ms: Number(byId("engine-time").value) }),
      signal: analysisController.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(friendlyEngineError(response.status, payload));
    if (generation !== analysisGeneration || targetNode !== tree.current_node_id || targetFen !== currentFen()) return;
    tree.nodes[targetNode].analysis = payload;
    engineAvailable = true;
    showAlert("");
    transientMessage = manual ? "当前局面分析完成" : "AI 辅导已更新";
    persist();
    render();
    if (currentAssistMode() === "auto" && payload.best_move?.iccs) {
      autoTimer = window.setTimeout(() => {
        if (tree.current_node_id !== targetNode) return;
        const iccs = payload.best_move.iccs;
        makeMove(iccs.slice(0, 2), iccs.slice(2, 4));
      }, 450);
    }
  } catch (error) {
    if (error.name === "AbortError") return;
    transientMessage = error.message;
    showAlert(error.message);
    render();
  } finally {
    if (generation === analysisGeneration) {
      updateEngineControls();
    }
  }
}

function maybeAssist() {
  const mode = currentAssistMode();
  if (engineAvailable && mode !== "off") analyzeCurrent();
}

async function checkEngine() {
  const pill = byId("engine-pill");
  try {
    const response = await fetch("/healthz", { cache: "no-store" });
    const health = await response.json();
    engineAvailable = Boolean(health.engine_ready);
    pill.className = `engine-pill ${engineAvailable ? "ready" : "unavailable"}`;
    pill.textContent = engineAvailable ? "引擎就绪" : "仅棋盘模式";
    if (engineAvailable && health.engine?.version) pill.title = `${health.engine.version} · ${health.engine.network_sha256 || ""}`;
    updateEngineControls();
    renderAnalysis();
  } catch {
    engineAvailable = false;
    pill.className = "engine-pill unavailable";
    pill.textContent = "引擎状态未知";
    updateEngineControls();
    renderAnalysis();
  }
}

function switchTab(name) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function resetTree(fen) {
  clearPendingAnalysis();
  tree = createGameTree(fen);
  game = new Xiangqi(toEngineFen(fen));
  selectedSquare = null;
  legalMoves = [];
  analysisArrow = null;
  persist();
  render();
}

function importIccs(value) {
  const tokens = value.trim().split(/[\s,;]+/).filter(Boolean);
  if (!tokens.length || tokens.some((token) => !/^[a-i][0-9][a-i][0-9]$/i.test(token))) {
    throw new Error("无法识别导入内容；ICCS 示例：e2e4 h9g7");
  }
  tree = createGameTree(START_FEN);
  game = new Xiangqi(toEngineFen(START_FEN));
  for (const raw of tokens) {
    const iccs = raw.toLowerCase();
    const move = game.move({ from: iccs.slice(0, 2), to: iccs.slice(2, 4) });
    if (!move) throw new Error(`着法 ${raw} 在第 ${currentLine(tree).length} 手不合法`);
    addTreeMove(tree, tree.current_node_id, move, currentFen(), makeId);
  }
}

function importValue(value) {
  const raw = value.trim();
  if (!raw) throw new Error("请先粘贴 FEN、ICCS 或 RakuXQ JSON");
  if (raw.startsWith("{")) {
    const candidate = validateImportedTree(JSON.parse(raw));
    tree = structuredClone(candidate);
    game = new Xiangqi(toEngineFen(node().fen));
  } else {
    try {
      const fen = normalizePublicFen(raw);
      tree = createGameTree(fen);
      game = new Xiangqi(toEngineFen(fen));
    } catch (fenError) {
      if (raw.includes("/") || /\s[wb](\s|$)/.test(raw)) throw fenError;
      importIccs(raw);
    }
  }
  selectedSquare = null;
  legalMoves = [];
  analysisArrow = node().analysis?.best_move?.iccs || null;
  transientMessage = "导入完成";
  persist();
  render();
}

function download(name, type, contents) {
  const blob = contents instanceof Blob ? contents : new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function exportJson() {
  const payload = structuredClone(tree);
  payload.exported_at = new Date().toISOString();
  download(`rakuxq-${Date.now()}.json`, "application/json", `${JSON.stringify(payload, null, 2)}\n`);
}

function exportBoardImage() {
  const source = byId("lab-board").cloneNode(true);
  source.setAttribute("width", "930");
  source.setAttribute("height", "1030");
  const style = svgElement("style");
  style.textContent = `.lab-surface{fill:url(#lab-board-surface);stroke:#c58d50;stroke-width:2}.board-lines,.board-star{fill:none;stroke:#3a2415;stroke-width:3}.river-label text{fill:#382113;font-family:KaiTi,serif;font-size:42px;text-anchor:middle;dominant-baseline:middle}.piece circle:first-child{fill:#ead8ad;stroke:currentColor;stroke-width:5}.piece circle:nth-child(2){fill:none;stroke:currentColor;stroke-width:2}.piece text{fill:currentColor;font-family:KaiTi,serif;font-size:49px;font-weight:700;text-anchor:middle;dominant-baseline:central}.piece.black{color:#172434}.piece.red{color:#a92e2b}.board-last-move{fill:#e8bc5740;stroke:#e8bc57;stroke-width:4}.board-hit,.board-target,.board-selection,.engine-arrow,.engine-origin{display:none}`;
  source.querySelector("defs").append(style);
  const markup = new XMLSerializer().serializeToString(source);
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = 930;
    canvas.height = 1030;
    canvas.getContext("2d").drawImage(image, 0, 0);
    canvas.toBlob((blob) => { if (blob) download(`rakuxq-position-${Date.now()}.png`, "image/png", blob); }, "image/png");
    URL.revokeObjectURL(image.src);
  };
  image.src = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml" }));
}

function initializeTree() {
  let directFen = null;
  try {
    directFen = fenFromLocation(window.location);
  } catch (error) {
    showAlert(`地址中的 FEN 无效：${error.message}。已打开经典测试局面。`);
  }
  if (directFen) {
    tree = createGameTree(directFen);
    if (!window.location.pathname.startsWith("/fen/")) history.replaceState(null, "", canonicalFenPath(directFen));
  } else if (window.location.pathname === "/lab" || window.location.pathname === "/lab/") {
    try {
      const saved = localStorage.getItem(storageKey);
      tree = saved ? validateImportedTree(JSON.parse(saved)) : createGameTree(CLASSIC_FEN);
    } catch {
      tree = createGameTree(CLASSIC_FEN);
    }
  } else {
    tree = createGameTree(CLASSIC_FEN);
  }
  try {
    game = new Xiangqi(toEngineFen(node().fen));
  } catch {
    showAlert("规则引擎无法加载该局面，已回退到经典测试局面。");
    tree = createGameTree(CLASSIC_FEN);
    game = new Xiangqi(toEngineFen(CLASSIC_FEN));
  }
}

function bindEvents() {
  document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  undoButton.addEventListener("click", () => {
    if (!node().parent_id) return;
    tree.nodes[node().parent_id].preferred_child_id = node().id;
    loadNode(node().parent_id);
  });
  redoButton.addEventListener("click", () => {
    const target = node().preferred_child_id || node().children[0];
    if (target) loadNode(target);
  });
  byId("moves-root").addEventListener("click", () => loadNode("root"));
  byId("lab-flip").addEventListener("click", () => { flipped = !flipped; transientMessage = flipped ? "已切换为黑方视角" : "已切换为红方视角"; render(); });
  byId("lab-reset").addEventListener("click", () => { resetTree(tree.initial_fen); transientMessage = "已恢复本局初始局面"; render(); });
  byId("lab-copy-fen").addEventListener("click", (event) => flashCopy(event.currentTarget, currentFen()));
  byId("lab-copy-link").addEventListener("click", (event) => flashCopy(event.currentTarget, `${location.origin}${canonicalFenPath(currentFen())}`));
  byId("analysis-run").addEventListener("click", () => analyzeCurrent({ manual: true }));
  ["red-assist", "black-assist", "engine-time"].forEach((id) => byId(id).addEventListener("change", () => { render(); maybeAssist(); }));
  byId("lab-import").addEventListener("click", () => { byId("import-error").hidden = true; byId("import-dialog").showModal(); });
  byId("lab-export").addEventListener("click", () => byId("export-dialog").showModal());
  byId("import-confirm").addEventListener("click", (event) => {
    event.preventDefault();
    try {
      importValue(byId("import-value").value);
      byId("import-dialog").close();
      showAlert("");
    } catch (error) {
      byId("import-error").textContent = error.message;
      byId("import-error").hidden = false;
    }
  });
  byId("export-fen").addEventListener("click", (event) => flashCopy(event.currentTarget, currentFen()));
  byId("export-link").addEventListener("click", (event) => flashCopy(event.currentTarget, `${location.origin}${canonicalFenPath(currentFen())}`));
  byId("export-iccs").addEventListener("click", (event) => flashCopy(event.currentTarget, currentLine(tree).slice(1).map((item) => item.move.iccs).join(" ")));
  byId("export-json").addEventListener("click", exportJson);
  byId("export-image").addEventListener("click", exportBoardImage);
}

  if (typeof Xiangqi === "undefined") {
  showAlert("象棋规则组件加载失败，请刷新页面重试。");
} else {
  initializeTree();
  bindEvents();
  persist();
  render();
  checkEngine();
}
