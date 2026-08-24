document.addEventListener("DOMContentLoaded", () => {
  revealStagger();
  animateCounters();
  initFunnelBars();
  initLiveFeed();
});

function revealStagger() {
  document.querySelectorAll(".reveal").forEach((el, i) => {
    el.style.transitionDelay = Math.min(i * 55, 440) + "ms";
    requestAnimationFrame(() =>
      requestAnimationFrame(() => el.classList.add("in"))
    );
  });
}

function animateCounters() {
  document.querySelectorAll("[data-count]").forEach((el) => {
    const target = parseFloat(el.dataset.count || "0");
    if (isNaN(target)) return;
    const dur = 950;
    const start = performance.now();
    const suffix = el.dataset.suffix || "";
    const decimal = !!el.dataset.decimal;
    const fmt = (v) =>
      (decimal ? v.toFixed(1) : Math.round(v).toLocaleString()) + suffix;
    function tick(t) {
      const p = Math.min((t - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
}

function initFunnelBars() {
  document.querySelectorAll(".bar i[data-w], .camp-bar i[data-w]").forEach((el) => {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => { el.style.width = el.dataset.w + "%"; })
    );
  });
}

const AGENT_CLASS = ["hunter","guardian","profiler","copywriter","sdr","networker","pipeline","security","engine","scheduler"];

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

function feedItemHtml(e) {
  const agentCls = AGENT_CLASS.includes(e.agent) ? "a-" + e.agent : "a-scheduler";
  return `<div class="feed-item" data-eid="${escapeHtml(e.id)}">
    <span class="agent-tag ${agentCls}">${escapeHtml(e.agent)}</span>
    <span class="feed-action">${escapeHtml((e.action || "").replace(/_/g, " "))}</span>
    <span class="feed-target">${escapeHtml(e.target || "")}</span>
    <time class="feed-time mono">${escapeHtml(e.ago || "just now")}</time>
  </div>`;
}

function initLiveFeed() {
  const feed = document.querySelector("#feed[data-live]");
  if (!feed) return;
  let known = new Set(
    Array.from(feed.querySelectorAll(".feed-item")).map((el) => el.dataset.eid)
  );
  async function poll() {
    try {
      const res = await fetch("/api/events/recent?limit=18", { cache: "no-store" });
      if (!res.ok) return;
      const events = await res.json();
      for (const e of events.reverse()) {
        if (known.has(String(e.id))) continue;
        known.add(String(e.id));
        feed.insertAdjacentHTML("afterbegin", feedItemHtml(e));
      }
      while (feed.children.length > 40) feed.lastElementChild.remove();
    } catch (_) {}
  }
  setInterval(poll, 6000);
}
