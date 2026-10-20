/* 鱼小二控制台 · 让小二做点什么（原生 ESM，无构建） */

import { $, $$, S, api, avatar, chip, closeModal, emptyBlock, esc, every, fmtTime, icon, money, navigate, nl2br, openModal, orderStatus, refreshGlobal, toast } from '../core.js';

  // =========================================================
  // Seller agent chat
  // =========================================================
export async function pageSeller() {
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

export async function loadSeller(scroll = false) {
    if (S.seller.busy) return; S.seller.busy = true;
    try {
      const data = await api('/seller/messages');
      S.seller.messages = data.messages || [];
      S.seller.pending = data.pending || [];
      renderSellerMessages(scroll);
      renderSellerSide();
    } finally { S.seller.busy = false; }
  }

export function renderSellerMessages(scroll = false) {
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

export function renderSellerCard(m, card) {
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

export function statusText(status) {
    return { pending: '待确认', confirmed: '已执行', cancelled: '已取消', expired: '已过期' }[status] || status;
  }

export function renderSellerSide() {
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

export async function uploadSellerImages(files) {
    const fd = new FormData();
    for (const file of files.slice(0, 9)) fd.append('files', file);
    const headers = S.accountId ? { 'X-Account-Id': S.accountId } : {};
    const response = await fetch('/api/media', { method: 'POST', body: fd, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || '图片上传失败');
    S.seller.images = [...S.seller.images, ...(data.paths || [])].slice(0, 9);
    renderSellerAttachments();
    toast(`已添加 ${(data.paths || []).length} 张图片`);
  }

export function renderSellerAttachments() {
    const el = $('#sellerAttachPreview'); if (!el) return;
    el.innerHTML = (S.seller.images || []).map((path, i) => {
      const name = String(path).split(/[\\/]/).pop();
      return `<span class="attach-chip">${icon('image')} ${esc(name)}<button data-rm-image="${i}" title="移除">${icon('x')}</button></span>`;
    }).join('');
    el.querySelectorAll('[data-rm-image]').forEach((b) => {
      b.onclick = () => { S.seller.images.splice(Number(b.dataset.rmImage), 1); renderSellerAttachments(); };
    });
  }

export async function sendSeller(textArg) {
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

export function openEditPublishModal(confirmationId) {
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

export async function resolveConfirmation(id, approve) {
    try {
      const res = await api(`/confirmations/${id}/${approve ? 'confirm' : 'cancel'}`, { method: 'POST' });
      toast(res.ok ? (approve ? '已执行' : '已取消') : '确认项已处理', res.ok ? 'ok' : 'warn');
      await loadSeller(true);
      await refreshGlobal();
    } catch (e) { toast(e.message, 'error'); }
  }
