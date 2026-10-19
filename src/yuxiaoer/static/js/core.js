/* 鱼小二控制台 · 核心：图标/格式化/状态/弹窗/外壳（原生 ESM，无构建） */

  // ---------------- icons ----------------
export const ICONS = {
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
export const icon = (name, cls = 'ico') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.grid}</svg>`;

  // ---------------- utils ----------------
export const $ = (sel, el = document) => el.querySelector(sel);
export const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const money = (cents) => `¥${((Number(cents) || 0) / 100).toFixed(2).replace(/\.?0+$/, '')}`;
export const pad = (n) => String(n).padStart(2, '0');
export function fmtTime(v, withDate = false) {
    if (!v) return '—';
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return withDate ? `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}` : `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
export function fmtDay(v) {
    if (!v) return '—';
    const d = new Date(v);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
export function chatDay(v) {
    if (!v) return '今天';
    const d = new Date(v); const now = new Date();
    if (d.toDateString() === now.toDateString()) return '今天';
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return '昨天';
    return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  }
export const nl2br = (text) => linkify(esc(text)).replace(/\n/g, '<br>');
export function linkify(escaped) {
    return escaped.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  }
export const initials = (name) => esc((name || '买').slice(0, 1));
export const avatar = (name, cls = '') => `<span class="avatar ${cls}">${initials(name)}</span>`;
export const avatarClass = (name) => `a${((name || '').length % 3) + 1}`;
export const clampPct = (n) => Math.max(0, Math.min(100, Number(n) || 0));

export function toast(message, type = 'ok') {
    const wrap = $('#toastWrap');
    const el = document.createElement('div');
    el.className = `toast ${type === 'error' ? 'error' : type === 'warn' ? 'warn' : ''}`;
    el.innerHTML = `${icon(type === 'error' ? 'alert' : type === 'warn' ? 'alert' : 'check')}<span>${esc(message)}</span>`;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .25s'; setTimeout(() => el.remove(), 260); }, 3600);
  }

export async function api(path, options = {}) {
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
export const S = {
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

export const ITEM_STATUS = {
    live: ['在售', 'green'], sold_out: ['已售出', 'amber'], pending_confirm: ['待确认', 'purple'],
    offline: ['已下架', 'gray'], draft: ['草稿', 'gray'],
  };
export const ORDER_STATUS = {
    new: ['新订单', 'gray'], paid: ['待发货', 'amber'], shipped: ['已发货', 'blue'],
    delivered: ['已送达', 'blue'], done: ['已完成', 'green'], refund_open: ['退款中', 'red'],
    refund_resolved: ['退款处理完成', 'purple'], cancelled: ['已取消', 'gray'],
  };
export const CATEGORY_LABEL = { pre_sale: '售前咨询', bargain: '议价', after_sale: '售后/履约', order: '订单查询', chitchat: '寒暄', risk: '风险消息', off_platform: '站外沟通', human: '要求人工', unknown: '未识别' };
export const ACTION_LABEL = { silent: '静默拦截', template: '模板回复', agent: 'Agent 托管' };

export function chip(text, cls = '') { return `<span class="chip ${cls}">${esc(text)}</span>`; }
export function itemStatus(status) { const m = ITEM_STATUS[status] || [status, 'gray']; return chip(m[0], m[1]); }
export function orderStatus(status) { const m = ORDER_STATUS[status] || [status, 'gray']; return chip(m[0], m[1]); }
export function levelChip(level) { return chip(level, level === 'P0' ? 'red' : level === 'P1' ? 'amber' : 'blue'); }

  // ---------------- modal ----------------
export let modalOnClose = null;
export function openModal({ title, body, footer = '', wide = false, onClose = null }) {
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
export function closeModal() {
    const root = $('#modalRoot');
    if (!root.innerHTML) return;
    root.innerHTML = '';
    document.body.classList.remove('modal-open');
    const cb = modalOnClose; modalOnClose = null;
    if (cb) cb();
  }
export function confirmAction({ title = '确认操作', message = '', confirmText = '确认', danger = false }) {
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
export const NAV_GROUPS = [
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
export const ROUTE_META = {
    overview: ['总览', '鱼小二正在替你值班'], inbox: ['客服工作台', '所有买家会话、上下文与转人工'],
    seller: ['让小二做点什么', '直接下指令，让 Agent 替你操作'],
    catalog: ['商品与知识', '商品状态、知识库版本与墓碑'], orders: ['订单履约', '待发货、退款与成交记录'],
    ops: ['观测评测', 'L0 健康 / L1 质量 / L2 成果 / 回放 / 黄金集'],
    accounts: ['账号与风控', '多账号登录生命周期、会话保活、反检测与熔断'],
    notify: ['通知渠道', '一个告警，多渠道投递 + 失败重试 + 投递日志'],
    settings: ['设置', '托管策略、通道与连接'],
  };

export function renderNav() {
    const nav = $('#nav');
    nav.innerHTML = NAV_GROUPS.map((g) => `
      <div class="nav-group">${esc(g.label)}</div>
      ${g.items.map((it) => {
        const badge = it.badge === 'inbox' && S.handoffCount > 0 ? `<span class="nav-badge">${S.handoffCount}</span>` : '';
        return `<a class="nav-item ${S.route === it.key ? 'active' : ''}" href="#/${it.key}">${icon(it.icon)}<span class="label">${esc(it.label)}</span>${badge}</a>`;
      }).join('')}
    `).join('');
  }

export async function refreshGlobal() {
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

export function clearTimers() {
    S.timers.forEach((t) => clearInterval(t));
    S.timers = [];
  }
export function every(fn, ms) { const t = setInterval(fn, ms); S.timers.push(t); return t; }

export function parseRoute() {
    const raw = (location.hash || '').replace(/^#\/?/, '');
    const key = raw.split('?')[0] || 'overview';
    return ROUTE_META[key] ? key : 'overview';
  }

export function metricCard(label, value, foot, ico, tone) {
    return `<div class="metric-card"><div class="top"><span class="metric-label">${esc(label)}</span><span class="metric-ico ${tone}">${icon(ico)}</span></div><div class="metric-value">${value}</div><div class="metric-foot">${esc(foot)}</div></div>`;
  }
export function emptyBlock(title, sub = '', ico = 'box') {
    return `<div class="empty"><div class="empty-ico">${icon(ico)}</div><strong>${esc(title)}</strong>${sub ? esc(sub) : ''}</div>`;
  }
export function compactPayload(p) {
    try { const s = JSON.stringify(p); return s.length > 110 ? s.slice(0, 108) + '…' : s; } catch (e) { return ''; }
  }
export function navigate(route) { location.hash = `#/${route}`; }

export async function openAlertCenter() {
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
