/* 鱼小二控制台 · 账号与风控（原生 ESM，无构建） */

import { $, S, api, avatar, chip, closeModal, compactPayload, confirmAction, emptyBlock, esc, every, icon, openModal, pad, refreshGlobal, toast } from '../core.js';

  // =========================================================
  // Accounts / session keeper / risk
  // =========================================================
export async function pageAccounts() {
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

export async function loadAccounts(scroll = false) {
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

export function renderAccounts() {
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

export function renderAccountCard(a, selected) {
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

export async function accountAction(id, action) {
    try {
      const r = await api(`/accounts/${id}/${action}`, { method: 'POST' });
      toast(action === 'refresh' ? '刷新完成' : action === 'activate' ? '已切换当前账号' : '已退出登录');
      await loadAccounts();
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); }
  }

export function openAddAccount() {
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

export async function openLoginModal(id) {
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

export const ACC_EVENT_LABEL = {
    created: '账号创建', login_start: '生成二维码', login_scanned: '已扫码',
    login_success: '登录成功', token_refresh: 'token 刷新', expiring: '即将过期',
    refresh_failed: '刷新失败', logout: '退出登录', activate: '切换当前账号',
  };
