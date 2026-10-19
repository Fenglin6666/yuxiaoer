/* 鱼小二 · 托管客服 — 单页控制台
   无构建步骤，原生 JS + fetch；所有用户文本均经过 esc()。 */
(() => {
  'use strict';

  // ---------------- icons ----------------
  const ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.7 8.7 0 0 1-3.5-.7L3 21l1.8-5.5A8.4 8.4 0 1 1 21 11.5Z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',
    wechat: '<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M7 9h10M7 13h6"/>',
    box: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4.4 7.7 7.6 4.4 7.6-4.4M12 12.1V21"/>',
    orders: '<path d="M9 5h11M9 12h11M9 19h11"/><path d="M4 5h.01M4 12h.01M4 19h.01"/>',
    eye: '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6S2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.6"/>',
    activity: '<path d="M3 12h4l2.5-7 5 14 2.5-7H21"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
    bell: '<path d="M18 9a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/>',
    send: '<path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/>',
    spark: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5L5 20"/>',
    play: '<path d="M6 4v16l14-8L6 4Z"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    check: '<path d="m20 6-11 11-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    alert: '<path d="M10.3 3.6 2.5 17a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    external: '<path d="M15 3h6v6M10 14 21 3M21 14v7H3V3h7"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    report: '<path d="M4 4h16v16H4z"/><path d="M8 14v-3M12 14V8M16 14v-5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
    plug: '<path d="M9 3v6M15 3v6M7 9h10v3a5 5 0 0 1-10 0V9ZM12 17v4"/>',
    rotate: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    filter: '<path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/>',
    message: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.7 8.7 0 0 1-3.5-.7L3 21l1.8-5.5A8.4 8.4 0 1 1 21 11.5Z"/>',
    lock: '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  };
  const icon = (name, cls = 'ico') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.grid}</svg>`;

  // ---------------- utils ----------------
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const money = (cents) => `¥${((Number(cents) || 0) / 100).toFixed(2).replace(/\.?0+$/, '')}`;
  const pad = (n) => String(n).padStart(2, '0');
  function fmtTime(v, withDate = false) {
    if (!v) return '—';
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return withDate ? `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}` : `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtDay(v) {
    if (!v) return '—';
    const d = new Date(v);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  function chatDay(v) {
    if (!v) return '今天';
    const d = new Date(v); const now = new Date();
    if (d.toDateString() === now.toDateString()) return '今天';
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return '昨天';
    return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  }
  const nl2br = (text) => linkify(esc(text)).replace(/\n/g, '<br>');
  function linkify(escaped) {
    return escaped.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }
  const initials = (name) => esc((name || '买').slice(0, 1));
  const avatar = (name, cls = '') => `<span class="avatar ${cls}">${initials(name)}</span>`;
  const avatarClass = (name) => `a${((name || '').length % 3) + 1}`;
  const clampPct = (n) => Math.max(0, Math.min(100, Number(n) || 0));

  function toast(message, type = 'ok') {
    const wrap = $('#toastWrap');
    const el = document.createElement('div');
    el.className = `toast ${type === 'error' ? 'error' : type === 'warn' ? 'warn' : ''}`;
    el.innerHTML = `${icon(type === 'error' ? 'alert' : type === 'warn' ? 'alert' : 'check')}<span>${esc(message)}</span>`;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .25s'; setTimeout(() => el.remove(), 260); }, 3600);
  }

  async function api(path, options = {}) {
    const opts = { method: options.method || 'GET', headers: {} };
    if (options.body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(options.body);
    }
    const res = await fetch(`/api${path}`, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && (data.detail || data.error)) || `请求失败 (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }

  // ---------------- state ----------------
  const S = {
    route: 'overview',
    system: null,
    alerts: [],
    handoffCount: 0,
    timers: [],
    inbox: { filter: 'active', convs: [], id: null, detail: null, search: '', busy: false },
    seller: { messages: [], pending: [], busy: false, images: [] },
    catalog: { items: [], sources: [], tab: 'items', results: null },
    orders: { filter: 'all', orders: [] },
    ops: { tab: 'events', metrics: null, events: [], sessions: [], trace: null, sessionId: null, runs: [], lastEval: null, busy: false },
    accounts: { list: [], risk: null, keeper: null, selected: null, events: [], busy: false },
    notify: { channels: [], logs: [], stats: null },
    settings: { data: null },
  };

  const ITEM_STATUS = {
    live: ['在售', 'green'], sold_out: ['已售出', 'amber'], pending_confirm: ['待确认', 'purple'],
    offline: ['已下架', 'gray'], draft: ['草稿', 'gray'],
  };
  const ORDER_STATUS = {
    new: ['新订单', 'gray'], paid: ['待发货', 'amber'], shipped: ['已发货', 'blue'],
    delivered: ['已送达', 'blue'], done: ['已完成', 'green'], refund_open: ['退款中', 'red'],
    refund_resolved: ['退款处理完成', 'purple'], cancelled: ['已取消', 'gray'],
  };
  const CATEGORY_LABEL = { pre_sale: '售前咨询', bargain: '议价', after_sale: '售后/履约', order: '订单查询', chitchat: '寒暄', risk: '风险消息', off_platform: '站外沟通', human: '要求人工', unknown: '未识别' };
  const ACTION_LABEL = { silent: '静默拦截', template: '模板回复', agent: 'Agent 托管' };

  function chip(text, cls = '') { return `<span class="chip ${cls}">${esc(text)}</span>`; }
  function itemStatus(status) { const m = ITEM_STATUS[status] || [status, 'gray']; return chip(m[0], m[1]); }
  function orderStatus(status) { const m = ORDER_STATUS[status] || [status, 'gray']; return chip(m[0], m[1]); }
  function levelChip(level) { return chip(level, level === 'P0' ? 'red' : level === 'P1' ? 'amber' : 'blue'); }

  // ---------------- modal ----------------
  let modalOnClose = null;
  function openModal({ title, body, footer = '', wide = false, onClose = null }) {
    modalOnClose = onClose;
    const root = $('#modalRoot');
    root.innerHTML = `
      <div class="modal-backdrop" id="modalBackdrop">
        <div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <div class="modal-head"><h3>${esc(title)}</h3><button class="close-btn" id="modalClose" aria-label="关闭">${icon('x')}</button></div>
          <div class="modal-body">${body}</div>
          ${footer ? `<div class="modal-foot">${footer}</div>` : ''}
        </div>
      </div>`;
    document.body.classList.add('modal-open');
    $('#modalClose').onclick = closeModal;
    $('#modalBackdrop').onclick = (e) => { if (e.target.id === 'modalBackdrop') closeModal(); };
  }
  function closeModal() {
    const root = $('#modalRoot');
    if (!root.innerHTML) return;
    root.innerHTML = '';
    document.body.classList.remove('modal-open');
    const cb = modalOnClose; modalOnClose = null;
    if (cb) cb();
  }
  function confirmAction({ title = '确认操作', message = '', confirmText = '确认', danger = false }) {
    return new Promise((resolve) => {
      let done = false;
      openModal({
        title,
        body: `<div class="pre" style="font-size:12.5px;color:var(--ink-2);line-height:1.7">${esc(message)}</div>`,
        footer: `<button class="btn ghost" id="cfCancel">取消</button><button class="btn ${danger ? 'danger' : 'primary'}" id="cfOk">${esc(confirmText)}</button>`,
        onClose: () => { if (!done) resolve(false); },
      });
      $('#cfCancel').onclick = () => { done = true; resolve(false); closeModal(); };
      $('#cfOk').onclick = () => { done = true; resolve(true); closeModal(); };
    });
  }

  // ---------------- shell ----------------
  const NAV_GROUPS = [
    { label: '工作台', items: [
      { key: 'overview', label: '总览', icon: 'grid' },
      { key: 'inbox', label: '客服工作台', icon: 'chat', badge: 'inbox' },
      { key: 'seller', label: '让小二做点什么', icon: 'spark' },
    ] },
    { label: '商品经营', items: [
      { key: 'catalog', label: '商品与知识', icon: 'box' },
      { key: 'orders', label: '订单履约', icon: 'orders' },
    ] },
    { label: '系统', items: [
      { key: 'ops', label: '观测评测', icon: 'activity' },
      { key: 'accounts', label: '账号与风控', icon: 'shield' },
      { key: 'notify', label: '通知渠道', icon: 'bell' },
      { key: 'settings', label: '设置', icon: 'settings' },
    ] },
  ];
  const ROUTE_META = {
    overview: ['总览', '鱼小二正在替你值班'], inbox: ['客服工作台', '所有买家会话、上下文与转人工'],
    seller: ['让小二做点什么', '直接下指令，让 Agent 替你操作'],
    catalog: ['商品与知识', '商品状态、知识库版本与墓碑'], orders: ['订单履约', '待发货、退款与成交记录'],
    ops: ['观测评测', 'L0 健康 / L1 质量 / L2 成果 / 回放 / 黄金集'],
    accounts: ['账号与风控', '多账号登录生命周期、会话保活、反检测与熔断'],
    notify: ['通知渠道', '一个告警，多渠道投递 + 失败重试 + 投递日志'],
    settings: ['设置', '托管策略、通道与连接'],
  };

  function renderNav() {
    const nav = $('#nav');
    nav.innerHTML = NAV_GROUPS.map((g) => `
      <div class="nav-group">${esc(g.label)}</div>
      ${g.items.map((it) => {
        const badge = it.badge === 'inbox' && S.handoffCount > 0 ? `<span class="nav-badge">${S.handoffCount}</span>` : '';
        return `<a class="nav-item ${S.route === it.key ? 'active' : ''}" href="#/${it.key}">${icon(it.icon)}<span class="label">${esc(it.label)}</span>${badge}</a>`;
      }).join('')}
    `).join('');
  }

  async function refreshGlobal() {
    try {
      const [sys, alerts, handoff] = await Promise.all([
        api('/status'), api('/alerts?status=open&limit=50'), api('/conversations?filter=handoff'),
      ]);
      S.system = sys;
      S.alerts = alerts || [];
      S.handoffCount = (handoff || []).length;
      const online = sys.channel && sys.channel.online;
      $('#sideDot').className = `dot ${online ? '' : 'offline'}`;
      $('#sideStatus').textContent = online ? `${sys.channel.label || '通道'}在线` : '通道离线';
      $('#sideHosted').textContent = online ? '运行中' : '需处理';
      const ch = $('#channelChip');
      ch.className = `status-chip ${online ? '' : 'offline'}`;
      ch.innerHTML = `<i class="dot ${online ? '' : 'offline'}"></i>${online ? '通道在线' : '通道离线'}`;
      const llm = sys.llm || {};
      $('#llmChip').textContent = llm.enabled ? 'LLM 在线' : '规则模式';
      $('#llmChip').title = llm.mode || '';
      const risk = sys.risk || {};
      const rc = $('#riskChip');
      rc.classList.toggle('hidden', !risk.open);
      if (risk.open) rc.textContent = `风控熔断至 ${risk.until_human || ''}`;
      $('#shopName').textContent = (sys.settings && sys.settings.shop_name) || '我的闲鱼小店';
      const badge = $('#alertBadge');
      const count = S.alerts.filter((a) => a.status === 'open').length;
      badge.textContent = String(count);
      badge.classList.toggle('hidden', count === 0);
      renderNav();
    } catch (e) { /* keep shell usable */ }
  }

  function clearTimers() {
    S.timers.forEach((t) => clearInterval(t));
    S.timers = [];
  }
  function every(fn, ms) { const t = setInterval(fn, ms); S.timers.push(t); return t; }

  function parseRoute() {
    const raw = (location.hash || '').replace(/^#\/?/, '');
    const key = raw.split('?')[0] || 'overview';
    return ROUTE_META[key] ? key : 'overview';
  }

  async function renderRoute() {
    clearTimers();
    const route = parseRoute();
    S.route = route;
    const [title, subtitle] = ROUTE_META[route];
    $('#pageTitle').textContent = title;
    $('#pageSubtitle').textContent = subtitle;
    renderNav();
    const view = $('#view');
    view.innerHTML = `<div class="loading-page"><span class="spinner"></span> 正在加载…</div>`;
    try {
      if (route === 'overview') await pageOverview();
      else if (route === 'inbox') await pageInbox();
      else if (route === 'seller') await pageSeller();
      else if (route === 'catalog') await pageCatalog();
      else if (route === 'orders') await pageOrders();
      else if (route === 'ops') await pageOps();
      else if (route === 'accounts') await pageAccounts();
      else if (route === 'notify') await pageNotify();
      else if (route === 'settings') await pageSettings();
    } catch (e) {
      view.innerHTML = `<div class="card pad"><div class="empty"><div class="empty-ico">${icon('alert')}</div><strong>页面加载失败</strong>${esc(e.message)}<div class="mt12"><button class="btn" onclick="location.reload()">重新加载</button></div></div></div>`;
      toast(e.message, 'error');
    }
  }

  // =========================================================
  // Overview
  // =========================================================
  async function pageOverview() {
    const [ov, events] = await Promise.all([api('/overview'), api('/events?limit=7')]);
    renderOverview(ov, events);
    every(async () => {
      if (document.hidden) return;
      try { await refreshOverview(); } catch (e) { /* noop */ }
    }, 9000);
  }

  async function refreshOverview() {
    if (S.route !== 'overview') return;
    const [ov, events] = await Promise.all([api('/overview'), api('/events?limit=7')]);
    if (S.route === 'overview') renderOverview(ov, events);
  }

  function renderOverview(ov, events) {
    const t = ov.today || {};
    const sys = ov.system || {};
    const hour = new Date().getHours();
    const greet = hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
    const owner = (sys.settings && sys.settings.owner_name) || '店主';
    const convRate = clampPct(t.conversion_rate);
    const alerts = ov.alerts || [];
    const jobs = sys.jobs || [];
    const recent = ov.recent_conversations || [];
    const recentOrders = ov.recent_orders || [];
    const series = ov.series || [];
    const maxBar = Math.max(1, ...series.map((d) => Math.max(d.conversations || 0, d.orders || 0)));
    const chart = `<div class="bars">${series.map((d) => `
      <div class="bar-col" title="${esc(d.date)}：咨询 ${d.conversations} · 成交 ${d.orders}">
        <div class="bar-pair">
          <div class="bar green" style="height:${Math.max(3, (d.conversations / maxBar) * 100)}%"></div>
          <div class="bar coral" style="height:${Math.max(2, (d.orders / maxBar) * 100)}%"></div>
        </div>
        <span class="bar-label">${esc(d.label)}</span>
      </div>`).join('')}</div>`;

    $('#view').innerHTML = `
      <section class="overview-hero">
        <div class="hero-copy">
          <span class="eyebrow"><i class="dot"></i> 24h 托管中 · ${esc(sys.local_now || '')}</span>
          <h2>${greet}，${esc(owner)}。<br />鱼小二正在替你<em>接住每一个询单</em>。</h2>
          <p>买家消息先过入口网关，再按咨询/议价/售后分流；退款、纠纷和风险消息会通过你配置的通知渠道推送。今天的每一个会话都可在回放里追溯。</p>
          <div class="hero-actions">
            <button class="btn" id="heroSeller">${icon('spark')} 让小二做点什么</button>
            <button class="btn" id="heroInbox">${icon('chat')} 看客服工作台</button>
          </div>
          <div class="hero-meta"><span>${icon('shield')} 回复率优先，不做违规刷互动</span><span>${icon('clock')} 首响保护 · 夜间免打扰</span><span>${icon('lock')} 买卖双方数据最小化</span></div>
        </div>
        <div class="hero-side">
          <div class="north-star">
            <div class="ring" style="--pct:${convRate}"><span>${convRate}%</span></div>
            <div><div class="label">北极星 · 今日询单转化率</div><strong>${t.paid_orders || 0} 单成交 · GMV ${money(t.gmv || 0)}</strong><small>咨询 ${t.conversations || 0} 个会话</small></div>
          </div>
          <div class="hero-mini">
            <div><small>今日 GMV</small><strong>${money(t.gmv || 0)}</strong></div>
            <div><small>待发货</small><strong>${t.pending_ship || 0} 单</strong></div>
            <div><small>自动回复率</small><strong>${t.answer_rate || 0}%</strong></div>
            <div><small>待人工</small><strong>${t.handoff || 0} 个会话</strong></div>
          </div>
        </div>
      </section>

      <div class="metric-grid">
        ${metricCard('今日咨询', t.conversations || 0, `${t.inbound || 0} 条买家消息 · ${t.unanswered || 0} 个未答`, 'chat', '')}
        ${metricCard('首响 P95', `${t.first_response_p95 || 0}s`, `P50 ${t.first_response_p50 || 0}s · 自动回复 ${t.outbound || 0} 条`, 'clock', 'coral')}
        ${metricCard('询单转化率', `${t.conversion_rate || 0}%`, `${t.paid_orders || 0} 单成交 · 退款率 ${t.refund_rate || 0}%`, 'spark', 'amber')}
        ${metricCard('待办', (t.pending_ship || 0) + (t.handoff || 0), `${t.pending_ship || 0} 待发货 · ${t.handoff || 0} 待人工`, 'alert', 'purple')}
      </div>

      <div class="overview-grid">
        <div class="stack">
          <div class="card chart-card">
            <div class="card-head">
              <div><div class="card-title">${icon('activity')} 近 7 日咨询与成交</div><div class="card-sub">绿色=新咨询会话，珊瑚色=成交订单</div></div>
              <div class="legend"><span><i class="g"></i>咨询</span><span><i class="c"></i>成交</span></div>
            </div>
            ${chart}
          </div>
          <div class="grid-2">
            <div class="card pad">
              <div class="card-head"><div><div class="card-title">${icon('chat')} 最近的会话</div><div class="card-sub">点进去可以查看完整轨迹</div></div><button class="btn xs ghost" data-nav="inbox">全部 ${icon('arrow')}</button></div>
              <div class="recent-conv">
                ${recent.length ? recent.slice(0, 5).map((c) => `
                  <a class="recent-row" href="#/inbox" data-conv="${esc(c.id)}">
                    ${avatar(c.buyer_nick || '买家', avatarClass(c.buyer_nick))}
                    <div class="r-main"><strong>${esc(c.buyer_nick || '买家')} ${c.handoff ? chip('待人工', 'red') : ''}</strong><small>${esc(c.item_title || '—')} · ${esc(c.last_text || '暂无消息')}</small></div>
                    <span class="r-time">${esc(c.last_human || '')}</span>
                  </a>`).join('') : emptyBlock('还没有会话', '连接账号后等待真实买家消息', 'chat')}
              </div>
            </div>
            <div class="card pad">
              <div class="card-head"><div><div class="card-title">${icon('orders')} 最近订单</div><div class="card-sub">虚拟自动发货 / 实物待发货</div></div><button class="btn xs ghost" data-nav="orders">全部 ${icon('arrow')}</button></div>
              <div>
                ${recentOrders.length ? recentOrders.slice(0, 5).map((o) => `
                  <div class="order-mini">
                    <span class="chip ${o.delivery_mode === 'virtual' ? 'purple' : 'blue'}">${o.delivery_mode === 'virtual' ? '虚拟' : '实物'}</span>
                    <div class="o-main"><strong>${esc(o.title || '—')}</strong><small>${esc(o.buyer_nick || o.buyer_id)} · ${esc(fmtTime(o.created_at))}</small></div>
                    <div class="right"><div class="amount">${money(o.amount_cents)}</div><div>${orderStatus(o.status)}</div></div>
                  </div>`).join('') : emptyBlock('还没有订单', '买家下单后会出现在这里', 'orders')}
              </div>
            </div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('activity')} 实时动态</div><div class="card-sub">事件总线：消息、订单、工具、值守</div></div><button class="btn xs ghost" data-nav="ops">观测 ${icon('arrow')}</button></div>
            <div class="event-table">
              ${(events || []).slice(0, 6).map((e) => `<div class="event-row"><span class="event-topic">${esc(e.topic)}</span><span class="event-payload">${esc(compactPayload(e.payload))}</span><span class="chip ${e.status === 'done' ? 'green' : e.status === 'failed' ? 'red' : 'amber'}">${esc(e.status)}</span><span class="event-time">${esc(e.created_human || '')}</span></div>`).join('') || emptyBlock('暂无事件', '', 'activity')}
            </div>
          </div>
        </div>
        <div class="stack">
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('shield')} 值守任务</div><div class="card-sub">后台自动跑，异常会告警</div></div><button class="btn xs ghost" data-nav="ops">任务 ${icon('arrow')}</button></div>
            <div class="jobs">
              ${jobs.map((j) => `
                <div class="job">
                  <span class="job-ico">${icon(jobIcon(j.name))}</span>
                  <div class="job-main"><strong>${esc(j.title)}</strong><small>下次 ${esc(j.next_run_human || '—')} · ${j.last_status === 'ok' ? '上次成功' : j.last_status === 'failed' ? '上次失败' : '等待首次运行'}</small></div>
                  <button class="run" data-job="${esc(j.name)}" title="立即运行">${icon('play')}</button>
                </div>`).join('')}
            </div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('bell')} 告警</div><div class="card-sub">P0 强提醒 · P1 普通 · P2 信息</div></div><button class="btn xs ghost" id="openAlerts">全部 ${icon('arrow')}</button></div>
            <div class="alert-list">
              ${alerts.length ? alerts.slice(0, 4).map((a) => `
                <div class="alert-item"><span class="level ${esc(a.level)}">${esc(a.level)}</span><div class="a-main"><strong>${esc(a.title)}</strong><p>${esc(a.body || '')}</p></div><button class="a-act btn xs ghost" data-ack="${esc(a.id)}" title="标记已处理">${icon('check')}</button></div>`).join('') : emptyBlock('暂无告警', '有风险消息或退款时会在这里提醒', 'shield')}
            </div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('clock')} 交付节奏</div><div class="card-sub">当前真实链路</div></div></div>
            <div class="kv-grid">
              <div class="kv-box"><small>入口网关</small><strong>规则 + LLM 兜底</strong></div>
              <div class="kv-box"><small>回复护栏</small><strong>频控 / 夜间延迟</strong></div>
              <div class="kv-box"><small>写路径</small><strong>单写队列 + 乐观锁</strong></div>
              <div class="kv-box"><small>可观测</small><strong>回放 + 黄金集</strong></div>
            </div>
          </div>
        </div>
      </div>
    `;

    // bindings
    $('#heroSeller').onclick = () => navigate('seller');
    $('#heroInbox').onclick = () => navigate('inbox');
    $$('[data-nav]').forEach((b) => { b.onclick = () => navigate(b.dataset.nav); });
    $$('[data-job]').forEach((b) => { b.onclick = async () => { b.disabled = true; try { const r = await api(`/patrol/jobs/${b.dataset.job}/run`, { method: 'POST' }); toast(r.text || '已执行'); await refreshOverview(); } catch (e) { toast(e.message, 'error'); } finally { b.disabled = false; } }; });
    $$('[data-ack]').forEach((b) => { b.onclick = async () => { try { await api(`/alerts/${b.dataset.ack}/ack`, { method: 'POST' }); toast('已标记处理'); await refreshGlobal(); await refreshOverview(); } catch (e) { toast(e.message, 'error'); } }; });
    $('#openAlerts').onclick = openAlertCenter;
    $$('[data-conv]').forEach((a) => { a.onclick = (e) => { e.preventDefault(); sessionStorage.setItem('yx_conv', a.dataset.conv); navigate('inbox'); }; });
  }

  function metricCard(label, value, foot, ico, tone) {
    return `<div class="metric-card"><div class="top"><span class="metric-label">${esc(label)}</span><span class="metric-ico ${tone}">${icon(ico)}</span></div><div class="metric-value">${value}</div><div class="metric-foot">${esc(foot)}</div></div>`;
  }
  function emptyBlock(title, sub = '', ico = 'box') {
    return `<div class="empty"><div class="empty-ico">${icon(ico)}</div><strong>${esc(title)}</strong>${sub ? esc(sub) : ''}</div>`;
  }
  function jobIcon(name) { return { heartbeat: 'activity', link_check: 'link', polish: 'spark', daily_report: 'report' }[name] || 'clock'; }
  function compactPayload(p) {
    try { const s = JSON.stringify(p); return s.length > 110 ? s.slice(0, 108) + '…' : s; } catch (e) { return ''; }
  }
  function navigate(route) { location.hash = `#/${route}`; }

  async function openAlertCenter() {
    try {
      const alerts = await api('/alerts?status=open&limit=50');
      openModal({
        title: '告警中心', wide: true,
        body: alerts.length ? `<div class="alert-list">${alerts.map((a) => `
          <div class="alert-item"><span class="level ${esc(a.level)}">${esc(a.level)}</span><div class="a-main"><strong>${esc(a.title)}</strong><p>${esc(a.body || '')}</p><small class="muted">${esc(fmtTime(a.created_at, true))}</small></div><button class="btn xs" data-modal-ack="${esc(a.id)}">标记已处理</button></div>`).join('')}</div>` : emptyBlock('暂无未处理告警', '账号、退款、风险消息会触发分级告警', 'shield'),
      });
      $$('[data-modal-ack]').forEach((b) => { b.onclick = async () => { try { await api(`/alerts/${b.dataset.modalAck}/ack`, { method: 'POST' }); toast('已处理'); closeModal(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); } }; });
    } catch (e) { toast(e.message, 'error'); }
  }

  // =========================================================
  // Buyer experience
  // =========================================================
  // =========================================================
  // Inbox
  // =========================================================
  async function pageInbox() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>所有会话都在这里</h2><p>中间对话，右侧是 Agent 的上下文与轨迹；你可以随时接管。</p></div>
        <div class="btn-row"><button class="btn" id="inboxRefresh">${icon('refresh')} 刷新</button></div>
      </div>
      <div class="inbox-shell">
        <aside class="conv-pane">
          <div class="conv-pane-head">
            <div class="filter-bar" id="inboxFilters">
              <button class="filter-pill active" data-filter="active">全部</button>
              <button class="filter-pill" data-filter="handoff">待人工</button>
            </div>
            <div class="conv-search">${icon('search')}<input id="convSearch" placeholder="搜买家 / 商品 / 消息" /></div>
          </div>
          <div class="conv-list" id="convList"></div>
        </aside>
        <section class="thread-pane">
          <div id="threadHead"></div>
          <div class="thread-body" id="threadBody"></div>
          <div class="thread-foot">
            <div class="reply-box"><textarea id="manualInput" rows="1" placeholder="以店主身份回复，接管后将暂停自动回复…"></textarea><button class="btn primary" id="manualSend">${icon('send')} 发送</button></div>
            <div class="reply-hint"><small>Ctrl/⌘ + Enter 发送 · 手动回复会进入审计日志</small><span class="tiny muted" id="threadHint"></span></div>
          </div>
        </section>
        <aside class="context-pane" id="ctxPane"></aside>
      </div>`;

    S.inbox.filter = 'active'; S.inbox.id = null; S.inbox.detail = null;
    const saved = sessionStorage.getItem('yx_conv'); if (saved) { S.inbox.id = saved; sessionStorage.removeItem('yx_conv'); }
    $('#inboxRefresh').onclick = () => loadInbox(true);
    $$('#inboxFilters [data-filter]').forEach((b) => { b.onclick = () => { S.inbox.filter = b.dataset.filter; $$('#inboxFilters [data-filter]').forEach((x) => x.classList.toggle('active', x === b)); loadInbox(); }; });
    $('#convSearch').oninput = (e) => { S.inbox.search = e.target.value.trim(); renderConvList(); };
    $('#manualSend').onclick = sendManualReply;
    $('#manualInput').addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); sendManualReply(); } });
    await loadInbox(true);
    every(() => { if (!document.hidden && !S.inbox.busy) loadInbox(false).catch(() => {}); }, 6000);
  }

  async function loadInbox(selectFirst = false) {
    if (S.inbox.busy) return;
    S.inbox.busy = true;
    try {
      const convs = await api(`/conversations?filter=${S.inbox.filter}`);
      S.inbox.convs = convs || [];
      if (!S.inbox.id || !S.inbox.convs.some((c) => c.id === S.inbox.id)) {
        S.inbox.id = S.inbox.convs[0] ? S.inbox.convs[0].id : null;
      }
      renderConvList();
      if (S.inbox.id) await loadConversation(S.inbox.id, false);
      else renderEmptyThread();
    } finally { S.inbox.busy = false; }
  }

  function renderConvList() {
    const el = $('#convList'); if (!el) return;
    const q = S.inbox.search.toLowerCase();
    const list = S.inbox.convs.filter((c) => !q || [c.buyer_nick, c.item_title, c.last_text].some((v) => String(v || '').toLowerCase().includes(q)));
    if (!list.length) { el.innerHTML = emptyBlock('没有匹配的会话', S.inbox.filter === 'handoff' ? '当前没有待人工会话' : '等待真实买家消息', 'chat'); return; }
    el.innerHTML = list.map((c) => `
      <div class="conv-item ${c.id === S.inbox.id ? 'active' : ''}" data-id="${esc(c.id)}">
        ${avatar(c.buyer_nick || '买家', avatarClass(c.buyer_nick))}
        <div class="c-main">
          <div class="c-top"><strong>${esc(c.buyer_nick || '买家')}</strong><span class="c-time">${esc(c.last_human || '')}</span></div>
          <div class="c-item">${esc(c.item_title || '—')}</div>
          <div class="c-msg">${esc(c.last_text || '暂无消息')}</div>
          <div class="c-tags">${c.handoff ? chip('待人工', 'red') : chip('托管中', 'green')}${c.unread_for_owner ? chip(`${c.unread_for_owner} 未读`, 'amber') : ''}</div>
        </div>
        ${c.unread_for_owner ? '<i class="unread"></i>' : ''}
      </div>`).join('');
    el.querySelectorAll('[data-id]').forEach((row) => { row.onclick = () => { S.inbox.id = row.dataset.id; renderConvList(); loadConversation(S.inbox.id, true); }; });
  }

  async function loadConversation(id, withBusy = true) {
    if (!id) return;
    try {
      const d = await api(`/conversations/${id}`);
      S.inbox.detail = d;
      const conv = S.inbox.convs.find((c) => c.id === id);
      if (conv) { conv.unread_for_owner = 0; }
      renderThreadHead(); renderThreadBody(); renderContext(); renderConvList();
    } catch (e) { if (withBusy) toast(e.message, 'error'); }
  }

  function renderEmptyThread() {
    $('#threadHead').innerHTML = '';
    $('#threadBody').innerHTML = emptyBlock('选择一个会话', '左侧会话会实时更新', 'chat');
    $('#ctxPane').innerHTML = '';
  }

  function renderThreadHead() {
    const head = $('#threadHead'); const d = S.inbox.detail;
    if (!head) return;
    if (!d) { head.innerHTML = ''; return; }
    const c = d.conversation; const b = d.buyer || {}; const it = d.item;
    head.innerHTML = `<div class="thread-head">
      ${avatar(b.nick || '买家', avatarClass(b.nick))}
      <div class="t-main"><strong>${esc(b.nick || '买家')} ${c.handoff ? chip('人工接管', 'red') : chip('托管中', 'green')}</strong><small>${esc(it ? it.title : '无商品')} · 会话 ${esc(c.id)}</small></div>
      <div class="btn-row">
        ${c.handoff ? `<button class="btn sm soft" id="resumeBtn">${icon('rotate')} 恢复自动</button>` : `<button class="btn sm" id="takeoverBtn">${icon('user')} 接管</button>`}
        <button class="btn sm ghost" id="threadReplay">${icon('activity')} 回放</button>
      </div>
    </div>`;
    const takeover = $('#takeoverBtn'); if (takeover) takeover.onclick = async () => { try { await api(`/conversations/${c.id}/takeover`, { method: 'POST' }); toast('已接管，30 分钟内不再自动回复'); await loadConversation(c.id, true); } catch (e) { toast(e.message, 'error'); } };
    const resume = $('#resumeBtn'); if (resume) resume.onclick = async () => { try { await api(`/conversations/${c.id}/resume`, { method: 'POST' }); toast('已恢复托管'); await loadConversation(c.id, true); } catch (e) { toast(e.message, 'error'); } };
    const replay = $('#threadReplay'); if (replay) replay.onclick = () => { S.ops.sessionId = c.id; navigate('ops'); };
  }

  function renderThreadBody() {
    const body = $('#threadBody'); const d = S.inbox.detail;
    if (!body) return;
    if (!d) { body.innerHTML = emptyBlock('选择一个会话', '', 'chat'); return; }
    const msgs = d.messages || [];
    const c = d.conversation;
    const banner = c.handoff ? `<div class="notice red" style="margin-bottom:12px">${icon('user')} 已转人工（${esc(c.handoff_reason || '')}）。自动回复暂停，你可以直接在下方回复。</div>` : '';
    const sched = d.scheduled_reply ? `<div class="scheduled-note">${icon('clock')} 已排期 ${esc(d.scheduled_reply.send_after_human)} 发送：${esc(d.scheduled_reply.text)}（${esc(d.scheduled_reply.reason || '')}）</div>` : '';
    body.innerHTML = `${banner}${sched}${msgs.length ? msgs.map((m) => {
      const out = m.direction === 'out';
      const role = m.role || (out ? 'agent' : 'buyer');
      const who = !out ? '买' : role === 'seller' ? '店' : '鱼';
      return `<div class="msg-row ${out ? 'out' : ''} ${m.meta && m.meta.manual ? 'manual' : ''}">
        <span class="msg-avatar">${who}</span>
        <div class="msg-body"><div class="msg-bubble">${nl2br(m.text)}</div><div class="msg-meta">${esc(m.created_human)}${out ? ` · ${role === 'seller' ? '店主手动' : '鱼小二'}` : ' · 买家'}</div></div>
      </div>`;
    }).join('') : emptyBlock('还没有消息', '买家发消息后会出现在这里', 'chat')}`;
    body.scrollTop = body.scrollHeight;
    $('#manualInput').disabled = false;
    $('#threadHint').textContent = c.handoff ? '人工接管中' : '自动托管中';
  }

  function renderContext() {
    const el = $('#ctxPane'); const d = S.inbox.detail;
    if (!el) return;
    if (!d) { el.innerHTML = ''; return; }
    const b = d.buyer || {}; const it = d.item; const o = d.order; const t = (d.turns || [])[0];
    const tools = t ? (t.tools || []) : [];
    const hits = d.kb_hits || [];
    el.innerHTML = `
      <div class="context-block"><h4>买家档案</h4><div class="ctx-buyer">${avatar(b.nick || '买家', avatarClass(b.nick))}<div><strong>${esc(b.nick || '买家')}</strong><small>成交 ${b.deal_count || 0} 次 · ID ${esc(b.id || '')}</small></div></div>${b.note ? `<p class="tiny muted mt8">${esc(b.note)}</p>` : ''}</div>
      <div class="context-block"><h4>商品上下文</h4>${it ? `<div class="ctx-item"><strong>${esc(it.title)}</strong><div class="ctx-price">${esc(it.price_text)}</div><div class="ctx-kv"><span>底价</span><strong>${esc(it.floor_text)}</strong></div><div class="ctx-kv"><span>状态</span><strong>${(ITEM_STATUS[it.status] || [it.status])[0]}</strong></div><div class="ctx-kv"><span>知识版本</span><strong>v${it.knowledge_version}</strong></div></div>` : '<div class="muted tiny">无关联商品</div>'}</div>
      ${o ? `<div class="context-block"><h4>最新订单</h4><div class="ctx-item"><div class="flex-between"><strong>${esc(o.id)}</strong>${orderStatus(o.status)}</div><div class="ctx-kv"><span>金额</span><strong>${money(o.amount_cents)}</strong></div>${o.tracking_no ? `<div class="ctx-kv"><span>物流</span><strong>${esc(o.tracking_company || '')} ${esc(o.tracking_no)}</strong></div>` : ''}</div></div>` : ''}
      <div class="context-block"><h4>最近一轮 Agent</h4>${t ? `<div class="turn-mini">
        <div class="kv"><span>意图</span><strong>${esc(CATEGORY_LABEL[t.intent] || t.intent || '—')}</strong></div>
        <div class="kv"><span>动作</span><strong>${esc(ACTION_LABEL[t.action] || t.action || '—')}</strong></div>
        <div class="kv"><span>首响</span><strong>${t.latency_ms != null ? (t.latency_ms / 1000).toFixed(1) + 's' : '—'}</strong></div>
        <div class="kv"><span>工具</span><strong>${tools.length} 次</strong></div>
        ${tools.map((x) => `<div class="tool-line"><span class="${x.ok ? 'ok' : 'bad'}">${x.ok ? '✓' : '×'}</span><span class="grow">${esc(x.tool)}</span><span class="muted">${x.latency_ms || 0}ms</span></div>`).join('')}
      </div>` : '<div class="muted tiny">暂无轨迹</div>'}</div>
      <div class="context-block"><h4>知识命中</h4>${hits.length ? hits.map((h) => `<div class="kb-hit"><div class="kb-head"><strong>${esc(h.title || h.type)}</strong><span class="score">${Number(h.score || 0).toFixed(2)}</span></div><p>${esc(h.snippet || h.text || '')}</p></div>`).join('') : '<div class="muted tiny">本轮未命中 FAQ</div>'}</div>
      <div class="context-block"><h4>告警</h4>${(d.alerts || []).length ? d.alerts.slice(0, 3).map((a) => `<div class="alert-mini ${esc(a.level)}">${esc(a.title)}</div>`).join('') : '<div class="muted tiny">暂无</div>'}</div>
    `;
  }

  async function sendManualReply() {
    const input = $('#manualInput'); const text = (input.value || '').trim();
    if (!text || !S.inbox.id) return;
    const btn = $('#manualSend'); btn.disabled = true;
    try {
      await api(`/conversations/${S.inbox.id}/reply`, { method: 'POST', body: { text } });
      input.value = '';
      toast('已以店主身份发送，自动回复暂停 2 小时');
      await loadConversation(S.inbox.id, true);
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); } finally { btn.disabled = false; }
  }

  // =========================================================
  // Seller agent chat
  // =========================================================
  async function pageSeller() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>让小二做点什么</h2><p>把图片和描述发给小二，它自动补标题、价格、分类、所在地；确认卡可编辑，改完再上架。</p></div>
        <div class="btn-row"><button class="btn soft" id="sellerOrders">${icon('orders')} 订单履约</button><button class="btn" id="sellerRefresh">${icon('refresh')} 刷新</button></div>
      </div>
      <div class="seller-wrap">
        <div class="seller-chat">
          <div class="seller-head">
            <span class="s-avatar">鱼</span>
            <div><strong>鱼小二 · 你的店长 Agent</strong><small><i class="dot" style="width:5px;height:5px"></i> 可对话 · 会先确认再动平台</small></div>
            <div class="head-actions"></div>
          </div>
          <div class="seller-body" id="sellerBody"></div>
          <div class="seller-quick">
            <button class="quick-chip" data-send="发布设置">发布设置</button>
            <button class="quick-chip" data-send="订单？">订单？</button>
            <button class="quick-chip" data-send="日报">日报</button>
            <button class="quick-chip" data-send="人工">人工</button>
            <button class="quick-chip" data-send="恢复">恢复</button>
            <button class="quick-chip" data-send="擦亮">擦亮</button>
            <button class="quick-chip" data-send="待确认">待确认</button>
          </div>
          <div class="attach-strip" id="sellerAttachPreview"></div>
          <div class="seller-compose"><input type="file" id="sellerFile" accept="image/*" multiple hidden /><button class="btn ghost" id="sellerAttach">图片</button><textarea id="sellerInput" rows="1" placeholder="发图片 + 描述，例如：9.9 元虚拟资料，拍下自动发"></textarea><button class="btn primary" id="sellerSend">${icon('send')} 发送</button></div>
        </div>
        <aside class="seller-side" id="sellerSide"></aside>
      </div>`;
    $('#sellerOrders').onclick = () => navigate('orders');
    $('#sellerRefresh').onclick = () => loadSeller(true);
    $('#sellerSend').onclick = () => sendSeller();
    $('#sellerAttach').onclick = () => $('#sellerFile').click();
    $('#sellerFile').onchange = async (e) => {
      const files = Array.from(e.target.files || []);
      e.target.value = '';
      if (!files.length) return;
      try { await uploadSellerImages(files); } catch (err) { toast(err.message, 'error'); }
    };
    $('#sellerInput').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendSeller(); } });
    $$('.seller-quick [data-send]').forEach((b) => { b.onclick = () => sendSeller(b.dataset.send); });
    await loadSeller(true);
    every(() => { if (!document.hidden && !S.seller.busy) loadSeller(false).catch(() => {}); }, 6000);
  }

  async function loadSeller(scroll = false) {
    if (S.seller.busy) return; S.seller.busy = true;
    try {
      const data = await api('/seller/messages');
      S.seller.messages = data.messages || [];
      S.seller.pending = data.pending || [];
      renderSellerMessages(scroll);
      renderSellerSide();
    } finally { S.seller.busy = false; }
  }

  function renderSellerMessages(scroll = false) {
    const body = $('#sellerBody'); if (!body) return;
    const msgs = S.seller.messages || [];
    if (!msgs.length) { body.innerHTML = emptyBlock('还没有对话', '先说「发布设置 …」，再让小二十架上架；也可以问订单/日报/擦亮', 'chat'); return; }
    body.innerHTML = msgs.map((m) => {
      const card = m.meta && m.meta.card;
      if (card) return renderSellerCard(m, card);
      const owner = m.role === 'owner' || m.direction === 'in';
      if (m.role === 'system') return `<div class="system-line">${esc(m.text)} · ${esc(m.created_human)}</div>`;
      return `<div class="seller-msg ${owner ? 'owner' : ''}">
        <span class="msg-avatar">${owner ? '我' : '鱼'}</span>
        <div><div class="s-bubble">${nl2br(m.text)}</div>${(m.meta && m.meta.images || []).length ? `<div class="s-attach">${icon('image')} ${m.meta.images.length} 张图片</div>` : ''}<div class="s-time">${esc(owner ? '我' : '鱼小二')} · ${esc(m.created_human)}</div></div>
      </div>`;
    }).join('');
    if (scroll) body.scrollTop = body.scrollHeight;
    body.querySelectorAll('[data-cc-confirm]').forEach((b) => b.onclick = () => resolveConfirmation(b.dataset.ccConfirm, true));
    body.querySelectorAll('[data-cc-cancel]').forEach((b) => b.onclick = () => resolveConfirmation(b.dataset.ccCancel, false));
    body.querySelectorAll('[data-edit-confirm]').forEach((b) => b.onclick = () => openEditPublishModal(b.dataset.editConfirm));
    body.querySelectorAll('[data-goto-orders]').forEach((b) => b.onclick = () => navigate('orders'));
  }

  function renderSellerCard(m, card) {
    if (card.type === 'confirmation') {
      const p = card.preview || {};
      const kindLabel = { publish_listing: '发布预览', publish_batch: '批量发布预览', offline_item: '下架确认', relist_item: '重新上架确认', change_price: '改价确认', bargain_price: '买家议价' }[p.kind] || '待确认';
      const status = card.status || 'pending';
      let body = '';
      if (p.kind === 'publish_batch') {
        const items = p.items || [];
        body = `<div class="cc-title">共 ${items.length} 件商品</div><div class="batch-preview compact">${items.map((x) => `<div class="batch-row"><div><strong>${esc(x.title)}</strong><div class="tiny muted">${x.delivery_mode === 'virtual' ? '虚拟自动发货' : '实物待发货'} · ${esc(x.category || '')}</div></div><div class="right"><strong>${esc(x.price_text || money(x.price_cents))}</strong><div>${chip('底价 ' + money(x.floor_price_cents), 'line')}</div></div></div>`).join('')}</div><div class="cc-row"><span>动作</span><strong>按顺序发布，仍走单写队列</strong></div>`;
      } else if (p.kind === 'publish_listing') {
        body = `<div class="cc-title">${esc(p.title)}</div><div class="cc-price"><strong>${esc(p.price_text || money(p.price_cents))}</strong><del>底价 ${money(p.floor_price_cents)}</del></div><div class="cc-row"><span>类型</span><strong>${p.delivery_mode === 'virtual' ? '虚拟自动发货' : '实物待发货'}</strong></div><div class="cc-row"><span>成色</span><strong>${esc(p.condition || '—')}</strong></div><div class="cc-row"><span>商品分类</span><strong>${esc(p.category || '—')}</strong></div><div class="cc-row"><span>发布分类</span><strong>${esc(p.publish_category || '未配置')}</strong></div><div class="cc-row"><span>图片 / 所在地</span><strong>${(p.images || []).length} 张 · ${esc(p.publish_address || '未配置')}</strong></div><div class="cc-desc">${esc(p.description || '')}</div>`;
      } else if (p.kind === 'offline_item') {
        body = `<div class="cc-title">${esc(p.title)}</div><div class="cc-row"><span>当前价格</span><strong>${money(p.price_cents)}</strong></div><div class="cc-row"><span>说明</span><strong>下架后知识库打墓碑，买家检索立即失效</strong></div>`;
      } else if (p.kind === 'relist_item') {
        body = `<div class="cc-title">${esc(p.title)}</div><div class="cc-row"><span>当前价格</span><strong>${money(p.price_cents)}</strong></div><div class="cc-row"><span>图片 / 分类</span><strong>${(p.images || []).length} 张 · ${esc(p.publish_category || '—')}</strong></div><div class="cc-row"><span>所在地</span><strong>${esc(p.publish_address || '—')}</strong></div><div class="cc-row"><span>说明</span><strong>会重新发布一条新商品，旧下架商品仍在后台</strong></div>`;
      } else if (p.kind === 'change_price') {
        body = `<div class="cc-title">${esc(p.title)}</div><div class="cc-price"><strong>${esc(p.new_price_text || money(p.new_price_cents))}</strong><del>${esc(p.old_price_text || money(p.old_price_cents))}</del></div><div class="cc-row"><span>生效</span><strong>同步商品知识版本</strong></div>`;
      } else if (p.kind === 'bargain_price') {
        body = `<div class="cc-title">${esc(p.title)}</div><div class="cc-price"><strong>${money(p.offer_cents)}</strong><del>标价 ${money(p.old_price_cents)}</del></div><div class="cc-row"><span>买家</span><strong>${esc(p.buyer_nick || '')}</strong></div><div class="cc-row"><span>动作</span><strong>同意后改价并通知买家</strong></div>`;
      }
      const actions = status === 'pending' ? `<div class="cc-actions">${p.kind === 'publish_listing' ? `<button class="btn sm soft" data-edit-confirm="${esc(card.confirmation_id)}">编辑</button>` : ''}<button class="btn sm ghost" data-cc-cancel="${esc(card.confirmation_id)}">取消</button><button class="btn sm primary" data-cc-confirm="${esc(card.confirmation_id)}">${p.kind === 'bargain_price' ? '同意改价' : p.kind === 'publish_batch' ? `确认发布 ${(p.items || []).length} 件` : p.kind === 'relist_item' ? '重新上架' : '确认执行'}</button></div>` : '';
      return `<div class="seller-msg"><span class="msg-avatar">鱼</span><div class="confirm-card"><div class="cc-head"><strong>${kindLabel}</strong>${chip(status === 'pending' ? '待确认' : statusText(status), status === 'pending' ? 'amber' : status === 'confirmed' ? 'green' : 'gray')}</div><div class="cc-body">${body}</div>${actions}</div></div>`;
    }
    if (card.type === 'order') {
      return `<div class="seller-msg"><span class="msg-avatar">鱼</span><div class="order-card"><div class="oc-top"><span>新订单 · 已付款</span>${chip('待发货', 'amber')}</div><strong>${esc(card.title || '')}</strong><div class="oc-amount">${money(card.amount_cents)}</div><div class="oc-actions"><button class="btn xs" data-goto-orders>去订单页处理</button></div></div></div>`;
    }
    if (card.type === 'order_list') {
      return `<div class="seller-msg"><span class="msg-avatar">鱼</span><div class="order-list-card">${(card.orders || []).map((o) => `<div class="ol-row"><div class="ol-main"><strong>${esc(o.title)}</strong><small>${esc(o.id)} · ${esc(o.buyer_id)}</small></div><span class="tiny">${money(o.amount_cents)}</span>${orderStatus(o.status)}</div>`).join('')}<div class="ol-row"><button class="btn xs" data-goto-orders>打开订单履约</button></div></div></div>`;
    }
    if (card.type === 'shipped') {
      return `<div class="seller-msg"><span class="msg-avatar">鱼</span><div class="order-card"><div class="oc-top"><span>发货回填成功</span>${chip('已通知买家', 'green')}</div><strong>${esc(card.company)} ${esc(card.tracking_no)}</strong><div class="oc-actions"><button class="btn xs" data-goto-orders>查看订单</button></div></div></div>`;
    }
    return `<div class="system-line">${esc(m.text)}</div>`;
  }

  function statusText(status) {
    return { pending: '待确认', confirmed: '已执行', cancelled: '已取消', expired: '已过期' }[status] || status;
  }

  function renderSellerSide() {
    const side = $('#sellerSide'); if (!side) return;
    const pending = S.seller.pending || [];
    const nt = (S.system && S.system.notify) || {};
    side.innerHTML = `
      <div class="card side-card">
        <div class="card-head"><div><div class="card-title">${icon('bell')} 业务提醒走通知渠道</div><div class="card-sub">退款 / 纠纷 / 风险</div></div>${chip(`${nt.enabled || 0} 个渠道`, (nt.enabled || 0) ? 'green' : 'gray')}</div>
        <div class="turn-mini">
          <div class="kv"><span>已启用</span><strong>${nt.enabled || 0} / ${nt.channels || 0}</strong></div>
          <div class="kv"><span>已发送</span><strong>${nt.sent || 0}</strong></div>
          <div class="kv"><span>失败</span><strong>${nt.failed || 0}</strong></div>
        </div>
        <div class="muted tiny mt8">退款、纠纷、风险消息只推送到已配置的通知渠道，不再写进这个对话。</div>
        <button class="btn sm soft mt8" data-side-notify>${icon('settings')} 配置通知渠道</button>
      </div>
      <div class="card side-card">
        <div class="card-head"><div><div class="card-title">${icon('check')} 待确认</div><div class="card-sub">写平台动作必须你点头</div></div>${chip(String(pending.length), pending.length ? 'amber' : 'gray')}</div>
        ${pending.length ? pending.map((c) => `
          <div class="pending-item"><strong>${esc(c.title)}</strong><small>${esc(c.kind)} · 过期 ${esc(fmtTime(c.expires_at, true))}</small><div class="flex">${c.kind === 'publish_listing' ? `<button class="btn xs soft" data-edit-confirm="${esc(c.id)}">编辑</button>` : ''}<button class="btn xs ghost" data-cc-cancel="${esc(c.id)}">取消</button><button class="btn xs primary" data-cc-confirm="${esc(c.id)}">确认</button></div></div>`).join('') : `<div class="muted tiny">没有待确认的操作。发图片+描述即可生成可编辑发布卡。</div>`}
      </div>
      <div class="card side-card">
        <div class="card-head"><div><div class="card-title">${icon('message')} 指令速查</div><div class="card-sub">直接对小二说</div></div></div>
        <div class="turn-mini">
          <div class="kv"><span>最省事</span><strong>发图片 + 描述，自动补参数</strong></div>
          <div class="kv"><span>配置</span><strong>发布设置 图片=… 分类ID=… 地址=…</strong></div>
          <div class="kv"><span>上架</span><strong>上架：标题 价格 描述</strong></div>
          <div class="kv"><span>改价</span><strong>改价 商品名 到 199</strong></div>
          <div class="kv"><span>下架</span><strong>下架 商品名</strong></div>
          <div class="kv"><span>重新上架</span><strong>重新上架 商品名</strong></div>
          <div class="kv"><span>发货</span><strong>发货 ord_xxx 顺丰 SF…</strong></div>
          <div class="kv"><span>查询</span><strong>订单？ / 日报 / 擦亮</strong></div>
          <div class="kv"><span>人工</span><strong>人工 买家昵称 / 恢复 买家昵称</strong></div>
        </div>
      </div>`;
    side.querySelectorAll('[data-cc-confirm]').forEach((b) => b.onclick = () => resolveConfirmation(b.dataset.ccConfirm, true));
    side.querySelectorAll('[data-cc-cancel]').forEach((b) => b.onclick = () => resolveConfirmation(b.dataset.ccCancel, false));
    side.querySelectorAll('[data-edit-confirm]').forEach((b) => b.onclick = () => openEditPublishModal(b.dataset.editConfirm));
    const notifyBtn = side.querySelector('[data-side-notify]');
    if (notifyBtn) notifyBtn.onclick = () => navigate('notify');
  }

  async function uploadSellerImages(files) {
    const fd = new FormData();
    for (const file of files.slice(0, 9)) fd.append('files', file);
    const response = await fetch('/api/media', { method: 'POST', body: fd });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || '图片上传失败');
    S.seller.images = [...S.seller.images, ...(data.paths || [])].slice(0, 9);
    renderSellerAttachments();
    toast(`已添加 ${(data.paths || []).length} 张图片`);
  }

  function renderSellerAttachments() {
    const el = $('#sellerAttachPreview'); if (!el) return;
    el.innerHTML = (S.seller.images || []).map((path, i) => {
      const name = String(path).split(/[\\/]/).pop();
      return `<span class="attach-chip">${icon('image')} ${esc(name)}<button data-rm-image="${i}" title="移除">${icon('x')}</button></span>`;
    }).join('');
    el.querySelectorAll('[data-rm-image]').forEach((b) => {
      b.onclick = () => { S.seller.images.splice(Number(b.dataset.rmImage), 1); renderSellerAttachments(); };
    });
  }

  async function sendSeller(textArg) {
    const input = $('#sellerInput');
    const text = (textArg || (input ? input.value : '') || '').trim();
    if (!text || S.seller.busy) return;
    const images = [...(S.seller.images || [])];
    S.seller.busy = true;
    if (input) input.value = '';
    const btn = $('#sellerSend'); if (btn) btn.disabled = true;
    try {
      const res = await api('/seller/message', { method: 'POST', body: { text, images } });
      if (images.length) { S.seller.images = []; renderSellerAttachments(); }
      S.seller.messages = res.messages || [];
      renderSellerMessages(true);
      const data = await api('/seller/messages');
      S.seller.messages = data.messages || []; S.seller.pending = data.pending || [];
      renderSellerMessages(true);
      renderSellerSide((await api('/alerts?status=open&limit=6')) || []);
      if (res.result && res.result.ok === false) toast(res.result.error || '指令未执行', 'warn');
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); if (input) input.value = text; }
    finally { S.seller.busy = false; if (btn) btn.disabled = false; if (input) input.focus(); }
  }

  function openEditPublishModal(confirmationId) {
    const cfm = (S.seller.pending || []).find((x) => x.id === confirmationId);
    const p = (cfm && cfm.preview) || {};
    if (!cfm || p.kind !== 'publish_listing') { toast('确认项已变化，请刷新重试', 'warn'); loadSeller(true); return; }
    const cat = p.category || '';
    openModal({
      title: '编辑发布预览', wide: true,
      body: `<div class="notice mb12">${icon('alert')} 这里是 Agent 的兜底编辑区；保存后仍然要点“确认执行”才会动平台。</div>
        <div class="form-grid">
          <div class="field"><label>标题</label><input class="input" id="epTitle" value="${esc(p.title || '')}" /></div>
          <div class="field"><label>售价（元）</label><input class="input" id="epPrice" type="number" min="0.01" step="0.01" value="${((p.price_cents || 0) / 100).toFixed(2)}" /></div>
          <div class="field"><label>底价（元）</label><input class="input" id="epFloor" type="number" min="0.01" step="0.01" value="${((p.floor_price_cents || 0) / 100).toFixed(2)}" /></div>
          <div class="field"><label>类型</label><select class="input" id="epType"><option value="physical" ${p.delivery_mode !== 'virtual' ? 'selected' : ''}>实物</option><option value="virtual" ${p.delivery_mode === 'virtual' ? 'selected' : ''}>虚拟</option></select></div>
          <div class="field"><label>库存 / 数量</label><input class="input" id="epStock" type="number" min="0" value="${esc(p.stock || 1)}" /></div>
          <div class="field"><label>店铺分类（展示用）</label><input class="input" id="epCategory" value="${esc(cat)}" disabled /></div>
          <div class="field" style="grid-column:1/-1"><label>商品描述</label><textarea class="input" id="epDesc" rows="3">${esc(p.description || '')}</textarea></div>
          <div class="field" style="grid-column:1/-1"><label>图片（每行一个 URL / 本地路径）</label><textarea class="input" id="epImages" rows="2">${esc((p.images || []).join('\n'))}</textarea></div>
          <div class="field"><label>平台分类 ID</label><input class="input" id="epCatId" value="${esc(p.publish_category_id || '')}" /></div>
          <div class="field"><label>平台分类名</label><input class="input" id="epCatName" value="${esc(p.publish_category || '')}" /></div>
          <div class="field"><label>频道分类 ID</label><input class="input" id="epChannelId" value="${esc(p.publish_channel_cat_id || '')}" /></div>
          <div class="field"><label>淘宝分类 ID</label><input class="input" id="epTbId" value="${esc(p.publish_tb_cat_id || '')}" /></div>
          <div class="field"><label>所在地</label><input class="input" id="epAddress" value="${esc(p.publish_address || '')}" /></div>
          <div class="field"><label>发布模式</label><select class="input" id="epMode"><option value="personal" ${p.publish_mode !== 'shop' ? 'selected' : ''}>普通卖家</option><option value="shop" ${p.publish_mode === 'shop' ? 'selected' : ''}>鱼小铺</option></select></div>
          <div class="field"><label>发货方式</label><select class="input" id="epShip">${['free', 'none', 'fixed', 'distance', 'template'].map((x) => `<option value="${x}" ${p.publish_shipping_method === x ? 'selected' : ''}>${x}</option>`).join('')}</select></div>
        </div>`,
      footer: `<button class="btn ghost" id="epCancel">取消</button><button class="btn primary" id="epSave">保存修改</button>`,
    });
    $('#epCancel').onclick = closeModal;
    $('#epSave').onclick = async () => {
      const price = Math.round(Number($('#epPrice').value) * 100);
      const floor = Math.round(Number($('#epFloor').value) * 100);
      if (!price) { toast('售价必须大于 0', 'error'); return; }
      const body = {
        title: $('#epTitle').value.trim(), description: $('#epDesc').value.trim(),
        price_cents: price, floor_price_cents: floor,
        delivery_mode: $('#epType').value, stock: Number($('#epStock').value) || 0,
        images: $('#epImages').value.split('\n').map((x) => x.trim()).filter(Boolean),
        category_id: $('#epCatId').value.trim(), category_name: $('#epCatName').value.trim(),
        channel_cat_id: $('#epChannelId').value.trim(), tb_cat_id: $('#epTbId').value.trim(),
        address: $('#epAddress').value.trim(), mode: $('#epMode').value,
        shipping_method: $('#epShip').value,
      };
      try {
        await api(`/confirmations/${confirmationId}`, { method: 'PATCH', body });
        toast('预览已更新，确认后才会发布'); closeModal(); await loadSeller(true);
      } catch (e) { toast(e.message, 'error'); }
    };
  }

  async function resolveConfirmation(id, approve) {
    try {
      const res = await api(`/confirmations/${id}/${approve ? 'confirm' : 'cancel'}`, { method: 'POST' });
      toast(res.ok ? (approve ? '已执行' : '已取消') : '确认项已处理', res.ok ? 'ok' : 'warn');
      await loadSeller(true);
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); }
  }

  // =========================================================
  // Catalog / knowledge
  // =========================================================
  async function pageCatalog() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>商品与知识源</h2><p>在售商品可直接改价/下架；也可在「让小二做点什么」用一句话操作。</p></div>
        <div class="tabs"><button class="tab active" data-tab="items">商品</button><button class="tab" data-tab="knowledge">知识库</button></div>
      </div>
      <div id="catalogMain"><div class="loading-page"><span class="spinner"></span> 加载商品…</div></div>`;
    $$('.tabs [data-tab]').forEach((b) => b.onclick = () => { S.catalog.tab = b.dataset.tab; $$('.tabs [data-tab]').forEach((x) => x.classList.toggle('active', x === b)); renderCatalog(); });
    await loadCatalog();
  }

  async function loadCatalog() {
    const [items, sources] = await Promise.all([api('/items'), api('/knowledge/sources')]);
    S.catalog.items = items || []; S.catalog.sources = sources || [];
    renderCatalog();
  }

  function renderCatalog() {
    const main = $('#catalogMain'); if (!main) return;
    if (S.catalog.tab === 'items') {
      main.innerHTML = `<div class="filter-bar mb12"><span class="tiny muted">${S.catalog.items.length} 件商品</span><button class="btn sm ghost" id="catalogRefresh">${icon('refresh')} 刷新</button><button class="btn sm" id="catalogAdd">${icon('spark')} 新增商品</button></div>
        <div class="item-grid">${S.catalog.items.map((it) => renderItemCard(it)).join('') || emptyBlock('还没有商品', '新增商品或等待真实订单/消息同步', 'box')}</div>`;
      $('#catalogRefresh').onclick = loadCatalog;
      $('#catalogAdd').onclick = openCreateItemModal;
      main.querySelectorAll('[data-view-item]').forEach((b) => b.onclick = () => openItemDetail(b.dataset.viewItem));
      main.querySelectorAll('[data-floor-item]').forEach((b) => b.onclick = () => openFloorDialog(b.dataset.floorItem));
      main.querySelectorAll('[data-price-item]').forEach((b) => b.onclick = () => openPriceModal(b.dataset.priceItem, S.catalog.items.find((x) => x.id === b.dataset.priceItem)));
      main.querySelectorAll('[data-offline-item]').forEach((b) => b.onclick = async () => {
        if (!(await confirmAction({ title: '下架商品', message: '会调用原生 batch.offline，并同步知识库墓碑。', confirmText: '下架', danger: true }))) return;
        try { await api(`/items/${b.dataset.offlineItem}/offline`, { method: 'POST' }); toast('已下架'); await loadCatalog(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
      });
      main.querySelectorAll('[data-relist-item]').forEach((b) => b.onclick = async () => {
        if (!(await confirmAction({ title: '重新上架', message: '会按保存的图片/分类/地址重新发布一条新商品；旧的下架商品仍在闲鱼后台。', confirmText: '重新上架' }))) return;
        try { await api(`/items/${b.dataset.relistItem}/relist`, { method: 'POST' }); toast('已重新上架'); await loadCatalog(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
      });
      return;
    }
    main.innerHTML = `
      <div class="kb-layout">
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('search')} 检索知识库</div><div class="card-sub">FTS5 + 中文 bigram · namespace 过滤 · 墓碑排除</div></div></div>
          <div class="kb-search"><input class="input" id="kbQuery" placeholder="例如：发货时间 / 怎么发 / 能便宜吗" /><button class="btn primary" id="kbSearchBtn">检索</button></div>
          <div id="kbResults" class="mt12">${S.catalog.results === null ? '<div class="muted tiny">输入问题，看看 Agent 会命中哪条知识。</div>' : (S.catalog.results.length ? S.catalog.results.map((h) => `<div class="kb-result"><div class="kr-top"><strong>${esc(h.title || h.type)}</strong><span class="score">${Number(h.score || 0).toFixed(2)}</span></div><p>${esc(h.snippet || h.text || '')}</p></div>`).join('') : '<div class="muted tiny">没有命中。真实 Agent 会转人工，不会编造。</div>')}</div>
          <div class="notice mt16">${icon('shield')} 检索路径零 LLM；命中失败时退化为 LIKE，并标记 degraded。买家侧永远不会看到底价字段。</div>
        </div>
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('box')} 知识源</div><div class="card-sub">${S.catalog.sources.length} 个 source · 商品 / FAQ / 店铺</div></div><button class="btn sm ghost" id="kbRefresh">${icon('refresh')}</button></div>
          <div style="max-height:600px;overflow:auto">${S.catalog.sources.map((s) => `
            <div class="source-row"><div class="sr-top"><strong>${esc(s.title)}</strong>${chip(s.type, s.type === 'faq' ? 'blue' : s.type === 'item' ? 'green' : 'gray')}${s.status === 'tombstone' ? chip('墓碑', 'gray') : ''}<span class="tiny muted" style="margin-left:auto">v${s.version}</span></div><p>${esc(s.content_snippet)}</p><div class="tiny muted mt8">${esc(s.namespace)} · ${esc(fmtTime(s.updated_at, true))}</div></div>`).join('') || emptyBlock('还没有知识源', '', 'box')}</div>
        </div>
      </div>`;
    $('#kbRefresh').onclick = loadCatalog;
    const search = async () => { const q = $('#kbQuery').value.trim(); if (!q) return; S.catalog.results = await api(`/knowledge/search?q=${encodeURIComponent(q)}&k=5`); renderCatalog(); };
    $('#kbSearchBtn').onclick = search;
    $('#kbQuery').addEventListener('keydown', (e) => { if (e.key === 'Enter') search(); });
  }

  function renderItemCard(it) {
    const st = ITEM_STATUS[it.status] || [it.status, 'gray'];
    return `<div class="card item-card">
      <div class="ic-top"><div class="ic-thumb">${esc(it.image_hint || '📦')}</div><div class="ic-main"><h3>${esc(it.title)}</h3><div class="ic-sub">${chip(st[0], st[1])}${chip(it.delivery_mode === 'virtual' ? '虚拟' : '实物', it.delivery_mode === 'virtual' ? 'purple' : 'blue')}${it.offline_reason ? chip(esc(it.offline_reason), 'gray') : ''}</div></div></div>
      <div class="ic-price">${esc(it.price_text)}<small>底价 ${esc(it.floor_text)}</small></div>
      <div class="ic-desc">${esc(it.description || '')}</div>
      <div class="ic-stats"><div><small>已售</small><strong>${it.sold_count || 0}</strong></div><div><small>知识版本</small><strong>v${it.knowledge_version}</strong></div><div><small>订单</small><strong>${it.order_count || 0}</strong></div></div>
      <div class="ic-actions">
        <button class="btn xs" data-view-item="${esc(it.id)}">${icon('eye')} 详情</button>
        <button class="btn xs ghost" data-floor-item="${esc(it.id)}">${icon('edit')} 底价</button>
        ${it.platform_item_id && it.status === 'live' ? `<button class="btn xs soft" data-price-item="${esc(it.id)}">改价</button><button class="btn xs amber" data-offline-item="${esc(it.id)}">下架</button>` : ''}
        ${['offline', 'sold_out'].includes(it.status) ? `<button class="btn xs primary" data-relist-item="${esc(it.id)}">重新上架</button>` : ''}
      </div>
    </div>`;
  }

  async function openItemDetail(id) {
    try {
      const it = await api(`/items/${id}`);
      openModal({
        title: '商品详情', wide: true,
        body: `<div class="flex mb12">${chip((ITEM_STATUS[it.status] || [it.status])[0], (ITEM_STATUS[it.status] || [])[1] || 'gray')}${chip(it.delivery_mode === 'virtual' ? '虚拟' : '实物', 'blue')}${chip(`知识 v${it.knowledge_version}`, 'purple')}</div>
          <div class="btn-row mb12">${!it.platform_item_id ? `<button class="btn sm primary" id="publishItemBtn">发布上架</button>` : ''}${it.platform_item_id && it.status === 'live' ? `<button class="btn sm amber" id="offlineItemBtn">下架</button><button class="btn sm soft" id="priceItemBtn">改价</button>` : ''}${['offline', 'sold_out'].includes(it.status) ? `<button class="btn sm primary" id="relistItemBtn">重新上架</button>` : ''}</div>
          <div class="flex mb8"><span class="tiny muted">平台商品 ID</span><input class="input" id="bindPlatformId" value="${esc(it.platform_item_id || '')}" placeholder="从闲鱼商品链接获取，绑定后订单才能自动匹配" /><button class="btn sm soft" id="bindPlatformBtn">绑定</button>${it.delivery_mode === 'physical' ? `<button class="btn sm ghost" id="makeVirtualBtn">设为虚拟自动发货</button>` : ''}</div>
          <h3 style="margin:0 0 6px;font-size:16px">${esc(it.title)}</h3><div class="muted">${esc(it.category || '')}</div>
          <div class="grid-3 mt16"><div class="kv-box"><small>售价</small><strong>${esc(it.price_text)}</strong></div><div class="kv-box"><small>底价</small><strong>${esc(it.floor_text)}</strong></div><div class="kv-box"><small>已售</small><strong>${it.sold_count}</strong></div></div>
          <div class="notice mt16">${icon('box')} 商品知识：${it.knowledge ? `v${it.knowledge.version}，最后同步 ${esc(fmtTime(it.knowledge.updated_at, true))}` : '尚无 live 知识源（可能是待确认/草稿）'}</div>
          <div class="divider"></div><div class="section-title">商品描述</div><div class="pre" style="font-size:12px;line-height:1.7;color:var(--ink-2)">${esc(it.description)}</div>
          ${it.delivery_mode === 'virtual' ? `<div class="divider"></div><div class="section-title">卡券库存 · ${it.card_counts?.available || 0} 可用 / ${it.card_counts?.used || 0} 已用</div>
            <div class="card-pool">${(it.cards || []).length ? it.cards.map((c) => `<div class="card-row"><span class="chip ${c.status === 'available' ? 'green' : c.status === 'used' ? 'gray' : 'red'}">${c.status === 'available' ? '可用' : c.status === 'used' ? '已用' : '停用'}</span><span class="mono grow">${esc((c.content || '').slice(0, 60))}</span><span class="tiny muted">${esc(c.note || '')}</span></div>`).join('') : '<div class="muted tiny">还没有卡券。虚拟商品没有卡券时不会自动发货。</div>'}</div>
            <div class="flex mt8"><input class="input" id="cardContent" placeholder="粘贴一张卡券 / 网盘链接…" /><button class="btn sm primary" id="cardAdd">添加</button></div>` : ''}
          ${it.card_content ? `<div class="divider"></div><div class="section-title">兜底卡券内容</div><div class="pre" style="font-size:11px;color:var(--muted);background:var(--surface-2);padding:10px;border-radius:9px">${esc(it.card_content)}</div>` : ''}
          <div class="divider"></div><div class="section-title">最近订单</div>${(it.orders || []).length ? it.orders.map((o) => `<div class="sys-row"><span>${esc(o.id)}</span><strong>${orderStatus(o.status)} ${money(o.amount_cents)}</strong></div>`).join('') : '<div class="muted tiny">暂无订单</div>'}`,
        footer: `<button class="btn" id="itemModalClose">关闭</button>`,
      });
      $('#itemModalClose').onclick = closeModal;
      const bind = $('#bindPlatformBtn');
      if (bind) bind.onclick = async () => {
        const value = $('#bindPlatformId').value.trim();
        if (!value) { toast('请输入平台商品 ID', 'error'); return; }
        try { await api(`/items/${id}/platform`, { method: 'POST', body: { platform_item_id: value } }); toast('平台商品 ID 已绑定'); closeModal(); await openItemDetail(id); await loadCatalog(); } catch (e) { toast(e.message, 'error'); }
      };
      const mv = $('#makeVirtualBtn');
      if (mv) mv.onclick = async () => {
        try { await api(`/items/${id}`, { method: 'PATCH', body: { delivery_mode: 'virtual', stock: 999 } }); toast('已设为虚拟自动发货，请补卡券'); closeModal(); await openItemDetail(id); await loadCatalog(); } catch (e) { toast(e.message, 'error'); }
      };
      const pub = $('#publishItemBtn');
      if (pub) pub.onclick = () => { closeModal(); openPublishModal(id); };
      const off = $('#offlineItemBtn');
      if (off) off.onclick = async () => {
        if (!(await confirmAction({ title: '下架商品', message: '会调用原生 batch.offline，知识库打墓碑。', confirmText: '下架', danger: true }))) return;
        try { await api(`/items/${id}/offline`, { method: 'POST' }); toast('已下架'); closeModal(); await loadCatalog(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
      };
      const price = $('#priceItemBtn');
      if (price) price.onclick = () => { closeModal(); openPriceModal(id, it); };
      const relist = $('#relistItemBtn');
      if (relist) relist.onclick = async () => {
        if (!(await confirmAction({ title: '重新上架', message: '会按保存的图片/分类/地址重新发布一条新商品；旧的下架商品仍在闲鱼后台。', confirmText: '重新上架' }))) return;
        try { await api(`/items/${id}/relist`, { method: 'POST' }); toast('已重新上架'); closeModal(); await loadCatalog(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
      };
      const add = $('#cardAdd');
      if (add) add.onclick = async () => {
        const content = $('#cardContent').value.trim();
        if (!content) { toast('请输入卡券内容', 'error'); return; }
        try { await api(`/items/${id}/cards`, { method: 'POST', body: { content, note: '手动添加' } }); toast('卡券已入库'); closeModal(); await openItemDetail(id); await loadCatalog(); } catch (e) { toast(e.message, 'error'); }
      };
    } catch (e) { toast(e.message, 'error'); }
  }

  function openCreateItemModal() {
    openModal({
      title: '新增商品（本地草稿）', wide: true,
      body: `<div class="form-grid">
        <div class="field"><label>标题</label><input class="input" id="niTitle" placeholder="商品标题" /></div>
        <div class="field"><label>售价（元）</label><input class="input" id="niPrice" type="number" min="0.01" step="0.01" /></div>
        <div class="field"><label>类型</label><select class="input" id="niType"><option value="physical">实物</option><option value="virtual">虚拟</option></select></div>
        <div class="field"><label>库存</label><input class="input" id="niStock" type="number" min="0" value="1" /></div>
        <div class="field" style="grid-column:1/-1"><label>描述</label><textarea class="input" id="niDesc" rows="4"></textarea></div>
      </div><div class="notice mt12">${icon('shield')} 仅创建本地草稿；点“发布上架”后才调用原生发布接口。</div>`,
      footer: `<button class="btn ghost" id="niCancel">取消</button><button class="btn primary" id="niSave">创建草稿</button>`,
    });
    $('#niCancel').onclick = closeModal;
    $('#niSave').onclick = async () => {
      const title = $('#niTitle').value.trim(); const price = Math.round(Number($('#niPrice').value) * 100);
      if (!title || !price) { toast('请填写标题和售价', 'error'); return; }
      try {
        const r = await api('/items', { method: 'POST', body: { title, description: $('#niDesc').value.trim(), price_cents: price, delivery_mode: $('#niType').value, stock: Number($('#niStock').value) || 0 } });
        closeModal(); await loadCatalog(); await openItemDetail(r.item.id);
      } catch (e) { toast(e.message, 'error'); }
    };
  }

  function openPublishModal(id) {
    openModal({
      title: '原生发布上架', wide: true,
      body: `<div class="notice mb12">${icon('alert')} 会真实上传图片并调用闲鱼发布接口；参数缺失会直接报错，不会假成功。</div>
        <div class="field"><label>商品图片 URL / 本地路径（每行一张）</label><textarea class="input" id="pubImages" rows="3" placeholder="https://.../1.jpg&#10;D:\\images\\2.jpg"></textarea></div>
        <div class="form-grid">
          <div class="field"><label>分类 cat_id</label><input class="input" id="pubCatId" placeholder="平台末级分类 ID" /></div>
          <div class="field"><label>分类名称</label><input class="input" id="pubCatName" placeholder="例如：虚拟资料" /></div>
          <div class="field"><label>频道分类 ID</label><input class="input" id="pubChannelId" /></div>
          <div class="field"><label>淘宝分类 ID</label><input class="input" id="pubTbId" /></div>
          <div class="field"><label>宝贝所在地关键词</label><input class="input" id="pubAddress" placeholder="例如：杭州市西湖区" /><div class="hint">不配 AMAP_KEY 时按城市内置坐标兜底。</div></div>
          <div class="field"><label>发布模式</label><select class="input" id="pubMode"><option value="personal">普通卖家</option><option value="shop">鱼小铺</option></select></div>
          <div class="field"><label>库存</label><input class="input" id="pubQty" type="number" min="0" value="1" /></div>
          <div class="field"><label>运费</label><select class="input" id="pubShip"><option value="free">包邮</option><option value="none">无需邮寄</option><option value="fixed">一口价</option></select></div>
        </div>`,
      footer: `<button class="btn ghost" id="pubCancel">取消</button><button class="btn primary" id="pubGo">上传并发布</button>`,
    });
    $('#pubCancel').onclick = closeModal;
    $('#pubGo').onclick = async () => {
      const images = $('#pubImages').value.split('\n').map((x) => x.trim()).filter(Boolean);
      if (!images.length) { toast('至少一张图片', 'error'); return; }
      const body = {
        images,
        category: { cat_id: $('#pubCatId').value.trim(), cat_name: $('#pubCatName').value.trim(), channel_cat_id: $('#pubChannelId').value.trim(), tb_cat_id: $('#pubTbId').value.trim() },
        address: $('#pubAddress').value.trim(),
        shipping_method: $('#pubShip').value,
        quantity: Number($('#pubQty').value) || 1,
        mode: $('#pubMode').value,
      };
      try { await api(`/items/${id}/publish`, { method: 'POST', body }); toast('发布成功'); closeModal(); await loadCatalog(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  function openPriceModal(id, it) {
    openModal({
      title: '原生改价',
      body: `<div class="muted mb12">${esc(it.title)}</div><div class="form-grid"><div class="field"><label>新售价（元）</label><input class="input" id="newPrice" type="number" min="0.01" step="0.01" value="${(it.price_cents / 100).toFixed(2)}" /></div><div class="field"><label>库存</label><input class="input" id="newStock" type="number" min="0" value="${it.stock || 0}" /></div></div><div class="notice warn mt12">${icon('alert')} 改价会直接调用卖家 info.update；失败会原样报错。</div>`,
      footer: `<button class="btn ghost" id="priceCancel">取消</button><button class="btn primary" id="priceGo">确认改价</button>`,
    });
    $('#priceCancel').onclick = closeModal;
    $('#priceGo').onclick = async () => {
      const price = Math.round(Number($('#newPrice').value) * 100);
      if (!price) { toast('请输入售价', 'error'); return; }
      try { await api(`/items/${id}/price`, { method: 'PATCH', body: { price_cents: price, stock: Number($('#newStock').value) || 0 } }); toast('改价成功'); closeModal(); await loadCatalog(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  function openFloorDialog(id) {
    const it = S.catalog.items.find((x) => x.id === id); if (!it) return;
    openModal({
      title: '调整议价底价',
      body: `<div class="muted mb12">${esc(it.title)}</div><div class="field"><label>底价（元）</label><input class="input" id="floorInput" type="number" min="0.01" step="0.01" value="${(it.floor_price_cents / 100).toFixed(2)}" /><div class="hint">底价是买家 Agent 议价时的硬约束，不会展示给买家。不能高于售价 ${esc(it.price_text)}。</div></div>`,
      footer: `<button class="btn ghost" id="floorCancel">取消</button><button class="btn primary" id="floorSave">保存</button>`,
    });
    $('#floorCancel').onclick = closeModal;
    $('#floorSave').onclick = async () => {
      const yuanValue = Number($('#floorInput').value);
      if (!yuanValue || yuanValue <= 0) { toast('请输入有效底价', 'error'); return; }
      try { await api(`/items/${id}/floor`, { method: 'POST', body: { floor_price_cents: Math.round(yuanValue * 100) } }); toast('底价已更新，知识库已同步'); closeModal(); await loadCatalog(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  // =========================================================
  // Orders
  // =========================================================
  async function pageOrders() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>订单流水与履约</h2><p>虚拟商品自动发货；实物回填单号后自动通知买家。</p></div>
        <div class="btn-row"><button class="btn soft" id="ordersRefresh">${icon('refresh')} 刷新</button></div>
      </div>
      <div class="order-stats" id="orderStats"></div>
      <div class="card pad">
        <div class="card-head"><div class="filter-bar" id="orderFilters">
          <button class="filter-pill active" data-status="all">全部</button>
          <button class="filter-pill" data-status="paid">待发货</button>
          <button class="filter-pill" data-status="refund_open">退款中</button>
          <button class="filter-pill" data-status="shipped">已发货</button>
          <button class="filter-pill" data-status="done">已完成</button>
        </div><span class="tiny muted" id="orderCount"></span></div>
        <div class="table-wrap" id="ordersTable"></div>
      </div>`;
    $('#ordersRefresh').onclick = () => loadOrders(true);
    $$('#orderFilters [data-status]').forEach((b) => { b.onclick = () => { S.orders.filter = b.dataset.status; $$('#orderFilters [data-status]').forEach((x) => x.classList.toggle('active', x === b)); renderOrders(); }; });
    await loadOrders(true);
    every(() => { if (!document.hidden) loadOrders(false).catch(() => {}); }, 12000);
  }

  async function loadOrders() {
    const orders = await api('/orders');
    S.orders.orders = orders || [];
    renderOrders();
  }

  function renderOrders() {
    const all = S.orders.orders;
    const stats = [
      ['待发货', all.filter((o) => o.status === 'paid').length, 'amber'],
      ['退款中', all.filter((o) => o.status === 'refund_open').length, 'red'],
      ['今日成交', all.filter((o) => new Date(o.paid_at || o.created_at).toDateString() === new Date().toDateString()).length, 'green'],
      ['累计 GMV', money(all.filter((o) => ['paid', 'shipped', 'delivered', 'done'].includes(o.status)).reduce((s, o) => s + Number(o.amount_cents || 0), 0)), 'blue'],
    ];
    $('#orderStats').innerHTML = stats.map(([label, value, tone]) => `<div class="order-stat"><small>${label}</small><strong style="color:${tone === 'red' ? 'var(--danger)' : tone === 'amber' ? 'var(--amber)' : tone === 'green' ? 'var(--brand)' : 'var(--ink)'}">${value}</strong></div>`).join('');
    const list = S.orders.filter === 'all' ? all : all.filter((o) => o.status === S.orders.filter);
    $('#orderCount').textContent = `${list.length} 条`;
    if (!list.length) { $('#ordersTable').innerHTML = emptyBlock('没有订单', S.orders.filter === 'all' ? '订单同步后显示在这里' : '当前筛选下没有订单', 'orders'); return; }
    $('#ordersTable').innerHTML = `<table class="table"><thead><tr><th>订单</th><th>商品</th><th>买家</th><th>金额</th><th>状态</th><th>物流 / 地址</th><th class="right">操作</th></tr></thead><tbody>${list.map((o) => `
      <tr>
        <td><div class="ord-id">${esc(o.id)}</div><div class="ord-sub">${esc(fmtTime(o.created_at, true))}</div></td>
        <td><div class="ord-title">${esc(o.title || '—')}</div><div class="ord-sub">${o.delivery_mode === 'virtual' ? '虚拟自动发货' : '实物待发货'}</div></td>
        <td><div>${esc(o.buyer_nick || o.buyer_id)}</div><div class="ord-sub">${esc(o.buyer_id)}</div></td>
        <td class="ord-amount">${money(o.amount_cents)}</td>
        <td>${orderStatus(o.status)}</td>
        <td><div class="ord-sub">${o.tracking_no ? `${esc(o.tracking_company || '')} ${esc(o.tracking_no)}` : (o.address ? esc(o.address) : '—')}</div></td>
        <td><div class="ord-actions">
          <button class="btn xs ghost" data-order-detail="${esc(o.id)}">详情</button>
          ${o.status === 'paid' && o.delivery_mode === 'physical' ? `<button class="btn xs primary" data-ship="${esc(o.id)}">填单号</button>` : ''}
          ${o.status === 'refund_open' ? `<button class="btn xs amber" data-refund="${esc(o.id)}">处理退款</button>` : ''}
          ${['shipped', 'delivered'].includes(o.status) ? `<button class="btn xs soft" data-complete="${esc(o.id)}">完成</button>` : ''}
          ${o.delivery_mode === 'virtual' && ['shipped', 'delivered', 'done'].includes(o.status) ? `<button class="btn xs ghost" data-resend="${esc(o.id)}">补发</button>` : ''}
          ${o.status === 'paid' && o.delivery_mode === 'virtual' ? `<span class="tiny muted">自动发货中</span>` : ''}
        </div></td>
      </tr>`).join('')}</tbody></table>`;
    $$('[data-order-detail]').forEach((b) => b.onclick = () => openOrderDetail(b.dataset.orderDetail));
    $$('[data-ship]').forEach((b) => b.onclick = () => openShipDialog(b.dataset.ship));
    $$('[data-refund]').forEach((b) => b.onclick = () => openRefundDialog(b.dataset.refund));
    $$('[data-resend]').forEach((b) => b.onclick = () => resendOrder(b.dataset.resend));
    $$('[data-complete]').forEach((b) => b.onclick = async () => { if (!(await confirmAction({ title: '完成订单', message: '将订单标记为已完成。', confirmText: '完成' }))) return; try { await api(`/orders/${b.dataset.complete}/complete`, { method: 'POST' }); toast('订单已完成'); await loadOrders(); } catch (e) { toast(e.message, 'error'); } });
  }

  async function resendOrder(id) {
    if (!(await confirmAction({ title: '补发卡券', message: '会复用订单原卡券或从库存取一张新卡，立即发送给买家。', confirmText: '补发' }))) return;
    try { await api(`/orders/${id}/resend`, { method: 'POST' }); toast('已补发'); await loadOrders(); } catch (e) { toast(e.message, 'error'); }
  }

  async function openOrderDetail(orderId) {
    try {
      const d = await api(`/orders/${orderId}`);
      const o = d.order; const it = d.item || {}; const b = d.buyer || {};
      const attempts = d.delivery_attempts || [];
      openModal({
        title: '订单详情', wide: true,
        body: `<div class="flex-between mb12"><div><h3 style="margin:0;font-size:16px">${esc(it.title || '')}</h3><div class="muted tiny">${esc(o.id)} · ${esc(fmtTime(o.created_at, true))}</div></div><div class="right">${orderStatus(o.status)}<div class="ord-amount" style="font-size:20px;margin-top:3px">${money(o.amount_cents)}</div></div></div>
          <div class="grid-3"><div class="kv-box"><small>买家</small><strong>${esc(b.nick || o.buyer_id)}</strong></div><div class="kv-box"><small>下单数量</small><strong>${o.quantity || 1}</strong></div><div class="kv-box"><small>支付时间</small><strong>${esc(fmtTime(o.paid_at, true))}</strong></div></div>
          <div class="grid-2 mt12"><div class="kv-box"><small>收货地址</small><strong>${esc(o.address || '—')}</strong></div><div class="kv-box"><small>物流</small><strong>${esc(o.tracking_company || '—')} ${esc(o.tracking_no || '')}</strong></div></div>
          ${o.refund_reason ? `<div class="notice warn mt12">${icon('alert')} 退款原因：${esc(o.refund_reason)} ${o.refund_note ? '· ' + esc(o.refund_note) : ''}</div>` : ''}
          ${o.reviewed_at ? `<div class="notice mt12">${icon('check')} 已评价：${esc(o.reviewed_text || '')} · ${esc(fmtTime(o.reviewed_at, true))}</div>` : ''}
          <div class="divider"></div><div class="section-title">发货尝试</div>
          ${attempts.length ? attempts.map((a) => `<div class="sys-row"><span>${esc(fmtTime(a.created_at, true))} · ${esc(a.status)}</span><strong>${esc((a.content_snippet || '').slice(0, 60))} ${a.error ? '· ' + esc(a.error) : ''}</strong></div>`).join('') : '<div class="muted tiny">暂无发货尝试</div>'}
          <div class="divider"></div><div class="section-title">订单事件</div>
          ${(d.events || []).slice(0, 8).map((e) => `<div class="sys-row"><span class="mono">${esc(e.topic)}</span><strong>${esc(e.status)}</strong></div>`).join('') || '<div class="muted tiny">暂无事件</div>'}
          <div class="divider"></div><div class="section-title">审计</div>
          ${(d.audits || []).slice(0, 6).map((a) => `<div class="sys-row"><span>${esc(a.actor)} · ${esc(a.action)}</span><strong>${esc(a.result)}</strong></div>`).join('') || '<div class="muted tiny">暂无审计</div>'}`,
        footer: `<div class="btn-row" style="margin-right:auto">
          ${o.status === 'paid' && it.delivery_mode === 'physical' ? `<button class="btn sm primary" id="odShip">填单号</button>` : ''}
          ${o.status === 'refund_open' ? `<button class="btn sm amber" id="odRefund">处理退款</button>` : ''}
          ${o.status === 'paid' && it.delivery_mode === 'virtual' ? `<button class="btn sm soft" id="odResend">补发卡券</button>` : ''}
          ${it.delivery_mode === 'virtual' && ['shipped', 'delivered', 'done'].includes(o.status) ? `<button class="btn sm ghost" id="odResend">补发卡券</button>` : ''}
          ${['shipped', 'delivered'].includes(o.status) ? `<button class="btn sm soft" id="odComplete">完成订单</button>` : ''}
          ${o.status === 'done' && !o.reviewed_at ? `<button class="btn sm ghost" id="odReview">自动评价</button>` : ''}
        </div><button class="btn" id="odClose">关闭</button>`,
      });
      $('#odClose').onclick = closeModal;
      const ship = $('#odShip'); if (ship) ship.onclick = () => { closeModal(); openShipDialog(orderId); };
      const refund = $('#odRefund'); if (refund) refund.onclick = () => { closeModal(); openRefundDialog(orderId); };
      const resend = $('#odResend'); if (resend) resend.onclick = () => { closeModal(); resendOrder(orderId); };
      const complete = $('#odComplete'); if (complete) complete.onclick = async () => { try { await api(`/orders/${orderId}/complete`, { method: 'POST' }); toast('订单已完成'); closeModal(); await loadOrders(); } catch (e) { toast(e.message, 'error'); } };
      const review = $('#odReview'); if (review) review.onclick = async () => { try { await api(`/orders/${orderId}/review`, { method: 'POST', body: { text: '交易愉快，感谢信任～' } }); toast('已自动评价'); closeModal(); await loadOrders(); } catch (e) { toast(e.message, 'error'); } };
    } catch (e) { toast(e.message, 'error'); }
  }

  function openShipDialog(orderId) {
    const o = S.orders.orders.find((x) => x.id === orderId);
    openModal({
      title: '回填快递单号',
      body: `<div class="muted mb12">${esc(o ? o.title : '')} · ${esc(o ? o.buyer_nick || o.buyer_id : '')}</div>
        <div class="form-grid"><div class="field"><label>快递公司</label><select class="input" id="shipCompany"><option>顺丰</option><option>中通</option><option>圆通</option><option>韵达</option><option>申通</option><option>京东</option><option>极兔</option><option>邮政</option><option>德邦</option><option>其他</option></select></div><div class="field"><label>快递单号</label><input class="input" id="shipNo" placeholder="例如 SF1234567890" /></div></div>
        <div class="notice mt12">${icon('send')} 保存后订单变为「已发货」，并自动给买家发一条含物流信息的消息。</div>`,
      footer: `<button class="btn ghost" id="shipCancel">取消</button><button class="btn primary" id="shipSave">确认发货</button>`,
    });
    $('#shipCancel').onclick = closeModal;
    $('#shipSave').onclick = async () => {
      const company = $('#shipCompany').value; const no = $('#shipNo').value.trim();
      if (!no) { toast('请填写快递单号', 'error'); return; }
      try { await api(`/orders/${orderId}/ship`, { method: 'POST', body: { company, tracking_no: no } }); toast('已发货并通知买家'); closeModal(); await loadOrders(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  function openRefundDialog(orderId) {
    const o = S.orders.orders.find((x) => x.id === orderId);
    openModal({
      title: '处理退款申请',
      body: `<div class="muted mb12">${esc(o ? o.title : '')} · ${money(o ? o.amount_cents : 0)}</div><div class="notice warn mb12">${icon('alert')} 退款原因：${esc(o && o.refund_reason ? o.refund_reason : '买家未填写')}</div>
        <div class="field"><label>处理方式</label><select class="input" id="refundApprove"><option value="1">同意退款</option><option value="0">拒绝退款（转协商）</option></select></div>
        <div class="field mt12"><label>备注</label><input class="input" id="refundNote" placeholder="给买家的处理说明（可选）" /></div>`,
      footer: `<button class="btn ghost" id="refundCancel">取消</button><button class="btn primary" id="refundSave">提交处理</button>`,
    });
    $('#refundCancel').onclick = closeModal;
    $('#refundSave').onclick = async () => {
      try { await api(`/orders/${orderId}/refund`, { method: 'POST', body: { approve: $('#refundApprove').value === '1', note: $('#refundNote').value.trim() } }); toast('退款处理完成，已通知买家'); closeModal(); await loadOrders(); await refreshGlobal(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  // =========================================================
  // Ops / replay / eval
  // =========================================================
  async function pageOps() {
    $('#view').innerHTML = `<div class="loading-page"><span class="spinner"></span> 读取指标与轨迹…</div>`;
    const [metrics, events, sessions, runs] = await Promise.all([
      api('/metrics'), api('/events?limit=60'), api('/replay/sessions?limit=30'), api('/eval/runs?limit=10'),
    ]);
    S.ops.metrics = metrics; S.ops.events = events || []; S.ops.sessions = sessions || []; S.ops.runs = runs || [];
    if (!S.ops.sessionId && S.ops.sessions[0]) S.ops.sessionId = S.ops.sessions[0].id;
    if (S.ops.sessionId) S.ops.trace = await api(`/replay/${S.ops.sessionId}`).catch(() => null);
    S.ops.lastEval = (S.ops.runs[0] && S.ops.runs[0].detail ? S.ops.runs[0] : null) || S.ops.lastEval;
    renderOps();
    every(async () => {
      if (document.hidden || S.route !== 'ops') return;
      try {
        const [m, e] = await Promise.all([api('/metrics'), api('/events?limit=60')]);
        S.ops.metrics = m; S.ops.events = e || [];
        if (S.ops.tab === 'events' || S.ops.tab === 'overview') renderOps();
      } catch (err) { /* noop */ }
    }, 12000);
  }

  function renderOps() {
    const m = S.ops.metrics || {}; const t = m.today || {}; const h = m.health || {};
    const series = m.series || [];
    const maxBar = Math.max(1, ...series.map((d) => Math.max(d.conversations || 0, d.orders || 0)));
    const chart = `<div class="bars">${series.map((d) => `<div class="bar-col" title="${esc(d.date)}"><div class="bar-pair"><div class="bar green" style="height:${Math.max(3, (d.conversations / maxBar) * 100)}%"></div><div class="bar coral" style="height:${Math.max(2, (d.orders / maxBar) * 100)}%"></div></div><span class="bar-label">${esc(d.label)}</span></div>`).join('')}</div>`;
    const view = $('#view');
    view.innerHTML = `
      <div class="page-head"><div><h2>指标、轨迹与回归</h2><p>L0 系统活着吗 · L1 客服称职吗 · L2 生意变好了吗。北极星：询单转化率。</p></div><div class="btn-row"><button class="btn sm ghost" id="opsRefresh">${icon('refresh')} 刷新</button></div></div>
      <div class="ops-metrics">
        ${metricCard('L0 · 通道', (S.system && S.system.channel && S.system.channel.online) ? '在线' : '离线', `事件积压 ${S.system?.events?.backlog ?? 0} · 队列 ${S.system?.queue?.depth ?? 0}`, 'activity', '')}
        ${metricCard('L0 · 工具错误率', `${h.tool_error_rate || 0}%`, `${h.tool_calls || 0} 次调用 / 24h`, 'plug', 'amber')}
        ${metricCard('L1 · 首响 P95', `${t.first_response_p95 || 0}s`, `P50 ${t.first_response_p50 || 0}s · 回复率 ${t.answer_rate || 0}%`, 'clock', 'coral')}
        ${metricCard('L2 · 询单转化', `${t.conversion_rate || 0}%`, `${t.paid_orders || 0} 单 · GMV ${money(t.gmv || 0)}`, 'spark', 'purple')}
      </div>
      <div class="overview-grid">
        <div class="card chart-card"><div class="card-head"><div><div class="card-title">${icon('activity')} 7 日趋势</div><div class="card-sub">会话 vs 成交 · 单位：个</div></div><div class="legend"><span><i class="g"></i>咨询</span><span><i class="c"></i>成交</span></div></div>${chart}</div>
        <div class="card pad"><div class="card-head"><div><div class="card-title">${icon('shield')} 运行健康</div><div class="card-sub">进程内服务与护栏</div></div></div>
          <div class="sys-row"><span>账号在线</span><strong>${(S.system && S.system.channel && S.system.channel.online) ? '在线' : '离线'}</strong></div>
          <div class="sys-row"><span>LLM 模式</span><strong>${esc(S.system?.llm?.mode || '—')}</strong></div>
          <div class="sys-row"><span>工具错误率</span><strong>${h.tool_error_rate || 0}%</strong></div>
          <div class="sys-row"><span>LLM 失败率</span><strong>${h.llm_fail_rate || 0}%</strong></div>
          <div class="sys-row"><span>事件积压</span><strong>${S.system?.events?.backlog ?? 0}</strong></div>
          <div class="sys-row"><span>outbox 待发</span><strong>${S.system?.outbox?.pending ?? 0}</strong></div>
          <div class="sys-row"><span>知识 chunks</span><strong>${S.system?.knowledge?.chunks ?? 0}</strong></div>
          <div class="sys-row"><span>运行时长</span><strong>${Math.floor((S.system?.uptime_seconds || 0) / 60)} 分钟</strong></div>
        </div>
      </div>
      <div class="ops-tabs">
        <div class="tabs"><button class="tab ${S.ops.tab === 'events' ? 'active' : ''}" data-ops-tab="events">事件流</button><button class="tab ${S.ops.tab === 'replay' ? 'active' : ''}" data-ops-tab="replay">会话回放</button><button class="tab ${S.ops.tab === 'eval' ? 'active' : ''}" data-ops-tab="eval">黄金集评测</button></div>
        <span class="tiny muted">session_id 全链路贯穿：消息 → 网关 → Agent → 工具 → 回复</span>
      </div>
      <div id="opsPanel"></div>`;
    $('#opsRefresh').onclick = () => pageOps();
    $$('[data-ops-tab]').forEach((b) => b.onclick = () => { S.ops.tab = b.dataset.opsTab; renderOpsPanel(); $$('[data-ops-tab]').forEach((x) => x.classList.toggle('active', x === b)); });
    renderOpsPanel();
  }

  function renderOpsPanel() {
    const panel = $('#opsPanel'); if (!panel) return;
    if (S.ops.tab === 'replay') { renderReplayPanel(); return; }
    if (S.ops.tab === 'eval') { renderEvalPanel(); return; }
    panel.innerHTML = `<div class="card pad"><div class="card-head"><div><div class="card-title">${icon('activity')} 事件流</div><div class="card-sub">最近 ${S.ops.events.length} 条 · 失败会生成 P1 告警</div></div><button class="btn xs ghost" id="eventsRefresh">${icon('refresh')}</button></div><div class="event-table">${S.ops.events.map((e) => `<div class="event-row"><span class="event-topic" title="${esc(e.topic)}">${esc(e.topic)}</span><span class="event-payload">${esc(compactPayload(e.payload))}</span><span class="chip ${e.status === 'done' ? 'green' : e.status === 'failed' ? 'red' : 'amber'}">${esc(e.status)}</span><span class="event-time">${esc(e.created_human || '')}</span></div>`).join('') || emptyBlock('暂无事件', '', 'activity')}</div></div>`;
    $('#eventsRefresh').onclick = async () => { S.ops.events = await api('/events?limit=60'); renderOpsPanel(); };
  }

  async function renderReplayPanel() {
    const panel = $('#opsPanel'); if (!panel) return;
    panel.innerHTML = `<div class="card pad"><div class="replay-layout"><div class="replay-sessions">${S.ops.sessions.map((s) => `<div class="rs-item ${s.id === S.ops.sessionId ? 'active' : ''}" data-session="${esc(s.id)}"><strong>${esc(s.buyer_nick || '买家')} · ${esc(s.item_title || '—')}</strong><small>${esc(s.last_at_human || '')} · ${s.message_count || 0} 消息 / ${s.turn_count || 0} 轮</small></div>`).join('') || emptyBlock('暂无会话', '', 'chat')}</div><div class="replay-trace" id="replayTrace">${renderTraceHtml()}</div></div></div>`;
    panel.querySelectorAll('[data-session]').forEach((el) => { el.onclick = async () => { S.ops.sessionId = el.dataset.session; S.ops.trace = await api(`/replay/${S.ops.sessionId}`); renderReplayPanel(); }; });
    const exportBtn = $('#exportTrace'); if (exportBtn) exportBtn.onclick = () => downloadTrace();
  }

  function renderTraceHtml() {
    const t = S.ops.trace;
    if (!t) return emptyBlock('选择一个会话', '左侧列表来自真实消息与 turns', 'activity');
    const conv = t.conversation || {}; const item = t.item; const buyer = t.buyer;
    return `<div class="flex-between mb12"><div><strong style="font-size:13px">${esc(buyer?.nick || '买家')} · ${esc(item?.title || '无商品')}</strong><div class="tiny muted">${esc(conv.session_id || '')} · 创建 ${esc(fmtTime(conv.created_at, true))}</div></div><button class="btn xs ghost" id="exportTrace">${icon('download')} 导出轨迹</button></div><div class="replay-timeline">${(t.timeline || []).map((x) => `<div class="rt-item ${esc(x.type)}"><div class="rt-head"><strong>${esc(x.title)}</strong><time>${esc(fmtTime(x.ts))}</time></div><div class="rt-text">${nl2br(String(x.text || '').slice(0, 600))}</div>${x.type === 'tool' || x.type === 'event' ? `<div class="rt-json">${esc(compactPayload(x.meta))}</div>` : ''}</div>`).join('')}</div>`;
  }

  function downloadTrace() {
    const blob = new Blob([JSON.stringify(S.ops.trace, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = `yuxiaoer-replay-${S.ops.sessionId}.json`; a.click(); URL.revokeObjectURL(url);
  }

  function renderEvalPanel() {
    const panel = $('#opsPanel'); if (!panel) return;
    const last = S.ops.lastEval || (S.ops.runs[0] && S.ops.runs[0].detail ? S.ops.runs[0] : null);
    const detail = last ? (last.detail || []) : [];
    const total = last ? last.total : (detail.length || 0);
    const score = last ? Number(last.score || 0) : 0;
    const failed = detail.filter((d) => !d.passed);
    const llm = (S.system && S.system.llm) || {};
    panel.innerHTML = `<div class="card pad">
      <div class="eval-hero"><div class="eval-score" style="--pct:${score}"><span>${score}</span></div><div class="grow"><div class="card-title">${icon('spark')} 黄金问答集</div><div class="muted tiny mt8">${last ? `最近运行 ${esc(fmtTime(last.finished_at || last.started_at, true))} · 判分 ${esc(last.judge_mode || 'rules')}` : '还没有运行过。50 条真实场景 + 期望动作 + 必含词 + 红线。'}</div><div class="flex mt12"><button class="btn primary" id="runEvalBtn">${icon('play')} 运行黄金集（50 条）</button><span class="tiny muted">${llm.enabled ? '可启用 LLM-as-judge' : '当前规则判分；配置 LLM 后可启用 judge'}</span></div></div><div class="right"><div class="kv-box"><small>通过</small><strong>${last ? last.passed : 0} / ${total || 50}</strong></div><div class="kv-box mt8"><small>红线失败</small><strong style="color:${last && last.redline_failures ? 'var(--danger)' : 'var(--ink)'}">${last ? last.redline_failures : 0}</strong></div></div></div>
      <div class="divider"></div>
      ${last ? `<div class="grid-4 mb12"><div class="kv-box"><small>意图匹配</small><strong>${detail.filter((d) => d.checks.category).length} / ${detail.length}</strong></div><div class="kv-box"><small>动作匹配</small><strong>${detail.filter((d) => d.checks.action).length} / ${detail.length}</strong></div><div class="kv-box"><small>必含词</small><strong>${detail.filter((d) => d.checks.must_include).length} / ${detail.length}</strong></div><div class="kv-box"><small>红线</small><strong>${detail.filter((d) => d.checks.redline).length} / ${detail.length}</strong></div></div>
      ${failed.length ? `<div class="notice red mb12">${icon('alert')} 有 ${failed.length} 条未通过：${failed.slice(0, 5).map((d) => esc(d.input)).join('、')}${failed.length > 5 ? '…' : ''}</div>` : `<div class="notice mb12">${icon('check')} 全部通过。回归红线：转人工率不升、违规词为 0。</div>`}
      <div style="max-height:420px;overflow:auto">${detail.map((d) => `<div class="eval-row"><div class="er-top">${d.passed ? chip('通过', 'green') : chip('失败', 'red')}<span class="er-input">${esc(d.input)}</span><span class="type-tag">${esc(CATEGORY_LABEL[d.actual_category] || d.actual_category)}</span><span class="type-tag">${esc(d.actual_action)}</span></div><div class="er-reply">${esc(d.reply || '（静默）')}</div><div class="eval-checks mt8">${Object.entries(d.checks || {}).map(([k, v]) => `<span class="eval-check ${v ? '' : 'bad'}">${esc(k)}</span>`).join('')}</div></div>`).join('')}</div>` : `<div class="empty"><div class="empty-ico">${icon('spark')}</div><strong>让回归成为习惯</strong>修改 prompt / 换模型前，先跑一遍黄金集。</div>`}
    </div>`;
    const runBtn = $('#runEvalBtn'); if (runBtn) runBtn.onclick = runEval;
  }

  async function runEval() {
    const btn = $('#runEvalBtn'); if (!btn || S.ops.busy) return;
    S.ops.busy = true; btn.disabled = true; btn.innerHTML = `<span class="spinner" style="width:13px;height:13px;border-width:2px"></span> 运行中…`;
    try {
      const llm = (S.system && S.system.llm) || {};
      const result = await api('/eval/run', { method: 'POST', body: { judge_mode: llm.enabled ? 'llm' : 'rules' } });
      S.ops.lastEval = result;
      S.ops.runs.unshift(result);
      toast(`评测完成：${result.passed}/${result.total}，得分 ${result.score}`);
      renderEvalPanel();
    } catch (e) { toast(e.message, 'error'); } finally { S.ops.busy = false; if ($('#runEvalBtn')) { $('#runEvalBtn').disabled = false; } }
  }

  // =========================================================
  // Accounts / session keeper / risk
  // =========================================================
  async function pageAccounts() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>账号、会话与反检测</h2><p>扫码登录 → Cookie 保活 → token 随机刷新 → 风控熔断。多账号之间随机错开。</p></div>
        <div class="btn-row">
          <button class="btn" id="addAccount">${icon('user')} 添加账号</button>
          <button class="btn soft" id="accountsRefresh">${icon('refresh')} 刷新</button>
        </div>
      </div>
      <div id="accountsMain"><div class="loading-page"><span class="spinner"></span> 读取账号状态…</div></div>`;
    $('#addAccount').onclick = openAddAccount;
    $('#accountsRefresh').onclick = () => loadAccounts(true);
    await loadAccounts(true);
    every(() => { if (!document.hidden && S.route === 'accounts') loadAccounts(false).catch(() => {}); }, 12000);
  }

  async function loadAccounts(scroll = false) {
    const [list, risk] = await Promise.all([api('/accounts'), api('/risk')]);
    S.accounts.list = list || [];
    S.accounts.risk = risk.status || null;
    S.accounts.keeper = risk.keeper || null;
    if (!S.accounts.selected || !S.accounts.list.some((a) => a.id === S.accounts.selected)) {
      const active = S.accounts.list.find((a) => a.is_active) || S.accounts.list[0];
      S.accounts.selected = active ? active.id : null;
    }
    if (S.accounts.selected) {
      S.accounts.events = await api(`/accounts/${S.accounts.selected}/events`).catch(() => []);
    }
    renderAccounts();
  }

  function renderAccounts() {
    const el = $('#accountsMain'); if (!el) return;
    const risk = S.accounts.risk || {};
    const keeper = S.accounts.keeper || {};
    const list = S.accounts.list || [];
    const selected = S.accounts.selected;
    el.innerHTML = `
      <div class="account-layout">
        <div class="stack">
          <div class="account-grid">
            ${list.map((a) => renderAccountCard(a, selected)).join('') || emptyBlock('还没有账号', '点右上角添加账号', 'user')}
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('activity')} 账号事件</div><div class="card-sub">登录 / 扫码 / 刷新 / 接手 / 熔断</div></div>${chip((list.find((a) => a.id === selected) || {}).nickname || '选择账号', 'line')}</div>
            <div class="account-events">
              ${(S.accounts.events || []).length ? S.accounts.events.map((e) => `<div class="acc-event"><span class="ae-dot"></span><div class="ae-main"><strong>${esc(ACC_EVENT_LABEL[e.event] || e.event)}</strong><small>${esc(e.when)} · ${esc(compactPayload(e.detail))}</small></div></div>`).join('') : '<div class="muted tiny">还没有事件。</div>'}
            </div>
          </div>
        </div>
        <div class="stack">
          <div class="card pad risk-card ${risk.open ? 'risk-open' : ''}">
            <div class="card-head"><div><div class="card-title">${icon('shield')} 风控熔断</div><div class="card-sub">平台写动作 fail-fast，不带病重试</div></div>${risk.open ? chip('熔断中', 'red') : chip('正常', 'green')}</div>
            <div class="risk-hero">
              <div class="risk-orb ${risk.open ? 'on' : ''}">${icon(risk.open ? 'alert' : 'shield')}</div>
              <div><div class="risk-state">${risk.open ? '写操作已暂停' : '通道写操作正常'}</div><div class="muted tiny">${risk.open ? `至 ${esc(risk.until_human)} · ${esc(risk.reason)}` : '串行队列 + 抖动 + 指数退避正在生效'}</div></div>
            </div>
            <div class="risk-grid">
              <div class="kv-box"><small>写间隔</small><strong>${esc(risk.write_interval_seconds || 0)}s</strong></div>
              <div class="kv-box"><small>随机抖动</small><strong>${esc(risk.write_jitter_seconds || 0)}s</strong></div>
              <div class="kv-box"><small>账号错开</small><strong>${(risk.account_stagger_seconds || [2,5]).join('–')}s</strong></div>
              <div class="kv-box"><small>H5 刷新</small><strong>${(risk.refresh_jitter_hours || [1.5,2.5]).join('–')}h</strong></div>
              <div class="kv-box"><small>WS 刷新</small><strong>${(risk.ws_refresh_hours || [10,14]).join('–')}h</strong></div>
              <div class="kv-box"><small>人工输入延迟</small><strong>${risk.human_typing ? '开' : '关'}</strong></div>
            </div>
            <div class="btn-row mt12">
              <button class="btn sm soft" data-risk-reset ${risk.open ? '' : 'disabled'}>解除熔断</button>
              <button class="btn sm ghost" data-acc-tick>${icon('refresh')} 立即保活</button>
            </div>
            <div class="divider"></div>
            <div class="section-title">刷新纪律</div>
            <div class="turn-mini">
              <div class="kv"><span>Cookie / hasLogin</span><strong>每 ${esc(keeper.cookie_check_minutes || 30)} 分钟 ± 抖动</strong></div>
              <div class="kv"><span>H5 token</span><strong>${(keeper.h5_refresh_hours || [1.5,2.5]).join('–')} 小时随机</strong></div>
              <div class="kv"><span>WebSocket token</span><strong>${(keeper.ws_refresh_hours || [10,14]).join('–')} 小时随机</strong></div>
              <div class="kv"><span>上次保活</span><strong>${esc(keeper.last_tick_human || '—')}</strong></div>
            </div>
            <div class="notice mt12">${icon('alert')} 触发条件：${(risk.signals || []).slice(0, 8).map(esc).join(' / ')}。</div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('plug')} 协议事实（只实现事实，不复制源码）</div><div class="card-sub">来自 OPEN-SOURCE-XIANYU-APIs 与 REFERENCE-MAP</div></div></div>
            <div class="turn-mini">
              <div class="kv"><span>消息长连接</span><strong>wss-goofish.dingtalk.com</strong></div>
              <div class="kv"><span>登录态</span><strong>accessToken 24h + refreshToken</strong></div>
              <div class="kv"><span>账号错开</span><strong>多账号刷新 2–5s 错峰</strong></div>
              <div class="kv"><span>当前通道</span><strong>${esc(S.system?.channel?.label || '原生闲鱼协议')}</strong></div>
            </div>
            <div class="notice warn mt12">${icon('shield')} 原生扫码/WS/订单同步已接入；发布/改价/擦亮仍以平台实际结果为准，不做假成功。</div>
          </div>
        </div>
      </div>`;
    el.querySelectorAll('[data-acc-select]').forEach((b) => { b.onclick = () => { S.accounts.selected = b.dataset.accSelect; loadAccounts().catch(() => {}); }; });
    el.querySelectorAll('[data-acc-login]').forEach((b) => { b.onclick = () => openLoginModal(b.dataset.accLogin); });
    el.querySelectorAll('[data-acc-refresh]').forEach((b) => { b.onclick = () => accountAction(b.dataset.accRefresh, 'refresh'); });
    el.querySelectorAll('[data-acc-sync]').forEach((b) => { b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await api(`/accounts/${b.dataset.accSync}/sync`, { method: 'POST' });
        if (r.ok === false) throw new Error(r.error || '同步失败');
        const seen = r.items?.seen ?? 0; const created = r.items?.created ?? 0; const updated = r.items?.updated ?? 0;
        toast(`同步完成：在售 ${seen} 件，新增 ${created}，更新 ${updated}`);
        await loadAccounts(); await refreshGlobal();
      } catch (e) { toast(e.message, 'error'); } finally { b.disabled = false; }
    }; });
    el.querySelectorAll('[data-acc-activate]').forEach((b) => { b.onclick = () => accountAction(b.dataset.accActivate, 'activate'); });
    el.querySelectorAll('[data-acc-logout]').forEach((b) => { b.onclick = async () => { if (await confirmAction({ title: '退出登录', message: '会清除该账号的 Cookie/Token；已登录的其他账号会被自动激活。', confirmText: '退出' })) accountAction(b.dataset.accLogout, 'logout'); }; });
    el.querySelectorAll('[data-risk-reset]').forEach((b) => { b.onclick = async () => { try { await api('/risk/reset', { method: 'POST' }); toast('熔断已解除'); await refreshGlobal(); await loadAccounts(); } catch (e) { toast(e.message, 'error'); } }; });
    el.querySelectorAll('[data-acc-tick]').forEach((b) => { b.onclick = async () => { try { const r = await api('/accounts/tick', { method: 'POST' }); toast(`保活完成：刷新 ${r.result.refreshed.length} 个账号`); await loadAccounts(); } catch (e) { toast(e.message, 'error'); } }; });
  }

  function renderAccountCard(a, selected) {
    const stateCls = a.session_state === 'authenticated' ? 'green' : a.session_state === 'expiring' ? 'amber' : a.session_state === 'expired' ? 'red' : a.session_state === 'logged_out' ? 'gray' : 'purple';
    return `<div class="card account-card ${a.is_active ? 'active' : ''} ${selected === a.id ? 'selected' : ''}" data-acc-select="${esc(a.id)}">
      <div class="acc-top"><span class="acc-avatar">${esc((a.nickname || '鱼').slice(0, 1))}</span><div class="grow"><strong>${esc(a.nickname)} ${a.is_active ? chip('当前账号', 'green') : ''}</strong><small>${esc(a.platform)} · ${esc(a.state_label)}</small></div>${chip(a.state_label, stateCls)}</div>
      <div class="acc-token"><span class="mono">unb ${esc(a.platform_user_id || '—')}</span><small>${a.has_cookie ? 'Cookie 已同步' : '无 Cookie'} · WS ${esc(a.ws_state || 'disconnected')}</small></div>
      ${a.detail ? `<div class="tiny muted mt6">${esc(a.detail)}</div>` : ''}
      <div class="acc-expiry">
        <div><small>access</small><strong>${esc(a.access_expires_human || '—')}</strong></div>
        <div><small>ws_token</small><strong>${esc(a.ws_expires_human || '—')}</strong></div>
        <div><small>下次刷新</small><strong>${esc(a.next_refresh_human || '—')}</strong></div>
      </div>
      <div class="acc-actions">
        ${a.session_state === 'logged_out' || a.session_state === 'expired' ? `<button class="btn xs primary" data-acc-login="${esc(a.id)}">${icon('eye')} 扫码登录</button>` : `<button class="btn xs ghost" data-acc-refresh="${esc(a.id)}">${icon('refresh')} 刷新</button>${a.session_state === 'authenticated' || a.session_state === 'expiring' ? `<button class="btn xs soft" data-acc-sync="${esc(a.id)}">同步账号</button>` : ''}`}
        ${!a.is_active && a.session_state === 'authenticated' ? `<button class="btn xs soft" data-acc-activate="${esc(a.id)}">设为当前</button>` : ''}
        ${a.session_state !== 'logged_out' ? `<button class="btn xs ghost" data-acc-logout="${esc(a.id)}">退出</button>` : ''}
      </div>
    </div>`;
  }

  async function accountAction(id, action) {
    try {
      const r = await api(`/accounts/${id}/${action}`, { method: 'POST' });
      toast(action === 'refresh' ? '刷新完成' : action === 'activate' ? '已切换当前账号' : '已退出登录');
      await loadAccounts();
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); }
  }

  function openAddAccount() {
    openModal({
      title: '添加闲鱼账号',
      body: `<div class="field"><label>账号备注</label><input class="input" id="newAccName" placeholder="例如：备用小号" /></div><div class="notice mt12">${icon('shield')} 添加后状态为「未登录」，需要走扫码 → 扫码确认 → 登录成功流程。</div>`,
      footer: `<button class="btn ghost" id="addAccCancel">取消</button><button class="btn primary" id="addAccSave">添加</button>`,
    });
    $('#addAccCancel').onclick = closeModal;
    $('#addAccSave').onclick = async () => {
      const nickname = $('#newAccName').value.trim();
      if (!nickname) { toast('请填写账号备注', 'error'); return; }
      try { await api('/accounts', { method: 'POST', body: { nickname } }); toast('账号已添加'); closeModal(); await loadAccounts(); } catch (e) { toast(e.message, 'error'); }
    };
  }

  async function openLoginModal(id) {
    let start;
    try { start = await api(`/accounts/${id}/login/start`, { method: 'POST' }); } catch (e) { toast(e.message, 'error'); return; }
    const account = S.accounts.list.find((a) => a.id === id);
    const real = Boolean(start.qr_code_url);
    if (real) {
      let stopped = false;
      openModal({
        title: '扫码登录 · ' + (account ? account.nickname : ''),
        body: `<div class="login-flow">
          <div class="qr-wrap"><img class="qr-img" src="${start.qr_code_url}" alt="闲鱼登录二维码" /><div class="qr-tip" id="qrLive">等待扫码 · 请用闲鱼 App 扫描</div></div>
          <div class="login-steps"><div class="login-step done">1. 平台二维码已生成</div><div class="login-step" id="stepScan">2. 手机扫码</div><div class="login-step" id="stepConfirm">3. 手机确认登录</div></div>
          <div class="notice mt12">${icon('clock')} 二维码 300 秒有效；登录成功后会自动获取 IM Token 并启动 WebSocket。</div>
          <div class="notice warn mt12 hidden" id="faceNotice">${icon('alert')} 平台要求人脸验证：<a id="faceLink" target="_blank" rel="noreferrer">打开验证页</a>，完成后重新扫码登录。</div>
        </div>`,
        footer: `<button class="btn ghost" id="loginCancel">取消</button>`,
      });
      const stop = () => { stopped = true; clearInterval(timer); };
      $('#loginCancel').onclick = () => { stop(); closeModal(); };
      const timer = setInterval(async () => {
        if (stopped || !document.querySelector('#qrLive')) { stop(); return; }
        try {
          const st = await api(`/accounts/${id}/login/status`);
          const state = st.status;
          if (state === 'scanned') { $('#stepScan')?.classList.add('done'); const el = $('#qrLive'); if (el) el.textContent = '已扫码 · 请在手机端确认'; }
          if (state === 'verification_required') {
            stop();
            const el = $('#qrLive'); if (el) el.textContent = '平台要求人脸验证';
            const notice = $('#faceNotice'); if (notice) notice.classList.remove('hidden');
            const link = $('#faceLink'); if (link && st.verification_url) link.href = st.verification_url;
          }
          if (state === 'expired' || state === 'cancelled' || state === 'failed') {
            stop();
            const el = $('#qrLive'); if (el) el.textContent = st.message || '二维码已失效，请重新生成';
          }
          if (state === 'success') {
            stop(); $('#stepConfirm')?.classList.add('done');
            toast('登录成功，正在启动原生 WebSocket');
            closeModal(); await loadAccounts(); await refreshGlobal();
          }
        } catch (e) {
          stop(); const el = $('#qrLive'); if (el) el.textContent = '状态查询失败：' + e.message;
        }
      }, 1500);
      return;
    }
    toast('二维码生成失败，请检查网络/日志', 'error');
  }

  // =========================================================
  // Notification channels
  // =========================================================
  const NOTIFY_KINDS = {
    log: ['站内日志', 'activity'], wecom: ['企业微信', 'wechat'], bark: ['Bark', 'bell'],
    serverchan: ['Server酱', 'send'], ntfy: ['ntfy', 'bell'], telegram: ['Telegram', 'send'],
    pushplus: ['PushPlus', 'send'], gotify: ['Gotify', 'send'], generic: ['通用 Webhook', 'link'],
    email: ['邮箱 SMTP/IMAP', 'send'],
  };
  const ACC_EVENT_LABEL = {
    created: '账号创建', login_start: '生成二维码', login_scanned: '已扫码',
    login_success: '登录成功', token_refresh: 'token 刷新', expiring: '即将过期',
    refresh_failed: '刷新失败', logout: '退出登录', activate: '切换当前账号',
  };

  async function pageNotify() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>一个告警，多渠道送达</h2><p>Bark / 企业微信 / Server酱 / ntfy / Telegram / PushPlus / Gotify / 邮箱 / 通用 Webhook；邮箱同时支持收指令。</p></div>
        <div class="btn-row"><button class="btn ghost" id="notifyEmailPoll">${icon('refresh')} 检查邮箱</button><button class="btn soft" id="notifyTestAlert">${icon('send')} 发测试告警</button><button class="btn" id="addChannel">${icon('bell')} 添加渠道</button><button class="btn ghost" id="notifyRefresh">${icon('refresh')}</button></div>
      </div>
      <div id="notifyMain"><div class="loading-page"><span class="spinner"></span> 读取通知渠道…</div></div>`;
    $('#addChannel').onclick = () => openChannelModal();
    $('#notifyRefresh').onclick = () => loadNotify();
    $('#notifyEmailPoll').onclick = async () => {
      try {
        const r = await api('/notify/email/poll', { method: 'POST' });
        if (r.ok === false) throw new Error(r.error || '检查邮箱失败');
        toast(`邮箱检查完成：收到 ${r.fetched || 0} 封，处理 ${r.processed || 0} 封`);
        await loadNotify();
      } catch (e) { toast(e.message, 'error'); }
    };
    $('#notifyTestAlert').onclick = async () => { try { await api('/notify/test', { method: 'POST', body: {} }); toast('测试告警已生成，正在投递'); await sleep(700); await loadNotify(); } catch (e) { toast(e.message, 'error'); } };
    await loadNotify();
  }

  async function loadNotify() {
    const [channels, logs] = await Promise.all([api('/notify/channels'), api('/notify/logs?limit=40')]);
    S.notify.channels = channels || [];
    S.notify.logs = logs || [];
    renderNotify();
  }

  function renderNotify() {
    const el = $('#notifyMain'); if (!el) return;
    const channels = S.notify.channels || [];
    const logs = S.notify.logs || [];
    const stats = S.system?.notify || {};
    el.innerHTML = `<div class="notify-layout">
      <div class="stack">
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('bell')} 渠道</div><div class="card-sub">${stats.enabled || channels.filter((c) => c.enabled).length} 个启用 · 当前告警会按 min_level 过滤</div></div>${chip(`${stats.sent || 0} 成功`, 'green')} ${chip(`${stats.failed || 0} 失败`, (stats.failed ? 'red' : 'gray'))}</div>
          <div class="channel-grid">
            ${channels.map((c) => renderChannelCard(c)).join('') || emptyBlock('还没有通知渠道', '至少保留一个站内日志渠道', 'bell')}
          </div>
          <div class="notice mt16">${icon('shield')} 站内日志渠道永远不需要外部网络；其余渠道在发送失败时会自动重试 3 次，并保留完整 error 日志。</div>
        </div>
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('activity')} 最近投递</div><div class="card-sub">每次告警 × 每个渠道 = 一条日志</div></div><button class="btn xs ghost" id="notifyLogsRefresh">${icon('refresh')}</button></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>渠道</th><th>告警</th><th>级别</th><th>状态</th><th>尝试</th><th>时间</th><th>错误</th></tr></thead><tbody>
            ${logs.length ? logs.map((l) => `<tr><td>${esc(l.channel_name || l.channel_id)}</td><td class="ord-id">${esc(l.alert_id || '—')}</td><td>${levelChip(l.level || 'P1')}</td><td>${chip(l.status === 'sent' ? '已送达' : l.status === 'failed' ? '失败' : '待发', l.status === 'sent' ? 'green' : l.status === 'failed' ? 'red' : 'amber')}</td><td>${l.attempts || 0}</td><td class="ord-sub">${esc(l.created_human || '')}</td><td class="ord-sub">${esc((l.error || '').slice(0, 80))}</td></tr>`).join('') : '<tr><td colspan="7"><div class="empty">暂无投递记录</div></td></tr>'}
          </tbody></table></div>
        </div>
      </div>
      <div class="stack">
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('spark')} 一个 Alert 的生命周期</div><div class="card-sub">告警中心 → 通知服务 → 渠道适配器</div></div></div>
          <div class="trace">
            <div class="trace-step"><span class="trace-dot">1</span><div class="trace-main"><strong>分级</strong><p>P0 强提醒 / P1 普通提醒 / P2 日报。渠道可设 min_level。</p></div></div>
            <div class="trace-step"><span class="trace-dot">2</span><div class="trace-main"><strong>分发</strong><p>启用渠道 + 级别过滤，每个渠道独立任务，不阻塞主链路。</p></div></div>
            <div class="trace-step"><span class="trace-dot">3</span><div class="trace-main"><strong>重试与留痕</strong><p>最多 3 次退避；发送结果落 notification_logs，可回看。</p></div></div>
          </div>
        </div>
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('plug')} 环境变量快捷接入</div></div></div>
          <div class="turn-mini">
            <div class="kv"><span>企业微信</span><strong>WECOM_WEBHOOK</strong></div>
            <div class="kv"><span>Bark</span><strong>BARK_URL</strong></div>
            <div class="kv"><span>Server酱</span><strong>SERVERCHAN_KEY</strong></div>
            <div class="kv"><span>ntfy</span><strong>NTFY_URL / NTFY_TOPIC</strong></div>
          </div>
          <div class="notice mt12">${icon('shield')} 邮箱/渠道配置保存于本机 <span class="mono">data/yuxiaoer.db</span>，重启自动读取；删除数据库才会丢失。</div>
          <div class="notice mt12">${icon('alert')} 修改环境变量后重启服务；也可以在本页直接添加渠道并点测试。</div>
        </div>
      </div>
    </div>`;
    el.querySelectorAll('[data-ch-toggle]').forEach((b) => { b.onclick = () => toggleChannel(b.dataset.chToggle); });
    el.querySelectorAll('[data-ch-test]').forEach((b) => { b.onclick = () => testChannel(b.dataset.chTest); });
    el.querySelectorAll('[data-ch-edit]').forEach((b) => { b.onclick = () => openChannelModal(b.dataset.chEdit); });
    el.querySelectorAll('[data-ch-del]').forEach((b) => { b.onclick = () => deleteChannel(b.dataset.chDel); });
    const lr = $('#notifyLogsRefresh'); if (lr) lr.onclick = loadNotify;
  }

  function renderChannelCard(c) {
    const kind = NOTIFY_KINDS[c.kind] || [c.kind, 'bell'];
    return `<div class="channel-card ${c.enabled ? 'on' : ''}">
      <div class="channel-top"><span class="channel-ico">${icon(kind[1])}</span><div class="grow"><strong>${esc(c.name)}</strong><small>${esc(kind[0])} · 最低 ${esc(c.min_level)}</small></div><button class="toggle ${c.enabled ? 'checked' : ''}" data-ch-toggle="${esc(c.id)}" title="启用/停用"><span></span></button></div>
      <div class="channel-config">${esc(c.config_summary || '无需配置')}</div>
      <div class="channel-actions"><button class="btn xs ghost" data-ch-test="${esc(c.id)}">${icon('send')} 测试</button><button class="btn xs ghost" data-ch-edit="${esc(c.id)}">${icon('edit')} 编辑</button>${c.id !== 'ch_log' ? `<button class="btn xs ghost" data-ch-del="${esc(c.id)}">${icon('trash')} 删除</button>` : ''}</div>
    </div>`;
  }

  async function toggleChannel(id) {
    const c = S.notify.channels.find((x) => x.id === id); if (!c) return;
    try {
      await api(`/notify/channels/${id}`, { method: 'PUT', body: { kind: c.kind, name: c.name, config: c.config, enabled: !c.enabled, min_level: c.min_level } });
      await loadNotify();
    } catch (e) { toast(e.message, 'error'); }
  }

  async function testChannel(id) {
    try {
      const r = await api(`/notify/channels/${id}/test`, { method: 'POST' });
      if (r.status && r.status !== 'sent') throw new Error(r.error || '发送失败');
      toast('测试消息已送达'); await loadNotify();
    } catch (e) { toast(e.message, 'error'); await loadNotify(); }
  }

  async function deleteChannel(id) {
    if (!(await confirmAction({ title: '删除通知渠道', message: '删除后该渠道不会再收到告警，历史投递日志保留。', confirmText: '删除', danger: true }))) return;
    try { await api(`/notify/channels/${id}`, { method: 'DELETE' }); toast('已删除'); await loadNotify(); } catch (e) { toast(e.message, 'error'); }
  }

  function openChannelModal(editId = null) {
    const c = editId ? S.notify.channels.find((x) => x.id === editId) : null;
    const cfg = (c && c.config) || {};
    const kind = c ? c.kind : 'bark';
    openModal({
      title: c ? '编辑通知渠道' : '添加通知渠道', wide: true,
      body: `<div class="form-grid">
        <div class="field"><label>渠道类型</label><select class="input" id="chKind">${Object.entries(NOTIFY_KINDS).map(([k, v]) => `<option value="${k}" ${k === kind ? 'selected' : ''}>${esc(v[0])}</option>`).join('')}</select></div>
        <div class="field"><label>名称</label><input class="input" id="chName" value="${esc(c ? c.name : '')}" placeholder="例如：我的 Bark" /></div>
        <div class="field"><label>最低级别</label><select class="input" id="chLevel">${['P0', 'P1', 'P2'].map((l) => `<option ${((c && c.min_level) || 'P1') === l ? 'selected' : ''}>${l}</option>`).join('')}</select><div class="hint">选 P1 会收到 P0+P1；P2 只收 P2。</div></div>
        <div class="field"><label>启用</label><label class="toggle"><input type="checkbox" id="chEnabled" ${!c || c.enabled ? 'checked' : ''}/><span></span></label></div>
      </div>
      <div class="divider"></div>
      <div id="chConfigFields"></div>
      <div class="notice mt12">${icon('shield')} 凭据只保存在本机 SQLite；测试与正式发送使用同一套适配器。</div>`,
      footer: `<button class="btn ghost" id="chCancel">取消</button><button class="btn primary" id="chSave">保存渠道</button>`,
    });
    const renderFields = () => {
      const k = $('#chKind').value;
      let html = '';
      if (k === 'log') html = '<div class="notice">站内日志渠道无需外部配置。</div>';
      else if (k === 'email') {
        html = `<div class="notice mb12">${icon('send')} SMTP 用来发告警/回复；IMAP 用来收店主的邮件指令。只有「允许发件人」发来的邮件会执行。</div>
          <div class="section-title">SMTP 发件</div>
          <div class="form-grid">
            <div class="field"><label>SMTP Host</label><input class="input" id="emSmtpHost" value="${esc(cfg.smtp_host || '')}" placeholder="smtp.qq.com" /></div>
            <div class="field"><label>SMTP 端口</label><input class="input" id="emSmtpPort" type="number" value="${esc(cfg.smtp_port || 465)}" /></div>
            <div class="field"><label>SMTP 账号</label><input class="input" id="emSmtpUser" value="${esc(cfg.smtp_user || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>SMTP 密码/授权码</label><input class="input" id="emSmtpPass" type="password" value="${esc(cfg.smtp_password || '')}" /></div>
            <div class="field"><label>发件地址</label><input class="input" id="emFrom" value="${esc(cfg.from_addr || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>收件地址（告警/回复）</label><input class="input" id="emTo" value="${esc(cfg.to_addr || '')}" placeholder="owner@example.com" /></div>
            <div class="field"><label>SMTP SSL</label><label class="toggle"><input type="checkbox" id="emSmtpSsl" ${cfg.smtp_ssl === false ? '' : 'checked'}/><span></span></label></div>
          </div>
          <div class="section-title mt16">IMAP 收件</div>
          <div class="form-grid">
            <div class="field"><label>IMAP Host</label><input class="input" id="emImapHost" value="${esc(cfg.imap_host || '')}" placeholder="imap.qq.com" /></div>
            <div class="field"><label>IMAP 端口</label><input class="input" id="emImapPort" type="number" value="${esc(cfg.imap_port || 993)}" /></div>
            <div class="field"><label>IMAP 账号</label><input class="input" id="emImapUser" value="${esc(cfg.imap_user || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>IMAP 密码/授权码</label><input class="input" id="emImapPass" type="password" value="${esc(cfg.imap_password || '')}" /></div>
            <div class="field"><label>邮箱文件夹</label><input class="input" id="emFolder" value="${esc(cfg.imap_folder || 'INBOX')}" /></div>
            <div class="field"><label>IMAP SSL</label><label class="toggle"><input type="checkbox" id="emImapSsl" ${cfg.imap_ssl === false ? '' : 'checked'}/><span></span></label></div>
            <div class="field" style="grid-column:1/-1"><label>允许发件人（逗号/换行分隔）</label><input class="input" id="emAllowed" value="${esc(cfg.allowed_senders || '')}" placeholder="owner@example.com" /><div class="hint">必须配置；只有这些邮箱能通过邮件让 Agent 执行上架/改价/下架等操作。</div></div>
          </div>`;
      } else {
        html = `<div class="form-grid"><div class="field"><label>服务地址 / URL</label><input class="input" id="chUrl" value="${esc(cfg.url || '')}" placeholder="https://..." /></div><div class="field"><label>Token / Key</label><input class="input" id="chToken" value="${esc(cfg.token || '')}" placeholder="可选" /></div><div class="field"><label>Topic / Chat ID</label><input class="input" id="chTopic" value="${esc(cfg.topic || cfg.chat_id || '')}" placeholder="ntfy topic / Telegram chat_id" /></div></div>`;
      }
      $('#chConfigFields').innerHTML = html;
    };
    $('#chKind').onchange = renderFields; renderFields();
    $('#chCancel').onclick = closeModal;
    $('#chSave').onclick = async () => {
      const k = $('#chKind').value;
      const config = {};
      if (k === 'email') {
        config.smtp_host = ($('#emSmtpHost')?.value || '').trim();
        config.smtp_port = Number($('#emSmtpPort')?.value) || 465;
        config.smtp_user = ($('#emSmtpUser')?.value || '').trim();
        config.smtp_password = $('#emSmtpPass')?.value || '';
        config.smtp_ssl = Boolean($('#emSmtpSsl')?.checked);
        config.from_addr = ($('#emFrom')?.value || '').trim();
        config.to_addr = ($('#emTo')?.value || '').trim();
        config.imap_host = ($('#emImapHost')?.value || '').trim();
        config.imap_port = Number($('#emImapPort')?.value) || 993;
        config.imap_user = ($('#emImapUser')?.value || '').trim();
        config.imap_password = $('#emImapPass')?.value || '';
        config.imap_folder = ($('#emFolder')?.value || 'INBOX').trim();
        config.imap_ssl = Boolean($('#emImapSsl')?.checked);
        config.allowed_senders = ($('#emAllowed')?.value || '').trim();
      } else if (k !== 'log') {
        const url = ($('#chUrl')?.value || '').trim();
        const token = ($('#chToken')?.value || '').trim();
        const topic = ($('#chTopic')?.value || '').trim();
        if (url) config.url = url;
        if (token) config.token = token;
        if (topic) { if (k === 'ntfy') config.topic = topic; else config.chat_id = topic; }
      }
      const payload = { kind: k, name: ($('#chName').value || '').trim() || (NOTIFY_KINDS[k] || ['渠道'])[0], config, enabled: $('#chEnabled').checked, min_level: $('#chLevel').value };
      try {
        if (editId) await api(`/notify/channels/${editId}`, { method: 'PUT', body: payload });
        else await api('/notify/channels', { method: 'POST', body: payload });
        toast('渠道已保存'); closeModal(); await loadNotify();
      } catch (e) { toast(e.message, 'error'); }
    };
  }


  async function pageSettings() {
    const [data, items] = await Promise.all([api('/settings'), api('/items')]);
    S.settings.data = data; S.settings.items = items || [];
    const v = data.values || {}; const sys = data.system || {}; const llm = data.llm || {};
    const editable = data.editable || [];
    const bool = (val) => String(val) === '1' || String(val) === 'true' || String(val) === 'on';
    $('#view').innerHTML = `
      <div class="page-head"><div><h2>托管参数与连接</h2><p>所有改动即时生效；频控与工具上限是服务端硬约束。</p></div><div class="btn-row"><button class="btn soft" id="saveSettings">${icon('check')} 保存托管设置</button><button class="btn" id="copyDiag">${icon('copy')} 复制诊断</button></div></div>
      <div class="settings-grid">
        <div class="stack">
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('settings')} 托管策略</div><div class="card-sub">影响买家 Agent 的议价与回复节奏</div></div></div>
            <div class="form-grid">
              <div class="field"><label>商品底价折扣（%）</label><input class="input" id="setFloor" type="number" min="50" max="100" value="${esc(v.floor_discount_pct || 85)}" /><div class="hint">新商品底价 = 售价 × 该比例；买家侧永不展示底价。</div></div>
              <div class="field"><label>消息合并窗口（秒）</label><input class="input" id="setMerge" type="number" min="0" max="30" step="0.5" value="${esc(v.merge_window_seconds || 1.5)}" /><div class="hint">同一买家在窗口内的多条消息合并为一轮，生产建议 5 秒。</div></div>
              <div class="field"><label>议价轮数上限</label><input class="input" id="setBargainRounds" type="number" min="1" max="10" value="${esc(v.bargain_max_rounds || 3)}" /><div class="hint">到达上限后只守底价，不再让步。</div></div>
              <div class="field"><label>店铺名</label><input class="input" id="setShop" value="${esc(v.shop_name || '')}" /></div>
              <div class="field"><label>风控熔断冷却（分钟）</label><input class="input" id="setRiskCooldown" type="number" min="1" max="180" value="${esc(v.risk_cooldown_minutes || 30)}" /></div>
              <div class="field"><label>每日擦亮时间</label><input class="input" id="setPolishTime" type="time" value="${esc(v.polish_time || '10:05')}" /></div>
              <div class="field"><label>日报时间</label><input class="input" id="setReportTime" type="time" value="${esc(v.daily_report_time || '21:00')}" /></div>
              <div class="switch"><div><strong>夜间免打扰</strong><small>01:00–07:00 的回复延迟到 07:30</small></div><label class="toggle"><input type="checkbox" id="setNight" ${bool(v.night_mode) ? 'checked' : ''}/><span></span></label></div>
              <div class="switch"><div><strong>完成后自动评价</strong><small>买家确认收货后自动留默认好评</small></div><label class="toggle"><input type="checkbox" id="setAutoReview" ${bool(v.auto_review) ? 'checked' : ''}/><span></span></label></div>
              <div class="switch"><div><strong>人工输入延迟</strong><small>发送前 0.35–0.95s 打字延迟，降低机器人特征</small></div><label class="toggle"><input type="checkbox" id="setTyping" ${bool(v.human_typing) ? 'checked' : ''}/><span></span></label></div>
            </div>
            <div class="notice mt16">${icon('shield')} 频控（1 分钟 ≤ 2 条）与工具步数上限是服务端硬编码，不属于可调项。</div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('spark')} LLM 接入（可选）</div><div class="card-sub">默认规则模式即可完整运行</div></div>${llm.enabled ? chip('在线', 'green') : chip('规则模式', 'gray')}</div>
            <div class="sys-row"><span>状态</span><strong>${esc(llm.mode || '未配置')}</strong></div>
            <div class="sys-row"><span>模型</span><strong>${esc(llm.model || '—')}</strong></div>
            <div class="sys-row"><span>端点</span><strong>${esc(llm.base_url || '—')}</strong></div>
            <div class="sys-row"><span>调用 / 失败</span><strong>${llm.calls || 0} / ${llm.failures || 0}</strong></div>
            <div class="switch mt12"><div><strong>启用 LLM 增强</strong><small>${llm.has_key ? '用于文案润色、低置信分类与 judge' : '需要先在 .env 配置 LLM_API_KEY'}</small></div><label class="toggle"><input type="checkbox" id="setLlm" ${bool(v.llm_enabled) && llm.has_key ? 'checked' : ''} ${llm.has_key ? '' : 'disabled'}/><span></span></label></div>
            <div class="notice mt12">${icon('plug')} 在项目根目录 <span class="mono">.env</span> 配置：<span class="mono">LLM_API_KEY / LLM_BASE_URL / LLM_MODEL</span>，重启后生效。LLM 失败会自动熔断并降级为规则模式。</div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('plug')} 开放接口（真实数据子集）</div><div class="card-sub">账号 / Cookie / 订单 / 消息日志</div></div>${chip('原生模式', 'purple')}</div>
            <div class="sys-row"><span>Base URL</span><strong class="mono">/api/v1/external</strong></div>
            <div class="sys-row"><span>共享秘钥</span><strong class="mono">${esc(sys.external?.secret_masked || '—')}</strong></div>
            <div class="sys-row"><span>调用方式</span><strong>JSON body / GET query</strong></div>
            <div class="notice mt12">${icon('shield')} 业务错误固定 HTTP 200；秘钥来自 <span class="mono">YUXIAOER_EXTERNAL_SECRET</span>。不提供发布/分类接口。</div>
            <div class="btn-row mt12"><a class="btn sm soft" href="/docs" target="_blank" rel="noreferrer">打开 Swagger</a><span class="tiny muted mono">docs/EXTERNAL-API.md</span></div>
          </div>
        </div>
        <div class="stack">
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('activity')} 系统状态</div><div class="card-sub">进程内实时快照</div></div></div>
            <div class="sys-row"><span>通道</span><strong>${esc(sys.channel?.label || '—')} · ${sys.channel?.online ? '在线' : '离线'}</strong></div>
            <div class="sys-row"><span>账号</span><strong>${sys.accounts_count || 0} 个 / 当前 ${esc(sys.account?.nickname || '—')}</strong></div>
            <div class="sys-row"><span>风控</span><strong>${sys.risk?.open ? '熔断中 · ' + esc(sys.risk.until_human) : '正常'}</strong></div>
            <div class="sys-row"><span>通知渠道</span><strong>${sys.notify?.enabled || 0} 启用 · ${sys.notify?.sent || 0} 送达</strong></div>
            <div class="sys-row"><span>账号心跳</span><strong>${esc(sys.account?.last_heartbeat_at ? fmtTime(sys.account.last_heartbeat_at, true) : '—')}</strong></div>
            <div class="sys-row"><span>写队列</span><strong>${sys.queue?.processed || 0} 成功 / ${sys.queue?.failed || 0} 失败 / 深度 ${sys.queue?.depth || 0}</strong></div>
            <div class="sys-row"><span>outbox</span><strong>${sys.outbox?.pending || 0} 待发 / ${sys.outbox?.failed || 0} 失败</strong></div>
            <div class="sys-row"><span>事件</span><strong>${sys.events?.delivered || 0} 已投递 / 积压 ${sys.events?.backlog || 0}</strong></div>
            <div class="sys-row"><span>知识库</span><strong>${sys.knowledge?.sources_live || 0} live / ${sys.knowledge?.chunks || 0} chunks / FTS ${sys.knowledge?.fts ? '开' : '关'}</strong></div>
            <div class="sys-row"><span>数据库</span><strong class="mono" style="font-size:9px">${esc(sys.db_path || '')}</strong></div>
            <div class="sys-row"><span>启动时间</span><strong>${esc(sys.started_human || '—')}</strong></div>
          </div>
          <div class="card pad">
            <div class="card-head"><div><div class="card-title">${icon('shield')} 风险与边界</div><div class="card-sub">对店主透明</div></div></div>
            <div class="notice warn">${icon('alert')} 逆向通道可能违反平台用户协议，账号存在被处置风险。请使用小号、控制频率，并优先考虑官方通道。</div>
            <div class="notice mt12">${icon('shield')} 原生模式：Cookie/Token 只在本机 SQLite；LLM 关闭时数据不出本机。</div>
            <div class="notice red mt12">${icon('alert')} 原生发布 / 下架 / 改价已接入；真实结果以平台返回为准，失败不会伪造成功。卡券只由店主在本地维护。</div>
            <div class="btn-row mt12"><button class="btn sm soft" data-nav="accounts">${icon('shield')} 账号与风控</button><button class="btn sm ghost" data-nav="notify">${icon('bell')} 通知渠道</button></div>
          </div>
        </div>
      </div>`;
    $('#saveSettings').onclick = saveSettings;
    $('#copyDiag').onclick = async () => { try { await navigator.clipboard.writeText(JSON.stringify(sys, null, 2)); toast('诊断 JSON 已复制'); } catch (e) { toast('复制失败，请手动查看', 'error'); } };
    $$('[data-nav]').forEach((b) => { b.onclick = () => navigate(b.dataset.nav); });
  }

  async function saveSettings() {
    const values = {
      floor_discount_pct: Number($('#setFloor').value),
      merge_window_seconds: Number($('#setMerge').value),
      bargain_max_rounds: Number($('#setBargainRounds').value),
      risk_cooldown_minutes: Number($('#setRiskCooldown').value),
      polish_time: $('#setPolishTime').value,
      daily_report_time: $('#setReportTime').value,
      shop_name: $('#setShop').value.trim(),
      night_mode: $('#setNight').checked ? 1 : 0,
      auto_review: $('#setAutoReview').checked ? 1 : 0,
      human_typing: $('#setTyping').checked ? 1 : 0,
      llm_enabled: $('#setLlm').checked ? 1 : 0,
    };
    try {
      const r = await api('/settings', { method: 'POST', body: { values } });
      toast('设置已保存'); await refreshGlobal(); await pageSettings();
    } catch (e) { toast(e.message, 'error'); }
  }

  // =========================================================
  // boot
  // =========================================================
  async function boot() {
    $('#brandMark').innerHTML = '<img src="/static/favicon.svg" alt="" style="width:100%;height:100%;border-radius:11px" />';
    $('#bellIcon').innerHTML = icon('bell');
    $('#alertBtn').onclick = openAlertCenter;
    window.addEventListener('hashchange', renderRoute);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
    renderNav();
    await refreshGlobal();
    setInterval(refreshGlobal, 30000);
    renderRoute();
  }

  boot();
})();
