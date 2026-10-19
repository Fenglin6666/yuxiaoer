/* 鱼小二控制台 · 通知渠道（原生 ESM，无构建） */

import { $, S, api, chip, closeModal, confirmAction, emptyBlock, esc, icon, levelChip, openModal, pad, sleep, toast } from '../core.js';

  // =========================================================
  // Notification channels
  // =========================================================
export const NOTIFY_KINDS = {
    log: ['站内日志', 'activity'], wecom: ['企业微信', 'wechat'], bark: ['Bark', 'bell'],
    serverchan: ['Server酱', 'send'], ntfy: ['ntfy', 'bell'], telegram: ['Telegram', 'send'],
    pushplus: ['PushPlus', 'send'], gotify: ['Gotify', 'send'], generic: ['通用 Webhook', 'link'],
    email: ['邮箱 SMTP/IMAP', 'send'],
  };
export async function pageNotify() {
    $('#view').innerHTML = `
      <div class="page-head">
        <div><h2>一个告警，多渠道送达</h2><p>Bark / 企业微信 / Server酱 / ntfy / Telegram / PushPlus / Gotify / 邮箱 / 通用 Webhook；邮箱同时支持收指令。</p></div>
        <div class="btn-row"><button class="btn ghost" id="notifyEmailPoll">${icon('refresh')} 检查邮箱</button><button class="btn soft" id="notifyTestAlert">${icon('send')} 发测试告警</button><button class="btn" id="addChannel">${icon('bell')} 添加渠道</button><button class="btn ghost" id="notifyRefresh">${icon('refresh')}</button></div>
      </div>
      <div id="notifyMain"><div class="loading-page"><span class="spinner"></span> 读取通知渠道…</div></div>`;
    $('#addChannel').onclick = () => openChannelModal();
    $('#notifyRefresh').onclick = () => loadNotify();
    $('#notifyEmailPoll').onclick = async () => {
      try {
        const r = await api('/notify/email/poll', { method: 'POST' });
        if (r.ok === false) throw new Error(r.error || '检查邮箱失败');
        toast(`邮箱检查完成：收到 ${r.fetched || 0} 封，处理 ${r.processed || 0} 封`);
        await loadNotify();
      } catch (e) { toast(e.message, 'error'); }
    };
    $('#notifyTestAlert').onclick = async () => { try { await api('/notify/test', { method: 'POST', body: {} }); toast('测试告警已生成，正在投递'); await sleep(700); await loadNotify(); } catch (e) { toast(e.message, 'error'); } };
    await loadNotify();
  }

export async function loadNotify() {
    const [channels, logs] = await Promise.all([api('/notify/channels'), api('/notify/logs?limit=40')]);
    S.notify.channels = channels || [];
    S.notify.logs = logs || [];
    renderNotify();
  }

