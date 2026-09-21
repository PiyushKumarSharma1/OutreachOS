// OutreachOS — Client-side interactions
// Skeuomorphic minimalistic: physical motion, progressive enhancement

(() => {
  'use strict';

  // ---- Config ----
  const REVEAL_THRESHOLD = 0.12;
  const BACK_TO_TOP_THRESHOLD = 300;
  const COUNTER_DURATION = 900;
  const FEED_POLL_INTERVAL = 6000;
  const MAX_FEED_ITEMS = 40;

  // ---- State ----
  let feedKnownIds = new Set();
  let feedPollTimer = null;

  // ---- Utils ----
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
  const fmtNum = (n) => Math.round(n).toLocaleString();
  const fmtPct = (n) => n.toFixed(1) + '%';
  const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&', '<': '<', '>': '>', '"': '"', "'": '''
  }[c]));

  // ---- Easing ----
  const easeOutCubic = t => 1 - Math.pow(1 - t, 3);

  // ---- Loading Screen ----
  function initLoading() {
    const loader = $('#app-loading');
    if (!loader) return;
    const minTime = 500;
    const maxTime = 2200;
    const start = performance.now();
    let hidden = false;
    function hide() {
      if (hidden) return;
      hidden = true;
      loader.classList.add('hidden');
      loader.style.cssText = 'opacity:0!important;visibility:hidden!important;pointer-events:none!important';
    }
    function loop() {
      if (performance.now() - start >= minTime) { hide(); return; }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    setTimeout(hide, maxTime);
    window.addEventListener('load', hide);
    // Also hide on DOMContentLoaded as backup
    document.addEventListener('DOMContentLoaded', hide);
  }

  // ---- Reveal on Scroll (IntersectionObserver) ----
  function initReveal() {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
      $$('.reveal').forEach(el => el.classList.add('visible'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: REVEAL_THRESHOLD, rootMargin: '0px 0px -10% 0px' });

    $$('.reveal').forEach(el => observer.observe(el));
  }

  // ---- Counter Animation ----
  function animateCounters() {
    $$('[data-count]').forEach(el => {
      const target = parseFloat(el.dataset.count || '0');
      if (isNaN(target)) return;
      const suffix = el.dataset.suffix || '';
      const decimal = !!el.dataset.decimal;
      const prefix = el.dataset.prefix || '';
      const startTime = performance.now();

      function tick(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / COUNTER_DURATION, 1);
        const eased = easeOutCubic(progress);
        const value = target * eased;
        const formatted = prefix + (decimal ? value.toFixed(1) : fmtNum(value)) + (el.dataset.suffix || '');
        el.textContent = formatted;
        if (progress < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }

  // ---- Funnel Bars ----
  function initFunnelBars() {
    $$('.funnel-bar > span[data-w], .camp-bar > i[data-w]').forEach(el => {
      // Force reflow then animate
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          el.style.width = el.dataset.w + '%';
        });
      });
    });
  }

  // ---- Back to Top ----
  function initBackToTop() {
    const btn = $('#back-to-top');
    if (!btn) return;

    let ticking = false;
    function onScroll() {
      if (!ticking) {
        requestAnimationFrame(() => {
          const show = window.scrollY > BACK_TO_TOP_THRESHOLD;
          btn.classList.toggle('visible', show);
          ticking = false;
        });
        ticking = true;
      }
    }
    window.addEventListener('scroll', onScroll, { passive: true });

    btn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ---- Live Feed Polling ----
  const AGENT_ICON_CLASS = [
    'hunter','guardian','profiler','copywriter','sdr',
    'networker','pipeline','security','engine','scheduler'
  ];

  function buildFeedItem(e) {
    const agentCls = AGENT_ICON_CLASS.includes(e.agent) ? `feed-icon ${e.agent}` : 'feed-icon';
    return `<div class="feed-item" data-eid="${escapeHtml(e.id)}">
      <div class="${agentCls}"></div>
      <div class="feed-content">
        <span class="feed-agent">${escapeHtml(e.agent)}</span>
        <div class="feed-action">${escapeHtml((e.action || '').replace(/_/g, ' '))}</div>
        <span class="feed-target">${escapeHtml(e.target || '')}</span>
        <time class="feed-time mono">${escapeHtml(e.ago || 'just now')}</time>
      </div>
    </div>`;
  }

  function initLiveFeed() {
    const feed = $('#feed[data-live]');
    if (!feed) return;

    // Seed known IDs
    $$('.feed-item', feed).forEach(el => feedKnownIds.add(el.dataset.eid));

    async function poll() {
      try {
        const res = await fetch('/api/events/recent?limit=18', { cache: 'no-store' });
        if (!res.ok) return;
        const events = await res.json();
        // Newest first in API, prepend in reverse
        for (const e of events.reverse()) {
          if (feedKnownIds.has(String(e.id))) continue;
          feedKnownIds.add(String(e.id));
          feed.insertAdjacentHTML('afterbegin', buildFeedItem(e));
        }
        // Cap
        while (feed.children.length > MAX_FEED_ITEMS) {
          feed.lastElementChild.remove();
        }
      } catch (_) {}
    }
    feedPollTimer = setInterval(poll, FEED_POLL_INTERVAL);
  }

  // ---- Page Transitions (optional, for navigation) ----
  function initPageTransitions() {
    const transition = document.createElement('div');
    transition.className = 'page-transition';
    document.body.appendChild(transition);

    document.addEventListener('click', e => {
      const a = e.target.closest('a[href^="/"]');
      if (!a) return;
      const href = a.getAttribute('href');
      if (!href || href.startsWith('#') || a.target === '_blank' || a.download) return;
      e.preventDefault();
      transition.classList.add('active');
      setTimeout(() => { window.location.href = href; }, 180);
    });
  }

  // ---- Form Enhancements ----
  function initForms() {
    // Auto-submit selects on change (for filters)
    $$('select[data-auto-submit]').forEach(sel => {
      sel.addEventListener('change', () => sel.form?.requestSubmit?.());
    });
    // Focus management
    $$('form').forEach(form => {
      form.addEventListener('submit', () => {
        const btn = form.querySelector('[type="submit"]');
        if (btn && !btn.disabled) {
          btn.disabled = true;
          btn.dataset.originalText = btn.textContent;
          btn.textContent = 'Working…';
        }
      });
    });
  }

  // ---- Keyboard Shortcuts ----
  function initKeyboardShortcuts() {
    document.addEventListener('keydown', e => {
      // Cmd/Ctrl + K -> focus search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const search = $('input[name="q"], input[type="search"]');
        if (search) search.focus();
      }
      // Escape -> close mobile sidebar
      if (e.key === 'Escape') {
        $('.sidebar')?.classList.remove('open');
        $('.sidebar-overlay')?.classList.remove('visible');
      }
    });
  }

  // ---- Mobile Sidebar Toggle ----
  function initMobileSidebar() {
    const toggle = $('#sidebar-toggle');
    const sidebar = $('.sidebar');
    const overlay = $('.sidebar-overlay');
    if (!toggle || !sidebar) return;

    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay?.classList.toggle('visible');
    });
    overlay?.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('visible');
    });
  }

  // ---- Initialize All ----
  function init() {
    initLoading();
    initReveal();
    animateCounters();
    initFunnelBars();
    initBackToTop();
    initLiveFeed();
    // initPageTransitions(); // enable if desired
    initForms();
    initKeyboardShortcuts();
    initMobileSidebar();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for debugging
  window.OutreachOS = {
    animateCounters,
    initFunnelBars,
    feedKnownIds,
    stopFeed: () => clearInterval(feedPollTimer),
  };
})();