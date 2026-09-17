const number = new Intl.NumberFormat("zh-CN");
const dateTime = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function renderChart(hourly) {
  const chart = document.getElementById("activity-chart");
  const counts = new Map(hourly.map((item) => [item.hour, Number(item.interactions)]));
  const now = new Date();
  now.setMinutes(0, 0, 0);
  const values = [];
  for (let offset = 71; offset >= 0; offset -= 1) {
    const time = new Date(now.getTime() - offset * 3600000);
    const key = time.toISOString().slice(0, 13) + ":00:00Z";
    values.push({ time, count: counts.get(key) || 0 });
  }
  const max = Math.max(...values.map((item) => item.count), 1);
  chart.replaceChildren(...values.map((item) => {
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.setProperty("--height", `${Math.max(2, item.count / max * 100)}%`);
    bar.title = `${dateTime.format(item.time)} · ${item.count} 次`;
    return bar;
  }));
}

function renderEvents(events) {
  const feed = document.getElementById("event-feed");
  if (!events.length) {
    feed.innerHTML = '<div class="empty-state">还没有公开交互。第一条记录正在路上。</div>';
    return;
  }
  feed.replaceChildren(...events.map((event) => {
    const row = document.createElement("div");
    row.className = "feed-row";
    const time = document.createElement("time");
    time.dateTime = event.occurred_at;
    time.textContent = dateTime.format(new Date(event.occurred_at));
    const status = document.createElement("span");
    status.className = `status-badge status-${event.status}`;
    status.textContent = event.status === "accepted" ? "自动通过" : "建议复核";
    const code = document.createElement("code");
    const link = document.createElement("a");
    link.href = `https://xiangqiai.com/#/${event.fen.replace(" ", "%20")}`;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = event.fen;
    link.title = "在棋谱查看器中打开";
    code.append(link);
    const confidence = document.createElement("span");
    confidence.className = "confidence";
    confidence.textContent = `${Math.round(event.confidence * 100)}%`;
    const duration = document.createElement("span");
    duration.className = "duration";
    duration.textContent = `${number.format(event.duration_ms)} ms`;
    row.append(time, status, code, confidence, duration);
    return row;
  }));
}

function configureShortcut(url) {
  const button = document.getElementById("shortcut-button");
  if (!url) return;
  button.href = url;
  button.target = "_blank";
  button.rel = "noreferrer";
  button.classList.remove("disabled");
  button.removeAttribute("aria-disabled");
  button.textContent = "获取 Apple 快捷指令 ↗";
  setText("shortcut-note", "下载内容不包含 API Key；每位用户使用自己的有效密钥。");
}

async function refresh() {
  try {
    const response = await fetch("/api/public/stats", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    setText("metric-lifetime", number.format(data.lifetime.successful));
    setText("metric-recent", number.format(data.recent.successful));
    setText("metric-rate", `${data.recent.acceptance_rate}%`);
    setText("metric-latency", `${number.format(data.recent.average_duration_ms)} ms`);
    setText("accepted-count", number.format(data.recent.accepted));
    setText("review-count", number.format(data.recent.review_required));
    setText("donut-rate", `${data.recent.acceptance_rate}%`);
    if (data.lifetime.first_seen_at) setText("metric-since", `始于 ${dateTime.format(new Date(data.lifetime.first_seen_at))}`);
    const donut = document.getElementById("quality-donut");
    donut.style.setProperty("--rate", `${data.recent.acceptance_rate * 3.6}deg`);
    setText("last-updated", `更新于 ${dateTime.format(new Date(data.generated_at))}`);
    renderChart(data.hourly);
    renderEvents(data.events);
    configureShortcut(data.shortcut_url);
  } catch (error) {
    setText("last-updated", "数据暂时不可用");
    console.warn("RakuXQ public metrics unavailable", error);
  }
}

refresh();
setInterval(refresh, 15000);
