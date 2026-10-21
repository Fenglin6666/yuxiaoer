/* 多账号切换器：嵌在客服工作台 / 让小二做点什么页面顶部，不单独做页面。 */

import { $, S, closeModal, esc, openModal, sessionMeta, toast } from './core.js?v=20261021-3';

async function hubFetch(path, options = {}) {
  const opts = { method: options.method || 'GET', headers: {} };
  if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function accountState(item) {
  const account = item.account || {};
  const session = sessionMeta(account);
  const online = Boolean(item.running && item.health && item.health.online);
  if (!account.id) return { account, session, online, dot: 'offline', short: item.running ? '未登录' : '已停止', detail: item.running ? '未登录' : '已停止' };
  const short = session.key === 'authenticated' ? (online ? '在线' : item.running ? '启动中' : '已停止') : session.short;
  const dot = session.key === 'authenticated' ? (online ? '' : 'offline') : session.dot;
  return { account, session, online, dot, short, detail: session.key === 'authenticated' ? short : session.label };
}

export function accountLabel(item) {
  const state = accountState(item);
  const who = state.account.nickname || state.account.platform_user_id || '未登录';
  return `${item.name} · ${who} · ${state.detail}`;
}

async function loadAccounts() {
  const data = await hubFetch('/api/hub/accounts');
  return data.accounts || [];
}

function selectAccount(accounts) {
  S.hubAccounts = accounts;
  if (!accounts.length) return;
  const exists = accounts.some((item) => item.id === S.accountId);
  if (!exists) {
    const preferred = accounts.find((item) => item.running && item.health && item.health.online && sessionMeta(item.account).usable)
      || accounts.find((item) => sessionMeta(item.account).key === 'authenticated')
      || accounts[0];
    S.accountId = preferred.id;
    localStorage.setItem('yuxiaoer_account', S.accountId);
  }
}

export function accountTabsHTML() {
  const accounts = S.hubAccounts || [];
  if (!accounts.length) {
    return '<div class="account-tabs"><span class="account-tabs-label">账号</span><span class="muted">还没有闲鱼账号</span><button class="account-tab add" data-account-manage>+ 添加账号</button></div>';
  }
  const tabs = accounts.map((item) => {
    const active = item.id === S.accountId;
    const state = accountState(item);
    const who = state.session.key === 'authenticated'
      ? (state.account.nickname || state.account.platform_user_id || '闲鱼账号')
      : '未登录';
    return `<button class="account-tab ${active ? 'active' : ''}" data-account-id="${esc(item.id)}">
      <span class="at-title"><i class="dot ${state.dot}"></i><b>${esc(item.name)}</b></span><span class="account-state ${state.dot}">${esc(who)} · ${esc(state.short)}</span>
    </button>`;
  }).join('');
  return `<div class="account-tabs"><span class="account-tabs-label">账号</span>${tabs}<button class="account-tab add" data-account-manage>+ 账号</button></div>`;
}

const tabReloads = new WeakMap();

export function bindAccountTabs(root, reload) {
  if (!root) return;
  tabReloads.set(root, reload);
  if (root.dataset.accountTabsBound === '1') return;
  root.dataset.accountTabsBound = '1';
  root.addEventListener('click', async (event) => {
    const tab = event.target.closest('[data-account-id]');
    if (tab) {
      const id = tab.dataset.accountId;
      if (id === S.accountId) return;
      S.accountId = id;
      localStorage.setItem('yuxiaoer_account', id);
      const fn = tabReloads.get(root);
      if (fn) {
        try { await fn(); } catch (err) { toast(err.message, 'error'); }
      }
      return;
    }
    if (event.target.closest('[data-account-manage]')) {
      openManager().catch((err) => toast(err.message, 'error'));
    }
  });
}

export async function refreshHub() {
  try {
    const accounts = await loadAccounts();
    selectAccount(accounts);
    const html = accountTabsHTML();
    ['#inboxAccounts', '#sellerAccounts'].forEach((selector) => {
      const root = $(selector);
      if (root && root.innerHTML !== html) root.innerHTML = html;
    });
  } catch (_) { /* 账号状态刷新失败时保留当前界面 */ }
}

async function openManager() {
  const accounts = await loadAccounts();
  const rows = accounts.map((item) => {
    const state = accountState(item);
    return `<div class="hub-row" style="display:flex;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)">
      <div style="flex:1;min-width:0">
        <b>${esc(item.name)}</b> <span class="muted">${esc(item.id)} · :${item.port}</span>
        <div class="muted"><i class="dot ${state.dot}" style="margin-right:5px"></i>${esc(state.account.nickname || '未登录')} · ${esc(state.detail)}${item.restarts ? ` · 重启${item.restarts}次` : ''}</div>
      </div>
      <button class="btn ghost" data-hub-action="select" data-id="${esc(item.id)}">切换</button>
      <button class="btn ghost" data-hub-action="login" data-id="${esc(item.id)}">扫码</button>
      <button class="btn ghost" data-hub-action="${item.running ? 'stop' : 'start'}" data-id="${esc(item.id)}">${item.running ? '停止' : '启动'}</button>
      <button class="btn ghost" data-hub-action="delete" data-id="${esc(item.id)}">删除</button>
    </div>`;
  }).join('') || '<div class="empty"><strong>还没有闲鱼账号</strong>先添加一个，再用闲鱼 App 扫码。</div>';

  openModal({
    title: '闲鱼账号',
    wide: true,
    body: `${rows}
      <div style="display:flex;gap:8px;margin-top:16px">
        <input id="hubNewName" class="input" placeholder="本地名称，如 主号 / 小号" style="flex:1" />
        <button class="btn primary" id="hubAdd">添加并启动</button>
      </div>
      <p class="muted" style="margin-top:8px">添加只创建本地实例；真实账号仍用闲鱼 App 扫码登录。</p>`,
  });
  $('#hubAdd').onclick = async () => {
    const name = $('#hubNewName').value.trim();
    if (!name) return;
    try {
      const created = await hubFetch('/api/hub/accounts', { method: 'POST', body: { name } });
      if (created.account && created.account.id) {
        S.accountId = created.account.id;
        localStorage.setItem('yuxiaoer_account', S.accountId);
      }
      await openManager();
    } catch (err) { toast(err.message, 'error'); }
  };
  $('#modalRoot').onclick = async (event) => {
    const btn = event.target.closest('[data-hub-action]');
    if (!btn) return;
    const id = btn.dataset.id;
    const action = btn.dataset.hubAction;
    try {
      if (action === 'select') {
        S.accountId = id;
        localStorage.setItem('yuxiaoer_account', id);
        location.reload();
        return;
      }
      if (action === 'delete') {
        if (!confirm('删除这个本地账号实例？不会删除闲鱼账号。')) return;
        await hubFetch(`/api/hub/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' });
        await openManager();
        return;
      }
      if (action === 'login') {
        closeModal();
        await startLogin(id);
        return;
      }
      await hubFetch(`/api/hub/accounts/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: {} });
      await openManager();
    } catch (err) { toast(err.message, 'error'); }
  };
}

async function startLogin(shopId) {
  const data = await hubFetch(`/api/hub/accounts/${encodeURIComponent(shopId)}/login/start`, { method: 'POST', body: {} });
  if (!data.qr_code_url) throw new Error('没有拿到二维码，账号实例可能未启动');
  openModal({
    title: '扫码登录闲鱼',
    body: `<div style="text-align:center">
      <img src="${esc(data.qr_code_url)}" alt="闲鱼二维码" style="width:260px;height:260px;object-fit:contain;border:1px solid var(--line);border-radius:12px" />
      <p class="muted" id="hubQrStatus">请用闲鱼 App 扫码…</p>
    </div>`,
    onClose: () => { if (window.__hubQrTimer) clearInterval(window.__hubQrTimer); window.__hubQrTimer = null; },
  });
  window.__hubQrTimer = setInterval(async () => {
    try {
      const status = await hubFetch(`/api/hub/accounts/${encodeURIComponent(shopId)}/login/status?account_id=${encodeURIComponent(data.account_id)}`);
      const text = status.status === 'success' ? '登录成功，正在同步商品…' : `状态：${status.status || '等待扫码'}`;
      const el = $('#hubQrStatus');
      if (el) el.textContent = text;
      if (status.status === 'success') {
        clearInterval(window.__hubQrTimer);
        window.__hubQrTimer = null;
        await hubFetch(`/api/hub/accounts/${encodeURIComponent(shopId)}/login/sync?account_id=${encodeURIComponent(data.account_id)}`, { method: 'POST', body: {} });
        closeModal();
        toast('账号登录成功');
        setTimeout(() => location.reload(), 600);
      }
    } catch (_) { /* keep polling */ }
  }, 2000);
}

export async function initHub() {
  const accounts = await loadAccounts();
  const manage = () => openManager().catch((err) => toast(err.message, 'error'));
  const manageBtn = $('#manageAccounts');
  if (manageBtn) manageBtn.onclick = manage;
  const top = $('#manageAccountsTop');
  if (top) top.onclick = manage;
  if (!accounts.length) {
    selectAccount(accounts);
    await openManager();
    return;
  }
  selectAccount(accounts);
}
