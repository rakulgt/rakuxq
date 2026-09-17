const samples = ["curl-code", "python-code", "javascript-code"];
let activeKey = "";
let countdownTimer;

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

function installKey(key) {
  activeKey = key;
  document.getElementById("trial-key").textContent = key;
  document.getElementById("copy-key").disabled = false;
  samples.forEach((id) => {
    const code = document.getElementById(id);
    code.textContent = code.textContent.replaceAll("YOUR_API_KEY", key);
  });
}

function startCountdown(seconds) {
  const display = document.getElementById("trial-countdown");
  let remaining = seconds;
  window.clearInterval(countdownTimer);
  const tick = () => {
    const minutes = Math.floor(remaining / 60);
    const secs = String(remaining % 60).padStart(2, "0");
    display.textContent = remaining > 0 ? `剩余 ${minutes}:${secs}` : "已失效";
    if (remaining <= 0) {
      window.clearInterval(countdownTimer);
      document.getElementById("trial-message").textContent = "临时 Key 已失效。刷新页面后可重新申请。";
    }
    remaining -= 1;
  };
  tick();
  countdownTimer = window.setInterval(tick, 1000);
}

document.getElementById("trial-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const message = document.getElementById("trial-message");
  button.disabled = true;
  button.textContent = "正在生成…";
  try {
    const response = await fetch("/api/public/trial-keys", { method: "POST", cache: "no-store" });
    const data = await response.json();
    if (!response.ok) {
      const retry = data.detail?.retry_after_seconds;
      throw new Error(retry ? `请在 ${retry} 秒后再试。已领取的 Key 不会再次显示。` : "临时 Key 暂时不可用，请稍后再试。");
    }
    installKey(data.api_key);
    startCountdown(data.expires_in_seconds);
    message.textContent = "请立即复制保存；刷新页面后无法再次查看。测试上传遵循 12 小时原图审计规则。";
    button.textContent = "本次已领取";
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
    button.textContent = "重新尝试";
  }
});

document.getElementById("copy-key").addEventListener("click", async (event) => {
  if (!activeKey) return;
  await copyText(activeKey);
  event.currentTarget.textContent = "已复制";
});

document.querySelectorAll(".code-copy").forEach((button) => {
  button.addEventListener("click", async () => {
    await copyText(document.getElementById(button.dataset.copy).textContent);
    button.textContent = "已复制";
    window.setTimeout(() => { button.textContent = "复制"; }, 1600);
  });
});
