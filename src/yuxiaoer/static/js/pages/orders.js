/* 鱼小二控制台 · 订单履约（原生 ESM，无构建） */

import { $, $$, S, api, closeModal, confirmAction, emptyBlock, esc, every, fmtTime, icon, money, openModal, orderStatus, pad, refreshGlobal, toast } from '../core.js?v=20261021-3';

  // =========================================================
  // Orders
  // =========================================================
export async function pageOrders() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>订单流水与履约</h2><p>虚拟商品自动发货；实物回填单号后自动通知买家。</p></div>
        <div class="btn-row"><button class="btn soft" id="ordersRefresh">${icon('refresh')} 刷新</button></div>
      </div>
      <div class="order-stats" id="orderStats"></div>
      <div class="card pad">
        <div class="card-head order-toolbar"><div class="filter-bar" id="orderFilters">
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

export async function loadOrders() {
    const orders = await api('/orders');
    S.orders.orders = orders || [];
    renderOrders();
  }

export function renderOrders() {
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

export async function resendOrder(id) {
    if (!(await confirmAction({ title: '补发卡券', message: '会复用订单原卡券或从库存取一张新卡，立即发送给买家。', confirmText: '补发' }))) return;
    try { await api(`/orders/${id}/resend`, { method: 'POST' }); toast('已补发'); await loadOrders(); } catch (e) { toast(e.message, 'error'); }
  }

export async function openOrderDetail(orderId) {
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

export function openShipDialog(orderId) {
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

export function openRefundDialog(orderId) {
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
