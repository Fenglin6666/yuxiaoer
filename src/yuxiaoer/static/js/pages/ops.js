/* 鱼小二控制台 · 观测/回放/评测（原生 ESM，无构建） */

import { $, $$, CATEGORY_LABEL, S, api, barChart, chip, compactPayload, emptyBlock, esc, every, fmtTime, icon, metricCard, money, nl2br, pad, sessionMeta, toast } from '../core.js?v=20261021-3';

  // =========================================================
  // Ops / replay / eval
  // =========================================================
export async function pageOps() {
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

export function renderOps() {
    const m = S.ops.metrics || {}; const t = m.today || {}; const h = m.health || {};
    const session = sessionMeta(S.system && S.system.account ? S.system.account : {});
    const series = m.series || [];
    const chart = barChart(series);
    const weekConversations = series.reduce((sum, d) => sum + (Number(d.conversations) || 0), 0);
    const weekOrders = series.reduce((sum, d) => sum + (Number(d.orders) || 0), 0);
    const view = $('#view');
    view.innerHTML = `
      <div class="page-head"><div><h2>指标、轨迹与回归</h2><p>L0 系统活着吗 · L1 客服称职吗 · L2 生意变好了吗。北极星：询单转化率。</p></div><div class="btn-row"><button class="btn sm ghost" id="opsRefresh">${icon('refresh')} 刷新</button></div></div>
      <div class="ops-metrics">
        ${metricCard('L0 · 通道', (S.system && S.system.channel && S.system.channel.online) ? '在线' : '离线', `登录态 ${session.short} · 事件积压 ${S.system?.events?.backlog ?? 0} · 队列 ${S.system?.queue?.depth ?? 0}`, 'activity', '')}
        ${metricCard('L0 · 工具错误率', `${h.tool_error_rate || 0}%`, `${h.tool_calls || 0} 次调用 / 24h`, 'plug', 'amber')}
        ${metricCard('L1 · 首响 P95', `${t.first_response_p95 || 0}s`, `P50 ${t.first_response_p50 || 0}s · 回复率 ${t.answer_rate || 0}%`, 'clock', 'coral')}
        ${metricCard('L2 · 询单转化', `${t.conversion_rate || 0}%`, `${t.paid_orders || 0} 单 · GMV ${money(t.gmv || 0)}`, 'spark', 'purple')}
      </div>
      <div class="overview-grid">
        <div class="card chart-card"><div class="card-head"><div><div class="card-title">${icon('activity')} 7 日趋势</div><div class="card-sub">会话 vs 成交 · 合计 ${weekConversations} 次咨询 / ${weekOrders} 单成交</div></div><div class="legend"><span><i class="g"></i>咨询</span><span><i class="c"></i>成交</span></div></div>${chart}</div>
        <div class="card pad"><div class="card-head"><div><div class="card-title">${icon('shield')} 运行健康</div><div class="card-sub">进程内服务与护栏</div></div></div>
          <div class="sys-row"><span>账号登录态</span><strong style="color:${session.tone === 'danger' ? 'var(--danger)' : session.tone === 'warn' ? 'var(--amber)' : 'var(--brand)'}">${esc(session.label)}</strong></div>
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

const EVENT_GROUPS = {
  'channel.ws_state': { group: 'channel', label: '通道状态', icon: 'plug' },
  'account.synced': { group: 'account', label: '账号同步', icon: 'refresh' },
  'account.event': { group: 'account', label: '账号事件', icon: 'user' },
  'patrol.run': { group: 'patrol', label: '值守任务', icon: 'clock' },
  'patrol.polished': { group: 'patrol', label: '擦亮完成', icon: 'spark' },
  'patrol.schedule_updated': { group: 'patrol', label: '排期更新', icon: 'clock' },
  'alert.created': { group: 'alert', label: '告警', icon: 'alert' },
};
const EVENT_FILTERS = [
  ['focus', '重点'],
  ['all', '全部'],
  ['account', '账号'],
  ['channel', '通道'],
  ['patrol', '值守'],
  ['alert', '告警'],
];
const TASK_LABELS = { heartbeat: '心跳', link_check: '链接检查', polish: '每日擦亮', daily_report: '每日日报' };
const WS_STATES = { connected: '已连接', connecting: '连接中', disconnected: '已断开', reconnecting: '重连中', online: '在线', offline: '离线' };
const EVENT_STATUS = { done: '完成', ok: '成功', failed: '失败', error: '错误', pending: '等待', running: '进行中', sent: '已发送', info: '记录' };

function eventMeta(event) {
  const topic = String(event.topic || 'event');
  return EVENT_GROUPS[topic] || { group: 'other', label: topic, icon: 'activity' };
}

function eventTime(event) {
  return fmtTime(event.created_at, true) || event.created_human || '—';
}

function eventSummary(event) {
  const p = event.payload || {};
  switch (event.topic) {
    case 'channel.ws_state':
      return `账号 ${String(p.account_id || '—').slice(-8)} · ${WS_STATES[p.state] || p.state || '状态未知'}`;
    case 'account.synced': {
      const c = p.counts || {};
      const items = p.items || {};
      const orders = p.orders || {};
      const profile = p.profile || {};
      const name = profile.nickname ? ` · ${profile.nickname}` : '';
      return `商品 ${items.seen ?? c.items ?? 0} 条（新增 ${items.created ?? 0} / 更新 ${items.updated ?? 0}） · 订单 ${orders.fetched ?? c.orders ?? 0}${name}`;
    }
    case 'account.event':
      return `${p.event || '账号事件'}${p.account_id ? ` · ${String(p.account_id).slice(-8)}` : ''}${p.state ? ` · ${p.state}` : ''}`;
    case 'patrol.run':
      return `${TASK_LABELS[p.name] || p.name || '任务'} · ${p.ok ? '成功' : '失败'}${p.manual ? ' · 手动' : ''}${p.text ? ` · ${p.text}` : ''}`;
    case 'patrol.polished':
      return `本轮擦亮 ${p.count ?? 0} 件商品`;
    case 'patrol.schedule_updated':
      return `${TASK_LABELS[p.name] || p.name || '任务'} · 下次 ${p.next_run_at ? fmtTime(p.next_run_at, true) : '待定'}`;
    case 'alert.created':
      return `[${p.level || 'P?'}] ${p.title || '告警'}${p.body ? ` · ${p.body}` : ''}`;
    default:
      return compactPayload(p);
  }
}

function eventFacts(event) {
  const p = event.payload || {};
  const facts = [];
  const push = (key, value) => { if (value !== undefined && value !== null && value !== '') facts.push([key, value]); };
  switch (event.topic) {
    case 'channel.ws_state': push('账号', p.account_id); push('状态', WS_STATES[p.state] || p.state); break;
    case 'account.synced': {
      const items = p.items || {}; const orders = p.orders || {}; const profile = p.profile || {};
      push('昵称', profile.nickname); push('平台 ID', profile.platform_user_id);
      push('商品', `${items.seen ?? 0} 条 / 新增 ${items.created ?? 0} / 更新 ${items.updated ?? 0}`);
      push('订单', `${orders.fetched ?? 0} 条 / 新增 ${orders.inserted ?? 0} / 更新 ${orders.updated ?? 0}`);
      if (Array.isArray(p.errors) && p.errors.length) push('错误', p.errors.join('；'));
      break;
    }
    case 'patrol.run': push('任务', TASK_LABELS[p.name] || p.name); push('结果', p.ok ? '成功' : '失败'); push('触发', p.manual ? '手动' : '定时'); push('下次', p.next_run_at ? fmtTime(p.next_run_at, true) : ''); break;
    case 'alert.created': push('级别', p.level); push('类型', p.kind); push('标题', p.title); push('内容', p.body); break;
    case 'account.event': push('账号', p.account_id); push('事件', p.event); push('通道', p.channel); break;
    case 'patrol.schedule_updated': push('任务', TASK_LABELS[p.name] || p.name); push('下次', p.next_run_at ? fmtTime(p.next_run_at, true) : ''); break;
    default: break;
  }
  return facts;
}

function filterEvents(events) {
  const filter = S.ops.eventFilter || 'focus';
  if (filter === 'focus') {
    return events.filter((e) => !['channel.ws_state', 'patrol.schedule_updated'].includes(e.topic));
  }
  if (filter === 'all') return events;
  return events.filter((e) => eventMeta(e).group === filter);
}

function mergeEvents(events) {
  if (S.ops.eventMerge === false) return events.map((event) => ({ ...event, count: 1 }));
  const merged = [];
  for (const event of events) {
    const account = (event.payload || {}).account_id || (event.payload || {}).profile?.platform_user_id || '';
    const key = `${event.topic}:${account}:${(event.payload || {}).state || ''}`;
    const previous = merged[merged.length - 1];
    if (previous && previous._key === key && event.topic === 'channel.ws_state') {
      previous.count += 1;
      previous.last_at = event.created_at;
      continue;
    }
    merged.push({ ...event, count: 1, _key: key });
  }
  return merged;
}

function renderEventRow(event) {
  const meta = eventMeta(event);
  const payload = JSON.stringify(event.payload || {}, null, 2);
  const facts = eventFacts(event);
  const status = String(event.status || 'done');
  const statusTone = ['done', 'ok', 'sent'].includes(status) ? 'green' : ['failed', 'error'].includes(status) ? 'red' : 'amber';
  const statusLabel = EVENT_STATUS[status] || status;
  const count = event.count > 1 ? `<span class="event-count">×${event.count}</span>` : '';
  const last = event.count > 1 && event.last_at ? ` · 最近 ${fmtTime(event.last_at, true)}` : '';
  return `<details class="event-row">
    <summary>
      <time>${esc(eventTime(event))}</time>
      <span class="event-mark">${icon(meta.icon || 'activity')}</span>
      <span class="event-main">
        <span class="event-kind">${esc(meta.label)}${count}</span>
        <span class="event-summary">${esc(eventSummary(event))}</span>
        ${last ? `<span class="event-last">${esc(last)}</span>` : ''}
      </span>
      <span class="chip ${statusTone}">${esc(statusLabel)}</span>
      <span class="event-chevron">${icon('arrow')}</span>
    </summary>
    <div class="event-detail">
      ${facts.length ? `<div class="event-facts">${facts.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(String(v))}</strong></div>`).join('')}</div>` : ''}
      <details class="event-raw"><summary>原始 JSON</summary><pre>${esc(payload)}</pre></details>
    </div>
  </details>`;
}

