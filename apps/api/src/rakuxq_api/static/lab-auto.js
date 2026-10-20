export function engineTurnAction({
  assistMode = "off",
  engineAvailable = false,
  editorActive = false,
  terminal = false,
} = {}) {
  if (!engineAvailable || editorActive || terminal || assistMode === "off") return "none";
  return assistMode === "auto" ? "analyze-and-move" : "analyze";
}

export function recommendationSummary(analysis = {}) {
  const recommendations = analysis.recommendations || [];
  return recommendations.length === 2
    ? recommendations.map((item, index) => `${index ? "备选" : "首选"}：${item.move.notation || item.move.iccs}`).join("；")
    : (analysis.best_move?.notation || analysis.best_move?.iccs || "无合法着法");
}

export function terminalOutcome({ turn, checkmate = false, stalemate = false, draw = false } = {}) {
  const winner = turn === "r" ? "黑方" : "红方";
  if (checkmate) return `${winner}胜（将死）`;
  if (stalemate) return `${winner}胜（困毙）`;
  if (draw) return "和棋";
  return "";
}
