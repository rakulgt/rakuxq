"use strict";

(() => {
  const initialFen = "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w";
  const svgNamespace = "http://www.w3.org/2000/svg";
  const files = "abcdefghi";
  const pieceNames = {
    r: { k: "帅", a: "仕", b: "相", n: "马", r: "车", c: "炮", p: "兵" },
    b: { k: "将", a: "士", b: "象", n: "馬", r: "車", c: "炮", p: "卒" },
  };

  const piecesLayer = document.getElementById("interactive-pieces");
  const highlightsLayer = document.getElementById("board-highlights");
  const hitareasLayer = document.getElementById("board-hitareas");
  const fenOutput = document.getElementById("board-fen");
  const turnOutput = document.getElementById("board-turn");
  const stateOutput = document.getElementById("board-state");
  const messageOutput = document.getElementById("board-message");
  const undoButton = document.getElementById("board-undo");
  const resetButton = document.getElementById("board-reset");
  const copyButton = document.getElementById("board-copy");
  const openLink = document.getElementById("board-open");

  if (!piecesLayer || typeof Xiangqi === "undefined") return;

  let game = new Xiangqi(toEngineFen(initialFen));
  let selectedSquare = null;
  let legalMoves = [];
  let lastMove = null;
  let transientMessage = "系统只允许符合象棋规则的着法";

  function toEngineFen(fen) {
    const [placement, turn = "w"] = fen.trim().split(/\s+/);
    return `${placement} ${turn === "w" ? "r" : "b"} - - 0 1`;
  }

  function toPublicFen(fen) {
    const [placement, turn] = fen.trim().split(/\s+/);
    return `${placement} ${turn === "r" ? "w" : "b"}`;
  }

  function pointForSquare(square) {
    return {
      x: files.indexOf(square[0]) * 100,
      y: (9 - Number(square[1])) * 100,
    };
  }

  function squareForCell(row, file) {
    return `${files[file]}${9 - row}`;
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function pieceDescription(piece, square) {
    if (!piece) return `${square} 空位`;
    const side = piece.color === "r" ? "红" : "黑";
    return `${square} ${side}${pieceNames[piece.color][piece.type]}`;
  }

  function renderPieces() {
    const elements = [];
    game.board().forEach((row, rowIndex) => {
      row.forEach((piece, fileIndex) => {
        if (!piece) return;
        const group = svgElement("g", {
          class: `piece ${piece.color === "r" ? "red" : "black"}`,
          transform: `translate(${fileIndex * 100} ${rowIndex * 100})`,
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
    if (lastMove) {
      [lastMove.from, lastMove.to].forEach((square) => {
        const point = pointForSquare(square);
        elements.push(svgElement("circle", {
          class: "board-last-move",
          cx: String(point.x),
          cy: String(point.y),
          r: "45",
        }));
      });
    }
    if (selectedSquare) {
      const point = pointForSquare(selectedSquare);
      elements.push(svgElement("circle", {
        class: "board-selection",
        cx: String(point.x),
        cy: String(point.y),
        r: "45",
      }));
    }
    legalMoves.forEach((move) => {
      const point = pointForSquare(move.to);
      elements.push(svgElement("circle", {
        class: move.captured ? "board-target capture" : "board-target",
        cx: String(point.x),
        cy: String(point.y),
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
    return `${side}走 · 点击棋子查看合法着法`;
  }

  function renderStatus() {
    const publicFen = toPublicFen(game.fen());
    fenOutput.textContent = publicFen;
    stateOutput.textContent = describeState();
    messageOutput.textContent = transientMessage;
    openLink.href = `/fen/${publicFen.replace(" ", "%20")}`;
    undoButton.disabled = game.history().length === 0;
  }

  function render() {
    renderHighlights();
    renderPieces();
    renderStatus();
  }

  function select(square) {
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
      const move = game.move({ from: selectedSquare, to: square });
      if (move) {
        lastMove = { from: move.from, to: move.to };
        const movedPiece = pieceNames[move.color][move.piece.toLowerCase()];
        transientMessage = `${movedPiece} ${move.from} → ${move.to}${move.captured ? "，完成吃子" : ""}`;
      }
      selectedSquare = null;
      legalMoves = [];
      buildHitareas();
      render();
      return;
    }

    if (piece && piece.color === game.turn()) {
      selectedSquare = square;
      legalMoves = game.moves({ square, verbose: true });
      transientMessage = legalMoves.length
        ? `已选择${pieceNames[piece.color][piece.type]}，绿色标记为合法落点`
        : "这个棋子当前没有合法着法";
    } else {
      selectedSquare = null;
      legalMoves = [];
      transientMessage = piece ? "现在还没轮到这个棋子" : "请先选择当前行棋方的棋子";
    }
    render();
  }

  function buildHitareas() {
    const elements = [];
    for (let row = 0; row < 10; row += 1) {
      for (let file = 0; file < 9; file += 1) {
        const square = squareForCell(row, file);
        const hitarea = svgElement("circle", {
          class: "board-hit",
          cx: String(file * 100),
          cy: String(row * 100),
          r: "46",
          tabindex: "0",
          role: "button",
          "aria-label": pieceDescription(game.get(square), square),
        });
        hitarea.addEventListener("click", () => select(square));
        hitarea.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            select(square);
          }
        });
        elements.push(hitarea);
      }
    }
    hitareasLayer.replaceChildren(...elements);
  }

  async function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const input = document.createElement("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  undoButton.addEventListener("click", () => {
    const move = game.undo();
    if (!move) return;
    selectedSquare = null;
    legalMoves = [];
    lastMove = null;
    transientMessage = `已撤销 ${move.from} → ${move.to}`;
    buildHitareas();
    render();
  });

  resetButton.addEventListener("click", () => {
    game = new Xiangqi(toEngineFen(initialFen));
    selectedSquare = null;
    legalMoves = [];
    lastMove = null;
    transientMessage = "已恢复经典残局的初始局面";
    buildHitareas();
    render();
  });

  copyButton.addEventListener("click", async () => {
    try {
      await copyText(toPublicFen(game.fen()));
      transientMessage = "当前 FEN 已复制";
      copyButton.textContent = "已复制";
      window.setTimeout(() => { copyButton.textContent = "复制 FEN"; }, 1600);
    } catch {
      transientMessage = "复制失败，请手动选择下方 FEN";
    }
    renderStatus();
  });

  buildHitareas();
  render();
})();
