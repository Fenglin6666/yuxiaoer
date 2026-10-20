/* 鱼小二控制台 · 客服工作台（原生 ESM，无构建） */

import { $, $$, ACTION_LABEL, CATEGORY_LABEL, ITEM_STATUS, S, api, avatar, avatarClass, chip, clearTimers, emptyBlock, esc, every, icon, money, navigate, nl2br, orderStatus, refreshGlobal, toast } from '../core.js?v=20261021-2';
import { accountTabsHTML, bindAccountTabs } from '../hub.js?v=20261021-2';

  // =========================================================
  // Buyer experience
  // =========================================================
  // =========================================================
  // Inbox
  // =========================================================
export async function pageInbox() {
    clearTimers();
    $('#view').innerHTML = `
      <div class="page-toolbar">
        <div class="page-accounts" id="inboxAccounts"></div>
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
    $('#inboxAccounts').innerHTML = accountTabsHTML();
    bindAccountTabs($('#inboxAccounts'), async () => {
      S.inbox.id = null;
      await pageInbox();
      await refreshGlobal();
    });
    await loadInbox(true);
    every(() => { if (!document.hidden && !S.inbox.busy) loadInbox(false).catch(() => {}); }, 6000);
  }

export async function loadInbox(selectFirst = false) {
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

export function renderConvList() {
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

export async function loadConversation(id, withBusy = true) {
    if (!id) return;
    try {
      const d = await api(`/conversations/${id}`);
      S.inbox.detail = d;
      const conv = S.inbox.convs.find((c) => c.id === id);
      if (conv) { conv.unread_for_owner = 0; }
      renderThreadHead(); renderThreadBody(); renderContext(); renderConvList();
    } catch (e) { if (withBusy) toast(e.message, 'error'); }
  }

export function renderEmptyThread() {
    $('#threadHead').innerHTML = '';
    $('#threadBody').innerHTML = emptyBlock('选择一个会话', '左侧会话会实时更新', 'chat');
    $('#ctxPane').innerHTML = '';
  }

export function renderThreadHead() {
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

export function renderThreadBody() {
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

export function renderContext() {
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

export async function sendManualReply() {
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
