/* One explicit acceptance per recognized browser/version, never inferred from a visit. */
(() => {
  let confirmedUntil = 0;
  let pending = null;
  const cacheWindowMs = 5 * 60 * 1000;

  async function getStatus() {
    const response = await fetch("/api/legal/status", { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error("暂时无法核验协议，请稍后重试；本地打谱仍可使用。");
    return response.json();
  }

  function promptAcceptance(policy) {
    return new Promise((resolve, reject) => {
      const previousFocus = document.activeElement;
      const dialog = document.createElement("dialog");
      dialog.className = "legal-dialog";
      dialog.setAttribute("aria-labelledby", "legal-dialog-title");
      dialog.innerHTML = `<h2 id="legal-dialog-title">提交前，请确认棋局授权</h2>
        <p>您免费、非独占地授权 RakuXQ 将您有权授权的棋局用于模型训练、产品改进及相关商业应用。授权覆盖此后提交，不因停止使用而自动终止；无关个人信息不在训练授权范围。不同意，请勿提交。</p>
        <p>原图最多12小时，训练样本最多3年；合法形成、不含可识别个人信息且不侵权的模型成果可依法持续使用。</p>
        <p><a href="/terms" target="_blank" rel="noopener">完整服务与训练授权协议</a> · <a href="/privacy" target="_blank" rel="noopener">隐私与数据使用</a></p>
        <small>当前未启用训练采集。本地看棋、走棋不需要授权。确认后通常不再逐局询问；版本更新、凭据失效或清除浏览器记录后可能重新确认。</small>
        <label><input type="checkbox" data-agree><span>我已阅读并同意以上两份规则，确认有权提交并授予上述棋局许可。</span></label>
        <p role="alert" data-error hidden></p><div class="legal-dialog-actions"><button type="button" data-cancel>暂不提交</button><button type="button" data-accept disabled>同意并继续</button></div>`;
      const checkbox = dialog.querySelector("[data-agree]");
      const accept = dialog.querySelector("[data-accept]");
      const cancel = dialog.querySelector("[data-cancel]");
      const message = dialog.querySelector("[data-error]");
      let submitting = false;
      function finish(value) {
        dialog.close(); dialog.remove(); previousFocus?.focus?.(); resolve(value);
      }
      checkbox.addEventListener("change", () => { accept.disabled = !checkbox.checked; });
      cancel.addEventListener("click", () => { if (!submitting) finish(false); });
      dialog.addEventListener("cancel", (event) => { event.preventDefault(); if (!submitting) finish(false); });
      accept.addEventListener("click", async () => {
        if (!checkbox.checked || submitting) return;
        submitting = true; accept.disabled = true; cancel.disabled = true;
        try {
          const response = await fetch("/api/legal/acceptances", {
            method: "POST", credentials: "same-origin", cache: "no-store",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ version: policy.version, terms_sha256: policy.terms_sha256,
              privacy_sha256: policy.privacy_sha256, accepted: true, training_license: true }),
          });
          if (!response.ok) throw new Error("确认记录未能保存，请刷新规则后重试；本次尚未发送棋局。");
          const saved = await getStatus();
          if (!saved.accepted) throw new Error("浏览器未保存确认凭据，请允许本站必要 Cookie 后重试。");
          confirmedUntil = Date.now() + cacheWindowMs;
          finish(true);
        } catch (error) {
          message.hidden = false; message.textContent = error.message;
          submitting = false; accept.disabled = !checkbox.checked; cancel.disabled = false;
        }
      });
      document.body.append(dialog);
      if (typeof dialog.showModal !== "function") {
        dialog.remove(); reject(new Error("当前浏览器不支持确认窗口，请更新浏览器；本地打谱不受影响。"));
        return;
      }
      dialog.showModal(); checkbox.focus();
    });
  }

  async function ensure() {
    if (Date.now() < confirmedUntil) return true;
    if (pending) return pending;
    pending = (async () => {
      const policy = await getStatus();
      if (policy.accepted || !policy.acceptance_required) { confirmedUntil = Date.now() + cacheWindowMs; return true; }
      return promptAcceptance(policy);
    })();
    try { return await pending; } finally { pending = null; }
  }
  window.RakuXQLegal = Object.freeze({ ensure });
})();
