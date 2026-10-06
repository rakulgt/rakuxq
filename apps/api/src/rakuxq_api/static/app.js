if (window.location.hash.startsWith("#/")) {
  const encodedFen = window.location.hash.slice(2);
  window.location.replace(`/fen/${encodedFen}`);
}

const number = new Intl.NumberFormat("zh-CN");
const dateTime = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
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

let eventCursor = null;
let loadedEventCount = 0;

function renderChart(daily) {
  const chart = document.getElementById("activity-chart");
  const counts = new Map(daily.map((item) => [item.day, Number(item.interactions)]));
  const now = new Date();
  now.setUTCHours(0, 0, 0, 0);
  const values = [];
  for (let offset = 29; offset >= 0; offset -= 1) {
    const time = new Date(now.getTime() - offset * 86400000);
    const key = time.toISOString().slice(0, 10);
    values.push({ time, count: counts.get(key) || 0 });
  }
  const max = Math.max(...values.map((item) => item.count), 1);
  chart.replaceChildren(...values.map((item) => {
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.setProperty("--height", `${Math.max(2, item.count / max * 100)}%`);
    bar.title = `${item.time.toLocaleDateString("zh-CN")} · ${item.count} 次`;
    return bar;
  }));
}

function locationLabel(location) {
  if (!location) return "未知";
  return location.country || location.country_code || "未知";
}

function eventRow(event) {
  const row = document.createElement("div");
  row.className = "feed-row";
  const time = document.createElement("time");
  time.dateTime = event.occurred_at;
  time.textContent = dateTime.format(new Date(event.occurred_at));
  const status = document.createElement("span");
  status.className = `status-badge status-${event.status}`;
  status.textContent = event.status === "accepted" ? "自动通过" : "建议复核";
  const location = document.createElement("span");
  location.className = "event-location";
  location.textContent = locationLabel(event.location);
  location.title = "IP 数据库推断的近似国家；VPN 或运营商出口可能影响结果";
  const code = document.createElement("code");
  code.textContent = event.fen;
  code.title = event.fen;
  const confidence = document.createElement("span");
  confidence.className = "confidence";
  confidence.textContent = `${Math.round(event.confidence * 100)}%`;
  const duration = document.createElement("span");
  duration.className = "duration";
  duration.textContent = `${number.format(event.duration_ms)} ms`;
  duration.title = "图片到达服务端后的视觉识别耗时；不含上传网络和 NNUE 出招计算";
  const actions = document.createElement("div");
  actions.className = "feed-actions";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "feed-action";
  copy.textContent = "复制 FEN";
  copy.addEventListener("click", async () => {
    try {
      await copyText(event.fen);
      copy.textContent = "已复制";
      window.setTimeout(() => { copy.textContent = "复制 FEN"; }, 1600);
    } catch {
      copy.textContent = "复制失败";
    }
  });
  const open = document.createElement("a");
  open.className = "feed-action";
  open.href = `https://xiangqiai.com/#/${event.fen.replace(" ", "%20")}`;
  open.target = "_blank";
  open.rel = "noreferrer";
  open.textContent = "打开局面 ↗";
  actions.append(copy, open);
  row.append(time, status, location, code, confidence, duration, actions);
  return row;
}

function renderEvents(events, append = false) {
  const feed = document.getElementById("event-feed");
  if (!append && !events.length) {
    feed.innerHTML = '<div class="empty-state">还没有公开交互。第一条记录正在路上。</div>';
    return;
  }
  const rows = events.map(eventRow);
  if (append) feed.append(...rows);
  else feed.replaceChildren(...rows);
}

async function loadEvents(reset = false) {
  const more = document.getElementById("feed-more");
  const status = document.getElementById("feed-page-status");
  more.disabled = true;
  more.textContent = "读取中…";
  try {
    const cursor = reset ? null : eventCursor;
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    const response = await fetch(`/api/public/events?${query}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderEvents(data.events, !reset && loadedEventCount > 0);
    loadedEventCount = reset ? data.events.length : loadedEventCount + data.events.length;
    eventCursor = data.next_cursor;
    status.textContent = `已显示 ${number.format(loadedEventCount)} / ${number.format(data.retained_events)} 条 · 最多保留 ${number.format(data.max_retained_events)} 条`;
    more.disabled = !data.has_more;
    more.textContent = data.has_more ? "加载更早记录" : "已到最早记录";
  } catch (error) {
    status.textContent = "记录读取失败，请稍后重试";
    more.disabled = false;
    more.textContent = "重新加载";
    console.warn("RakuXQ public event stream unavailable", error);
  }
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
    renderChart(data.daily || []);
    configureShortcut(data.shortcut_url);
  } catch (error) {
    setText("last-updated", "数据暂时不可用");
    console.warn("RakuXQ public metrics unavailable", error);
  }
}

document.getElementById("feed-more").addEventListener("click", () => loadEvents(false));
document.getElementById("feed-refresh").addEventListener("click", () => loadEvents(true));

refresh();
loadEvents(true);
setInterval(refresh, 15000);
