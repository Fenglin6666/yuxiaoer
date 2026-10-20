/* 鱼小二控制台 · 设置（原生 ESM，无构建） */

import { $, $$, S, api, chip, esc, fmtTime, icon, navigate, pad, refreshGlobal, toast } from '../core.js';

export async function pageSettings() {
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

export async function saveSettings() {
    const values = {
      floor_discount_pct: Number($('#setFloor').value),
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
