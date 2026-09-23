(() => {
  "use strict";

  const CANONICAL_URL = document.querySelector('link[rel="canonical"]')?.href || "https://public-dl.github.io/niigata-infection-radar/";
  const SHARE_TITLE = "新潟インフルエンザレーダー";
  const SHARE_TEXT = "新潟県のインフルエンザ流行状況を、地域・年代・時系列で確認できます。";

  function setStatus(message) {
    const status = document.getElementById("share-status");
    if (!status) return;
    status.textContent = message;
    window.clearTimeout(setStatus.timer);
    setStatus.timer = window.setTimeout(() => {
      status.textContent = "";
    }, 2600);
  }

  function encoded(value) {
    return encodeURIComponent(value);
  }

  function setupShareLinks() {
    const x = document.getElementById("share-x");
    const line = document.getElementById("share-line");
    const facebook = document.getElementById("share-facebook");

    if (x) {
      x.href = `https://twitter.com/intent/tweet?text=${encoded(`${SHARE_TITLE}｜${SHARE_TEXT}`)}&url=${encoded(CANONICAL_URL)}`;
    }
    if (line) {
      line.href = `https://social-plugins.line.me/lineit/share?url=${encoded(CANONICAL_URL)}`;
    }
    if (facebook) {
      facebook.href = `https://www.facebook.com/sharer/sharer.php?u=${encoded(CANONICAL_URL)}`;
    }
  }

  async function copyUrl() {
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(CANONICAL_URL);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = CANONICAL_URL;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const ok = document.execCommand("copy");
        textarea.remove();
        if (!ok) throw new Error("copy failed");
      }
      setStatus("URLをコピーしました");
    } catch (error) {
      setStatus("URLをコピーできませんでした");
    }
  }

  async function nativeShare() {
    if (!navigator.share) return;
    try {
      await navigator.share({
        title: SHARE_TITLE,
        text: SHARE_TEXT,
        url: CANONICAL_URL
      });
    } catch (error) {
      if (error?.name !== "AbortError") {
        setStatus("共有を開始できませんでした");
      }
    }
  }

  function init() {
    setupShareLinks();

    const copyButton = document.getElementById("share-copy");
    if (copyButton) copyButton.addEventListener("click", copyUrl);

    const nativeButton = document.getElementById("share-native");
    if (nativeButton) {
      if (navigator.share) {
        nativeButton.hidden = false;
        nativeButton.addEventListener("click", nativeShare);
      } else {
        nativeButton.hidden = true;
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