export function renderNotify() {
    const el = $('#notifyMain'); if (!el) return;
    const channels = S.notify.channels || [];
    const logs = S.notify.logs || [];
    const stats = S.system?.notify || {};
    el.innerHTML = `<div class="notify-layout">
      <div class="stack">
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('bell')} 渠道</div><div class="card-sub">${stats.enabled || channels.filter((c) => c.enabled).length} 个启用 · 当前告警会按 min_level 过滤</div></div>${chip(`${stats.sent || 0} 成功`, 'green')} ${chip(`${stats.failed || 0} 失败`, (stats.failed ? 'red' : 'gray'))}</div>
          <div class="channel-grid">
            ${channels.map((c) => renderChannelCard(c)).join('') || emptyBlock('还没有通知渠道', '至少保留一个站内日志渠道', 'bell')}
          </div>
          <div class="notice mt16">${icon('shield')} 站内日志渠道永远不需要外部网络；其余渠道在发送失败时会自动重试 3 次，并保留完整 error 日志。</div>
        </div>
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('activity')} 最近投递</div><div class="card-sub">每次告警 × 每个渠道 = 一条日志</div></div><button class="btn xs ghost" id="notifyLogsRefresh">${icon('refresh')}</button></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>渠道</th><th>告警</th><th>级别</th><th>状态</th><th>尝试</th><th>时间</th><th>错误</th></tr></thead><tbody>
            ${logs.length ? logs.map((l) => `<tr><td>${esc(l.channel_name || l.channel_id)}</td><td class="ord-id">${esc(l.alert_id || '—')}</td><td>${levelChip(l.level || 'P1')}</td><td>${chip(l.status === 'sent' ? '已送达' : l.status === 'failed' ? '失败' : '待发', l.status === 'sent' ? 'green' : l.status === 'failed' ? 'red' : 'amber')}</td><td>${l.attempts || 0}</td><td class="ord-sub">${esc(l.created_human || '')}</td><td class="ord-sub">${esc((l.error || '').slice(0, 80))}</td></tr>`).join('') : '<tr><td colspan="7"><div class="empty">暂无投递记录</div></td></tr>'}
          </tbody></table></div>
        </div>
      </div>
      <div class="stack">
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('spark')} 一个 Alert 的生命周期</div><div class="card-sub">告警中心 → 通知服务 → 渠道适配器</div></div></div>
          <div class="trace">
            <div class="trace-step"><span class="trace-dot">1</span><div class="trace-main"><strong>分级</strong><p>P0 强提醒 / P1 普通提醒 / P2 日报。渠道可设 min_level。</p></div></div>
            <div class="trace-step"><span class="trace-dot">2</span><div class="trace-main"><strong>分发</strong><p>启用渠道 + 级别过滤，每个渠道独立任务，不阻塞主链路。</p></div></div>
            <div class="trace-step"><span class="trace-dot">3</span><div class="trace-main"><strong>重试与留痕</strong><p>最多 3 次退避；发送结果落 notification_logs，可回看。</p></div></div>
          </div>
        </div>
        <div class="card pad">
          <div class="card-head"><div><div class="card-title">${icon('plug')} 环境变量快捷接入</div></div></div>
          <div class="turn-mini">
            <div class="kv"><span>企业微信</span><strong>WECOM_WEBHOOK</strong></div>
            <div class="kv"><span>Bark</span><strong>BARK_URL</strong></div>
            <div class="kv"><span>Server酱</span><strong>SERVERCHAN_KEY</strong></div>
            <div class="kv"><span>ntfy</span><strong>NTFY_URL / NTFY_TOPIC</strong></div>
          </div>
          <div class="notice mt12">${icon('shield')} 邮箱/渠道配置保存于本机 <span class="mono">data/yuxiaoer.db</span>，重启自动读取；删除数据库才会丢失。</div>
          <div class="notice mt12">${icon('alert')} 修改环境变量后重启服务；也可以在本页直接添加渠道并点测试。</div>
        </div>
      </div>
    </div>`;
    el.querySelectorAll('[data-ch-toggle]').forEach((b) => { b.onclick = () => toggleChannel(b.dataset.chToggle); });
    el.querySelectorAll('[data-ch-test]').forEach((b) => { b.onclick = () => testChannel(b.dataset.chTest); });
    el.querySelectorAll('[data-ch-edit]').forEach((b) => { b.onclick = () => openChannelModal(b.dataset.chEdit); });
    el.querySelectorAll('[data-ch-del]').forEach((b) => { b.onclick = () => deleteChannel(b.dataset.chDel); });
    const lr = $('#notifyLogsRefresh'); if (lr) lr.onclick = loadNotify;
  }

export function renderChannelCard(c) {
    const kind = NOTIFY_KINDS[c.kind] || [c.kind, 'bell'];
    return `<div class="channel-card ${c.enabled ? 'on' : ''}">
      <div class="channel-top"><span class="channel-ico">${icon(kind[1])}</span><div class="grow"><strong>${esc(c.name)}</strong><small>${esc(kind[0])} · 最低 ${esc(c.min_level)}</small></div><button class="toggle ${c.enabled ? 'checked' : ''}" data-ch-toggle="${esc(c.id)}" title="启用/停用"><span></span></button></div>
      <div class="channel-config">${esc(c.config_summary || '无需配置')}</div>
      <div class="channel-actions"><button class="btn xs ghost" data-ch-test="${esc(c.id)}">${icon('send')} 测试</button><button class="btn xs ghost" data-ch-edit="${esc(c.id)}">${icon('edit')} 编辑</button>${c.id !== 'ch_log' ? `<button class="btn xs ghost" data-ch-del="${esc(c.id)}">${icon('trash')} 删除</button>` : ''}</div>
    </div>`;
  }

