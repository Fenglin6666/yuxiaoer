/* 鱼小二控制台 · 商品与知识（原生 ESM，无构建） */

import { $, $$, ITEM_STATUS, S, api, chip, closeModal, confirmAction, emptyBlock, esc, fmtTime, icon, money, openModal, orderStatus, pad, refreshGlobal, toast } from '../core.js';

  // =========================================================
  // Catalog / knowledge
  // =========================================================
export async function pageCatalog() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>商品与知识源</h2><p>在售商品可直接改价/下架；也可在「让小二做点什么」用一句话操作。</p></div>
        <div class="tabs"><button class="tab active" data-tab="items">商品</button><button class="tab" data-tab="knowledge">知识库</button></div>
      </div>
      <div id="catalogMain"><div class="loading-page"><span class="spinner"></span> 加载商品…</div></div>`;
    $$('.tabs [data-tab]').forEach((b) => b.onclick = () => { S.catalog.tab = b.dataset.tab; $$('.tabs [data-tab]').forEach((x) => x.classList.toggle('active', x === b)); renderCatalog(); });
    await loadCatalog();
  }

export async function loadCatalog() {
    const [items, sources] = await Promise.all([api('/items'), api('/knowledge/sources')]);
    S.catalog.items = items || []; S.catalog.sources = sources || [];
    renderCatalog();
  }

export function renderCatalog() {
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

export function renderItemCard(it) {
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

export async function openItemDetail(id) {
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

export function openCreateItemModal() {
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

export function openPublishModal(id) {
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

export function openPriceModal(id, it) {
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

export function openFloorDialog(id) {
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
