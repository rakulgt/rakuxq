export function engineTurnAction({
  assistMode = "off",
  engineAvailable = false,
  editorActive = false,
  terminal = false,
  authenticationRequired = false,
  hasCredentials = false,
} = {}) {
  if (!engineAvailable || editorActive || terminal || assistMode === "off") return "none";
  if (authenticationRequired && !hasCredentials) return "credentials";
  return assistMode === "auto" ? "analyze-and-move" : "analyze";
}

export function terminalOutcome({ turn, checkmate = false, stalemate = false, draw = false } = {}) {
  const winner = turn === "r" ? "黑方" : "红方";
  if (checkmate) return `${winner}胜（将死）`;
  if (stalemate) return `${winner}胜（困毙）`;
  if (draw) return "和棋";
  return "";
}