export function renderOpsPanel() {
    const panel = $('#opsPanel'); if (!panel) return;
    if (S.ops.tab === 'replay') { renderReplayPanel(); return; }
    if (S.ops.tab === 'eval') { renderEvalPanel(); return; }
    const filtered = filterEvents(S.ops.events);
    const events = mergeEvents(filtered);
    const activeFilter = S.ops.eventFilter || 'focus';
    const failed = S.ops.events.filter((e) => ['failed', 'error'].includes(String(e.status))).length;
    const filterHtml = EVENT_FILTERS.map(([key, label]) => {
      const count = key === 'all' ? S.ops.events.length : key === 'focus'
        ? S.ops.events.filter((e) => !['channel.ws_state', 'patrol.schedule_updated'].includes(e.topic)).length
        : S.ops.events.filter((e) => eventMeta(e).group === key).length;
      return `<button class="event-filter ${activeFilter === key ? 'active' : ''}" data-event-filter="${key}">${label}<span>${count}</span></button>`;
    }).join('');
    panel.innerHTML = `<div class="card pad event-panel">
      <div class="card-head">
        <div><div class="card-title">${icon('activity')} 事件流</div><div class="card-sub">按时间倒序 · 点击一行展开上下文 · 原始 JSON 收在详情里</div></div>
        <div class="event-actions"><label class="event-merge"><input type="checkbox" id="eventMerge" ${S.ops.eventMerge === false ? '' : 'checked'}> 合并连续状态</label><button class="btn xs ghost" id="eventsRefresh">${icon('refresh')}</button></div>
      </div>
      <div class="event-overview">
        <div><small>窗口事件</small><strong>${S.ops.events.length}</strong></div>
        <div><small>当前视图</small><strong>${events.length}</strong></div>
        <div><small>失败</small><strong class="${failed ? 'bad' : ''}">${failed}</strong></div>
        <div><small>时间范围</small><strong>${S.ops.events.length ? `${esc(eventTime(S.ops.events[S.ops.events.length - 1]))} — ${esc(eventTime(S.ops.events[0]))}` : '—'}</strong></div>
      </div>
      <div class="event-filters">${filterHtml}</div>
      <div class="event-table">${events.map(renderEventRow).join('') || emptyBlock('当前筛选下暂无事件', '切换筛选或刷新事件流', 'activity')}</div>
    </div>`;
    $$('[data-event-filter]').forEach((button) => {
      button.onclick = () => { S.ops.eventFilter = button.dataset.eventFilter; renderOpsPanel(); };
    });
    const merge = $('#eventMerge');
    if (merge) merge.onchange = () => { S.ops.eventMerge = merge.checked; renderOpsPanel(); };
    $('#eventsRefresh').onclick = async () => { S.ops.events = await api('/events?limit=60'); renderOpsPanel(); };
  }