export async function toggleChannel(id) {
    const c = S.notify.channels.find((x) => x.id === id); if (!c) return;
    try {
      await api(`/notify/channels/${id}`, { method: 'PUT', body: { kind: c.kind, name: c.name, config: c.config, enabled: !c.enabled, min_level: c.min_level } });
      await loadNotify();
    } catch (e) { toast(e.message, 'error'); }
  }

export async function testChannel(id) {
    try {
      const r = await api(`/notify/channels/${id}/test`, { method: 'POST' });
      if (r.status && r.status !== 'sent') throw new Error(r.error || '发送失败');
      toast('测试消息已送达'); await loadNotify();
    } catch (e) { toast(e.message, 'error'); await loadNotify(); }
  }

export async function deleteChannel(id) {
    if (!(await confirmAction({ title: '删除通知渠道', message: '删除后该渠道不会再收到告警，历史投递日志保留。', confirmText: '删除', danger: true }))) return;
    try { await api(`/notify/channels/${id}`, { method: 'DELETE' }); toast('已删除'); await loadNotify(); } catch (e) { toast(e.message, 'error'); }
  }

export function openChannelModal(editId = null) {
    const c = editId ? S.notify.channels.find((x) => x.id === editId) : null;
    const cfg = (c && c.config) || {};
    const kind = c ? c.kind : 'bark';
    openModal({
      title: c ? '编辑通知渠道' : '添加通知渠道', wide: true,
      body: `<div class="form-grid">
        <div class="field"><label>渠道类型</label><select class="input" id="chKind">${Object.entries(NOTIFY_KINDS).map(([k, v]) => `<option value="${k}" ${k === kind ? 'selected' : ''}>${esc(v[0])}</option>`).join('')}</select></div>
        <div class="field"><label>名称</label><input class="input" id="chName" value="${esc(c ? c.name : '')}" placeholder="例如：我的 Bark" /></div>
        <div class="field"><label>最低级别</label><select class="input" id="chLevel">${['P0', 'P1', 'P2'].map((l) => `<option ${((c && c.min_level) || 'P1') === l ? 'selected' : ''}>${l}</option>`).join('')}</select><div class="hint">选 P1 会收到 P0+P1；P2 只收 P2。</div></div>
        <div class="field"><label>启用</label><label class="toggle"><input type="checkbox" id="chEnabled" ${!c || c.enabled ? 'checked' : ''}/><span></span></label></div>
      </div>
      <div class="divider"></div>
      <div id="chConfigFields"></div>
      <div class="notice mt12">${icon('shield')} 凭据只保存在本机 SQLite；测试与正式发送使用同一套适配器。</div>`,
      footer: `<button class="btn ghost" id="chCancel">取消</button><button class="btn primary" id="chSave">保存渠道</button>`,
    });
    const renderFields = () => {
      const k = $('#chKind').value;
      let html = '';
      if (k === 'log') html = '<div class="notice">站内日志渠道无需外部配置。</div>';
      else if (k === 'email') {
        html = `<div class="notice mb12">${icon('send')} SMTP 用来发告警/回复；IMAP 用来收店主的邮件指令。只有「允许发件人」发来的邮件会执行。</div>
          <div class="section-title">SMTP 发件</div>
          <div class="form-grid">
            <div class="field"><label>SMTP Host</label><input class="input" id="emSmtpHost" value="${esc(cfg.smtp_host || '')}" placeholder="smtp.qq.com" /></div>
            <div class="field"><label>SMTP 端口</label><input class="input" id="emSmtpPort" type="number" value="${esc(cfg.smtp_port || 465)}" /></div>
            <div class="field"><label>SMTP 账号</label><input class="input" id="emSmtpUser" value="${esc(cfg.smtp_user || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>SMTP 密码/授权码</label><input class="input" id="emSmtpPass" type="password" value="${esc(cfg.smtp_password || '')}" /></div>
            <div class="field"><label>发件地址</label><input class="input" id="emFrom" value="${esc(cfg.from_addr || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>收件地址（告警/回复）</label><input class="input" id="emTo" value="${esc(cfg.to_addr || '')}" placeholder="owner@example.com" /></div>
            <div class="field"><label>SMTP SSL</label><label class="toggle"><input type="checkbox" id="emSmtpSsl" ${cfg.smtp_ssl === false ? '' : 'checked'}/><span></span></label></div>
          </div>
          <div class="section-title mt16">IMAP 收件</div>
          <div class="form-grid">
            <div class="field"><label>IMAP Host</label><input class="input" id="emImapHost" value="${esc(cfg.imap_host || '')}" placeholder="imap.qq.com" /></div>
            <div class="field"><label>IMAP 端口</label><input class="input" id="emImapPort" type="number" value="${esc(cfg.imap_port || 993)}" /></div>
            <div class="field"><label>IMAP 账号</label><input class="input" id="emImapUser" value="${esc(cfg.imap_user || '')}" placeholder="bot@example.com" /></div>
            <div class="field"><label>IMAP 密码/授权码</label><input class="input" id="emImapPass" type="password" value="${esc(cfg.imap_password || '')}" /></div>
            <div class="field"><label>邮箱文件夹</label><input class="input" id="emFolder" value="${esc(cfg.imap_folder || 'INBOX')}" /></div>
            <div class="field"><label>IMAP SSL</label><label class="toggle"><input type="checkbox" id="emImapSsl" ${cfg.imap_ssl === false ? '' : 'checked'}/><span></span></label></div>
            <div class="field" style="grid-column:1/-1"><label>允许发件人（逗号/换行分隔）</label><input class="input" id="emAllowed" value="${esc(cfg.allowed_senders || '')}" placeholder="owner@example.com" /><div class="hint">必须配置；只有这些邮箱能通过邮件让 Agent 执行上架/改价/下架等操作。</div></div>
          </div>`;
      } else {
        html = `<div class="form-grid"><div class="field"><label>服务地址 / URL</label><input class="input" id="chUrl" value="${esc(cfg.url || '')}" placeholder="https://..." /></div><div class="field"><label>Token / Key</label><input class="input" id="chToken" value="${esc(cfg.token || '')}" placeholder="可选" /></div><div class="field"><label>Topic / Chat ID</label><input class="input" id="chTopic" value="${esc(cfg.topic || cfg.chat_id || '')}" placeholder="ntfy topic / Telegram chat_id" /></div></div>`;
      }
      $('#chConfigFields').innerHTML = html;
    };
    $('#chKind').onchange = renderFields; renderFields();
    $('#chCancel').onclick = closeModal;
    $('#chSave').onclick = async () => {
      const k = $('#chKind').value;
      const config = {};
      if (k === 'email') {
        config.smtp_host = ($('#emSmtpHost')?.value || '').trim();
        config.smtp_port = Number($('#emSmtpPort')?.value) || 465;
        config.smtp_user = ($('#emSmtpUser')?.value || '').trim();
        config.smtp_password = $('#emSmtpPass')?.value || '';
        config.smtp_ssl = Boolean($('#emSmtpSsl')?.checked);
        config.from_addr = ($('#emFrom')?.value || '').trim();
        config.to_addr = ($('#emTo')?.value || '').trim();
        config.imap_host = ($('#emImapHost')?.value || '').trim();
        config.imap_port = Number($('#emImapPort')?.value) || 993;
        config.imap_user = ($('#emImapUser')?.value || '').trim();
        config.imap_password = $('#emImapPass')?.value || '';
        config.imap_folder = ($('#emFolder')?.value || 'INBOX').trim();
        config.imap_ssl = Boolean($('#emImapSsl')?.checked);
        config.allowed_senders = ($('#emAllowed')?.value || '').trim();
      } else if (k !== 'log') {
        const url = ($('#chUrl')?.value || '').trim();
        const token = ($('#chToken')?.value || '').trim();
        const topic = ($('#chTopic')?.value || '').trim();
        if (url) config.url = url;
        if (token) config.token = token;
        if (topic) { if (k === 'ntfy') config.topic = topic; else config.chat_id = topic; }
      }
      const payload = { kind: k, name: ($('#chName').value || '').trim() || (NOTIFY_KINDS[k] || ['渠道'])[0], config, enabled: $('#chEnabled').checked, min_level: $('#chLevel').value };
      try {
        if (editId) await api(`/notify/channels/${editId}`, { method: 'PUT', body: payload });
        else await api('/notify/channels', { method: 'POST', body: payload });
        toast('渠道已保存'); closeModal(); await loadNotify();
      } catch (e) { toast(e.message, 'error'); }
    };
  }
