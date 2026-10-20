/* 鱼小二控制台 · 总览（原生 ESM，无构建） */

import { $, $$, S, api, avatar, avatarClass, chip, clampPct, compactPayload, emptyBlock, esc, every, fmtTime, icon, metricCard, money, navigate, openAlertCenter, orderStatus, pad, refreshGlobal, toast } from '../core.js?v=20261021-2';

  // =========================================================
  // Overview
  // =========================================================
export async function pageOverview() {
    const [ov, events] = await Promise.all([api('/overview'), api('/events?limit=7')]);
    renderOverview(ov, events);
    every(async () => {
      if (document.hidden) return;
      try { await refreshOverview(); } catch (e) { /* noop */ }
    }, 9000);
  }

export async function refreshOverview() {
    if (S.route !== 'overview') return;
    const [ov, events] = await Promise.all([api('/overview'), api('/events?limit=7')]);
    if (S.route === 'overview') renderOverview(ov, events);
  }

export function renderOverview(ov, events) {
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

export function jobIcon(name) { return { heartbeat: 'activity', link_check: 'link', polish: 'spark', daily_report: 'report' }[name] || 'clock'; }
