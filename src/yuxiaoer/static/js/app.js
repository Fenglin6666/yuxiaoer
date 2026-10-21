/* 鱼小二控制台 · 入口（原生 ESM，无构建） */

import { $, ROUTE_META, S, clearTimers, closeModal, esc, icon, openAlertCenter, parseRoute, refreshGlobal, renderNav, toast } from './core.js?v=20261021-3';
import { initHub, refreshHub } from './hub.js?v=20261021-3';
import { pageAccounts } from './pages/accounts.js?v=20261021-3';
import { pageCatalog } from './pages/catalog.js?v=20261021-3';
import { pageInbox } from './pages/inbox.js?v=20261021-3';
import { pageNotify } from './pages/notify.js?v=20261021-3';
import { pageOps } from './pages/ops.js?v=20261021-3';
import { pageOrders } from './pages/orders.js?v=20261021-3';
import { pageOverview } from './pages/overview.js?v=20261021-3';
import { pageSeller } from './pages/seller.js?v=20261021-3';
import { pageSettings } from './pages/settings.js?v=20261021-3';

  async function renderRoute() {
    clearTimers();
    const route = parseRoute();
    S.route = route;
    const [title, subtitle] = ROUTE_META[route];
    document.title = `${title} · 鱼小二`;
    $('#pageTitle').textContent = title;
    $('#pageSubtitle').textContent = subtitle;
    renderNav();
    window.scrollTo(0, 0);
    const view = $('#view');
    view.className = `view view-${route}`;
    view.innerHTML = `<div class="loading-page"><span class="spinner"></span> 正在加载…</div>`;
    try {
      if (route === 'overview') await pageOverview();
      else if (route === 'inbox') await pageInbox();
      else if (route === 'seller') await pageSeller();
      else if (route === 'catalog') await pageCatalog();
      else if (route === 'orders') await pageOrders();
      else if (route === 'ops') await pageOps();
      else if (route === 'accounts') await pageAccounts();
      else if (route === 'notify') await pageNotify();
      else if (route === 'settings') await pageSettings();
    } catch (e) {
      view.innerHTML = `<div class="card pad"><div class="empty"><div class="empty-ico">${icon('alert')}</div><strong>页面加载失败</strong>${esc(e.message)}<div class="mt12"><button class="btn" onclick="location.reload()">重新加载</button></div></div></div>`;
      toast(e.message, 'error');
    }
  }

  // =========================================================
  // boot
  // =========================================================
  async function boot() {
    $('#brandMark').innerHTML = '<img src="/static/favicon.svg" alt="" style="width:100%;height:100%;border-radius:11px" />';
    $('#bellIcon').innerHTML = icon('bell');
    $('#alertBtn').onclick = openAlertCenter;
    $('#channelChip').onclick = () => { location.hash = '#/accounts'; };
    window.addEventListener('hashchange', renderRoute);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
    renderNav();
    await initHub();
    await refreshGlobal();
    setInterval(async () => { await refreshHub(); await refreshGlobal(); }, 30000);
    renderRoute();
  }

  boot();