export async function renderReplayPanel() {
    const panel = $('#opsPanel'); if (!panel) return;
    panel.innerHTML = `<div class="card pad"><div class="replay-layout"><div class="replay-sessions">${S.ops.sessions.map((s) => `<div class="rs-item ${s.id === S.ops.sessionId ? 'active' : ''}" data-session="${esc(s.id)}"><strong>${esc(s.buyer_nick || '买家')} · ${esc(s.item_title || '—')}</strong><small>${esc(s.last_at_human || '')} · ${s.message_count || 0} 消息 / ${s.turn_count || 0} 轮</small></div>`).join('') || emptyBlock('暂无会话', '', 'chat')}</div><div class="replay-trace" id="replayTrace">${renderTraceHtml()}</div></div></div>`;
    panel.querySelectorAll('[data-session]').forEach((el) => { el.onclick = async () => { S.ops.sessionId = el.dataset.session; S.ops.trace = await api(`/replay/${S.ops.sessionId}`); renderReplayPanel(); }; });
    const exportBtn = $('#exportTrace'); if (exportBtn) exportBtn.onclick = () => downloadTrace();
  }

export function renderTraceHtml() {
    const t = S.ops.trace;
    if (!t) return emptyBlock('选择一个会话', '左侧列表来自真实消息与 turns', 'activity');
    const conv = t.conversation || {}; const item = t.item; const buyer = t.buyer;
    return `<div class="flex-between mb12"><div><strong style="font-size:13px">${esc(buyer?.nick || '买家')} · ${esc(item?.title || '无商品')}</strong><div class="tiny muted">${esc(conv.session_id || '')} · 创建 ${esc(fmtTime(conv.created_at, true))}</div></div><button class="btn xs ghost" id="exportTrace">${icon('download')} 导出轨迹</button></div><div class="replay-timeline">${(t.timeline || []).map((x) => `<div class="rt-item ${esc(x.type)}"><div class="rt-head"><strong>${esc(x.title)}</strong><time>${esc(fmtTime(x.ts))}</time></div><div class="rt-text">${nl2br(String(x.text || '').slice(0, 600))}</div>${x.type === 'tool' || x.type === 'event' ? `<div class="rt-json">${esc(compactPayload(x.meta))}</div>` : ''}</div>`).join('')}</div>`;
  }

export function downloadTrace() {
    const blob = new Blob([JSON.stringify(S.ops.trace, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = `yuxiaoer-replay-${S.ops.sessionId}.json`; a.click(); URL.revokeObjectURL(url);
  }

export function renderEvalPanel() {
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

export async function runEval() {
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
