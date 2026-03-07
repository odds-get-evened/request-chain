'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────
const BASE = 'http://127.0.0.1:5000';
const TX_TYPE_LABELS = ['COINBASE', 'REQUEST', 'RELEASE', 'TRANSFER', 'BUYOUT'];
const TX_TYPE_COLORS = ['#ffd700', '#58a6ff', '#3fb950', '#bc8cff', '#d29922'];
const TX_BADGE_CLASS = ['coinbase', 'request', 'release', 'transfer', 'buyout'];

// ── State ─────────────────────────────────────────────────────────────────────
let _state = null;          // last full payload from backend
let _batch = [];            // [{action, uid}]
let _logFilters = new Set(['block', 'tx', 'network', 'system']);
let _selectedItem = null;   // uid of item currently in detail panel

// ── Charts ────────────────────────────────────────────────────────────────────
let sparklineChart  = null;
let donutChart      = null;
let growthChart     = null;
let txsChart        = null;
let allocChart      = null;

// ─────────────────────────────────────────────────────────────────────────────
// API helper
// ─────────────────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  opts = Object.assign({ method: 'GET' }, opts);
  opts.method = opts.method.toUpperCase();
  if (opts.method === 'POST') {
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers);
    if (!('body' in opts)) opts.body = JSON.stringify({});
  }
  const res = await fetch(BASE + path, opts);
  return res.json();
}

function el(id) { return document.getElementById(id); }
function qs(sel) { return document.querySelector(sel); }

// ─────────────────────────────────────────────────────────────────────────────
// Charts init
// ─────────────────────────────────────────────────────────────────────────────
function initCharts() {
  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 11;

  // Balance sparkline
  sparklineChart = new Chart(el('balance-sparkline').getContext('2d'), {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#ffd700', backgroundColor: 'rgba(255,215,0,0.1)', fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5 }] },
    options: {
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
      responsive: false,
    }
  });

  // Donut chart (tx type distribution)
  donutChart = new Chart(el('donut-chart').getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: TX_TYPE_LABELS,
      datasets: [{ data: [0, 0, 0, 0, 0], backgroundColor: TX_TYPE_COLORS, borderWidth: 1, borderColor: '#1c2333' }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 8, font: { size: 10 } } } },
      cutout: '60%',
    }
  });

  // Chain growth line chart
  growthChart = new Chart(el('growth-chart').getContext('2d'), {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'Blocks', data: [], borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)', fill: true, tension: 0.2, pointRadius: 2, borderWidth: 1.5 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: false }, ticks: { maxTicksLimit: 8 } },
        y: { beginAtZero: true, title: { display: false } },
      }
    }
  });

  // Txs per block bar chart
  txsChart = new Chart(el('txs-chart').getContext('2d'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'Txs', data: [], backgroundColor: '#1f4e8c', borderColor: '#58a6ff', borderWidth: 1 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: 'Block' } },
        y: { beginAtZero: true, title: { display: true, text: 'Transactions' } },
      }
    }
  });

  // Alloc pie chart
  allocChart = new Chart(el('alloc-chart').getContext('2d'), {
    type: 'pie',
    data: { labels: ['Reserved', 'Available'], datasets: [{ data: [0, 0], backgroundColor: ['#f85149', '#3fb950'], borderWidth: 1, borderColor: '#1c2333' }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 8 } } },
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Status bar
// ─────────────────────────────────────────────────────────────────────────────
function updateStatusBar(payload) {
  const { summary, stats, node } = payload;
  if (!summary || !node) return;

  el('sb-blocks').textContent = summary.chain_length;
  el('sb-peers').textContent  = (payload.peers || []).length;
  el('sb-mempool').textContent = summary.mempool_size || 0;
  el('sb-port').textContent   = `P2P: ${node.port}`;
  el('sb-pubkey').textContent = node.pubkey_short || '—';
  el('sb-pubkey').title       = node.pubkey_hex || '';
  el('sb-balance').textContent = node.balance != null ? node.balance.toFixed(1) : '0';
  el('ni-pubkey').textContent = node.pubkey_short || '—';
  el('ni-pubkey').title       = node.pubkey_hex || '';
  el('ni-port').textContent   = node.port;

  const integrityEl = el('sb-integrity');
  integrityEl.textContent = stats.integrity_ok ? 'OK' : 'CORRUPT';
  integrityEl.className   = 'status-item__value ' + (stats.integrity_ok ? 'status-ok' : 'status-bad');

  // Mining indicator
  const mineBtn = el('btn-mine');
  const spinner = el('mining-spinner');
  if (summary.mining_in_progress) {
    mineBtn.disabled = true;
    spinner.classList.remove('hidden');
  } else {
    mineBtn.disabled = false;
    spinner.classList.add('hidden');
  }
  el('chk-auto-mine').checked = !!summary.auto_mining;
}

// ─────────────────────────────────────────────────────────────────────────────
// Balance sparkline
// ─────────────────────────────────────────────────────────────────────────────
function updateSparkline(history) {
  if (!history || history.length === 0) return;
  const labels = history.map(h => '');
  const data   = history.map(h => h[1]);
  sparklineChart.data.labels = labels;
  sparklineChart.data.datasets[0].data = data;
  sparklineChart.update('none');
}

// ─────────────────────────────────────────────────────────────────────────────
// Charts
// ─────────────────────────────────────────────────────────────────────────────
function updateCharts(payload) {
  const { summary, stats } = payload;
  if (!summary) return;

  // Donut: tx type counts
  const counts = summary.tx_type_counts || {};
  donutChart.data.datasets[0].data = [counts[0]||0, counts[1]||0, counts[2]||0, counts[3]||0, counts[4]||0];
  donutChart.update('none');

  // Chain growth
  growthChart.data.labels = (summary.block_indexes || []).map(i => `#${i}`);
  growthChart.data.datasets[0].data = (summary.block_indexes || []).map((_, i) => i + 1);
  growthChart.update('none');

  // Txs per block bar
  txsChart.data.labels = (summary.block_indexes || []).map(i => `#${i}`);
  txsChart.data.datasets[0].data = summary.txs_per_block || [];
  txsChart.update();

  // Alloc pie
  allocChart.data.datasets[0].data = [summary.allocated_count, summary.available_count];
  allocChart.update();
}

// ─────────────────────────────────────────────────────────────────────────────
// Heat map (D3)
// ─────────────────────────────────────────────────────────────────────────────
function updateHeatmap(items) {
  const container = el('heatmap');
  const emptyMsg  = el('heatmap-empty');

  if (!items) return;
  const allItems = [...(items.reserved || []), ...(items.available || [])];

  if (allItems.length === 0) {
    container.innerHTML = '';
    emptyMsg.classList.remove('hidden');
    return;
  }
  emptyMsg.classList.add('hidden');

  const maxDemand = Math.max(...allItems.map(d => d.demand), 1);

  // Color scale: blue (cold) → green → yellow → red (hot)
  const colorScale = d3.scaleSequential()
    .domain([0, maxDemand])
    .interpolator(d3.interpolateRgbBasis(['#2563eb', '#16a34a', '#ca8a04', '#dc2626']));

  // Size scale: base size 72px, grows with value
  const maxVal = Math.max(...allItems.map(d => d.value), 10);
  const sizeScale = d3.scaleLinear().domain([0, maxVal]).range([72, 110]).clamp(true);

  // D3 data join on container
  const sel = d3.select(container)
    .selectAll('.item-tile')
    .data(allItems, d => d.uid);

  // Enter
  const enter = sel.enter()
    .append('div')
    .attr('class', 'item-tile')
    .style('opacity', 0)
    .on('click', (_, d) => onItemClick(d));

  enter.append('div').attr('class', 'item-tile__uid');
  enter.append('div').attr('class', 'item-tile__meta');
  enter.append('div').attr('class', 'item-tile__badge');

  // Update (enter + existing)
  const merged = enter.merge(sel);
  merged
    .style('background-color', d => colorScale(d.demand))
    .style('color', d => d.demand > maxDemand * 0.6 ? '#fff' : '#0f1117')
    .style('width', d => sizeScale(d.value) + 'px')
    .transition().duration(400)
    .style('opacity', 1);

  merged.select('.item-tile__uid').text(d => d.uid);
  merged.select('.item-tile__meta').text(d => {
    const demandStr = d.demand > 0 ? ` 🔥${d.demand}` : '';
    return `${d.value.toFixed(1)}cr${demandStr}`;
  });
  merged.select('.item-tile__badge')
    .attr('class', d => {
      if (d.is_mine) return 'item-tile__badge item-tile__badge--mine';
      if (d.holder)  return 'item-tile__badge item-tile__badge--held';
      return 'item-tile__badge item-tile__badge--free';
    })
    .text(d => d.is_mine ? 'MINE' : d.holder ? 'HELD' : 'FREE');

  // Exit
  sel.exit().transition().duration(200).style('opacity', 0).remove();
}

// ─────────────────────────────────────────────────────────────────────────────
// Block rail
// ─────────────────────────────────────────────────────────────────────────────
function updateBlockRail(chainData, isNew = false) {
  const rail = el('block-rail');
  if (!chainData || chainData.length === 0) return;

  // Full rebuild on non-animated updates to keep it clean
  if (!isNew) {
    rail.innerHTML = '';
    [...chainData].reverse().forEach(b => rail.appendChild(buildBlockCard(b, false)));
    return;
  }

  // Animated: prepend new block card, only if not already there
  const newest = chainData[chainData.length - 1];
  const existingFirst = rail.querySelector('.block-card');
  if (existingFirst && existingFirst.dataset.index == newest.index) return;

  const card = buildBlockCard(newest, true);
  rail.insertBefore(card, rail.firstChild);
  setTimeout(() => card.classList.remove('block-card--new'), 2000);
}

function buildBlockCard(b, animate) {
  const card = document.createElement('div');
  card.className = 'block-card' + (animate ? ' block-card--new' : '');
  card.dataset.index = b.index;

  const header = document.createElement('div');
  header.className = 'block-card__header';
  header.innerHTML = `
    <span class="block-card__index">#${b.index}</span>
    <span class="block-card__hash">${(b.hash || '').slice(0, 20)}…</span>`;

  const ts = document.createElement('div');
  ts.className = 'block-card__ts';
  ts.textContent = new Date(b.timestamp * 1000).toLocaleString() + ` · nonce: ${b.nonce}`;

  const txsEl = document.createElement('div');
  txsEl.className = 'block-card__txs';
  (b.transactions || []).forEach(tx => {
    const badge = document.createElement('span');
    const typeIdx = parseInt(tx.type) || 0;
    badge.className = `tx-badge tx-badge--${TX_BADGE_CLASS[typeIdx] || 'request'}`;
    const label = TX_TYPE_LABELS[typeIdx] || 'TX';
    const pubShort = (tx.requester || '').slice(0, 8);
    badge.textContent = tx.type === 0
      ? `⛏ +${(tx.amount || 0).toFixed(1)}`
      : `${label.slice(0, 3)} ${tx.uid || ''} · ${pubShort}`;
    badge.title = `${label} | ${tx.uid || ''} | ${tx.requester || ''} | ts: ${new Date(tx.timestamp * 1000).toLocaleTimeString()}`;
    txsEl.appendChild(badge);
  });

  const footer = document.createElement('div');
  footer.className = 'block-card__footer';
  footer.innerHTML = `<span>${(b.transactions || []).length} transactions</span>`;

  card.appendChild(header);
  card.appendChild(ts);
  card.appendChild(txsEl);
  card.appendChild(footer);
  return card;
}

// ─────────────────────────────────────────────────────────────────────────────
// Peers
// ─────────────────────────────────────────────────────────────────────────────
function updatePeers(peers) {
  const container = el('peer-list');
  if (!peers || peers.length === 0) {
    container.innerHTML = '<div class="empty-state">No peers connected</div>';
    return;
  }
  container.innerHTML = '';
  const now = Date.now() / 1000;
  peers.forEach(peer => {
    const idle = now - (peer.last_seen || 0);
    const dotClass = !peer.connected ? 'red' : idle < 10 ? 'green' : 'yellow';
    const uptime = formatUptime(peer.uptime_seconds || 0);
    const item = document.createElement('div');
    item.className = 'peer-item';
    item.title = `Blocks: ${peer.blocks_received} · Txs: ${peer.transactions_received} · Msgs: ${peer.messages_received} in / ${peer.messages_sent} out`;
    item.innerHTML = `
      <div class="peer-dot peer-dot--${dotClass}"></div>
      <div class="peer-item__info">
        <div class="peer-item__addr">${peer.address}</div>
        <div class="peer-item__stats">↑${peer.blocks_received}blk · ↑${peer.transactions_received}tx · ${uptime}</div>
      </div>`;
    container.appendChild(item);
  });
}

function formatUptime(s) {
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pool list (dev tools)
// ─────────────────────────────────────────────────────────────────────────────
function updatePoolList(pool) {
  const container = el('pool-list');
  if (!pool || pool.length === 0) { container.innerHTML = '<div class="empty-state">Mempool empty</div>'; return; }
  container.innerHTML = '';
  pool.forEach(tx => {
    const label = TX_TYPE_LABELS[parseInt(tx.type)] || 'TX';
    const div = document.createElement('div');
    div.className = 'pool-item';
    div.textContent = `${label} ${tx.uid || ''} · ${(tx.requester || '').slice(0, 12)}…`;
    container.appendChild(div);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Activity log
// ─────────────────────────────────────────────────────────────────────────────
function addLogEntry(entry) {
  const log = el('activity-log');
  const li = document.createElement('li');
  li.className = `log-entry log-entry--${entry.type}`;
  if (!_logFilters.has(entry.type)) li.classList.add('hidden');

  const ts = new Date(entry.ts * 1000);
  const timeStr = ts.toLocaleTimeString('en-GB', { hour12: false });

  li.innerHTML = `<span class="log-entry__ts">${timeStr}</span><span class="log-entry__msg">${escapeHtml(entry.message)}</span>`;
  li.dataset.type = entry.type;

  log.insertBefore(li, log.firstChild);

  // Cap log at 100 entries
  while (log.children.length > 100) log.removeChild(log.lastChild);
}

function renderFullLog(entries) {
  const log = el('activity-log');
  log.innerHTML = '';
  (entries || []).slice().reverse().forEach(addLogEntry);
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ─────────────────────────────────────────────────────────────────────────────
// Full state render
// ─────────────────────────────────────────────────────────────────────────────
function renderAll(payload, isBlockAdded = false) {
  _state = payload;
  updateStatusBar(payload);
  updateSparkline(payload.balance_history);
  updateCharts(payload);
  updateHeatmap(payload.items);
  updateBlockRail(payload.chain, isBlockAdded);
  updatePeers(payload.peers);
  updatePoolList(payload.pool);
  if (payload.activity_log) renderFullLog(payload.activity_log);
  updateMiningHint(payload);

  // Refresh item detail panel if open
  if (_selectedItem) {
    const allItems = [...(payload.items?.reserved || []), ...(payload.items?.available || [])];
    const found = allItems.find(i => i.uid === _selectedItem);
    if (found) showItemDetail(found);
  }
}

function updateMiningHint(payload) {
  const pool = payload.pool || [];
  const hint = el('mining-reward-hint');
  let escrow = 0;
  // estimate: any RELEASE in mempool contributes escrow fee to miner
  pool.forEach(tx => {
    if (parseInt(tx.type) === 2 && tx.amount) escrow += tx.amount * 0.3333;
  });
  if (escrow > 0) {
    hint.textContent = `Reward: 50 + ${escrow.toFixed(2)} escrow = ${(50 + escrow).toFixed(2)} credits`;
  } else {
    hint.textContent = 'Reward: 50 credits';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Item detail panel
// ─────────────────────────────────────────────────────────────────────────────
function onItemClick(item) {
  _selectedItem = item.uid;
  showItemDetail(item);
  loadItemHistory(item.uid);
}

function showItemDetail(item) {
  el('item-detail-uid').textContent   = item.uid;
  el('detail-value').textContent      = item.value?.toFixed(2) + ' cr';
  el('detail-demand').textContent     = item.demand || 0;
  el('detail-escrow').textContent     = (item.escrow || 0).toFixed(2) + ' cr';
  el('detail-holder').textContent     = item.holder_short || (item.holder ? item.holder.slice(0,12)+'…' : 'FREE');

  el('detail-btn-add').onclick = () => {
    const action = item.is_mine ? 'RELEASE' : 'REQUEST';
    addToBatch(action, item.uid);
  };
  el('detail-btn-add').textContent = item.is_mine ? 'Add RELEASE' : 'Add REQUEST';

  const panel = el('item-detail-panel');
  panel.classList.remove('hidden');
}

async function loadItemHistory(uid) {
  const timeline = el('item-detail-timeline');
  timeline.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const res = await api(`/api/items/${encodeURIComponent(uid)}/history`);
    const history = res.history || [];
    timeline.innerHTML = '';
    if (history.length === 0) {
      timeline.innerHTML = '<div class="empty-state">No transactions found</div>';
      return;
    }
    history.slice().reverse().forEach(ev => {
      const typeLabel = TX_TYPE_LABELS[ev.type] || 'TX';
      const ts = new Date(ev.timestamp * 1000).toLocaleDateString();
      const div = document.createElement('div');
      div.className = 'timeline-event';
      div.innerHTML = `
        <span class="timeline-event__block">#${ev.block_index}<br/>${ts}</span>
        <div class="timeline-event__body">
          <div class="timeline-event__type">${typeLabel}${ev.amount ? ' · ' + ev.amount.toFixed(2) + ' cr' : ''}</div>
          <div class="timeline-event__who">${ev.is_mine ? '(YOU)' : ev.requester_short}</div>
        </div>`;
      timeline.appendChild(div);
    });
  } catch (e) {
    timeline.innerHTML = '<div class="empty-state">Failed to load</div>';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch operations
// ─────────────────────────────────────────────────────────────────────────────
function addToBatch(action, uid) {
  if (!uid) return;
  if (_batch.find(i => i.uid === uid && i.action === action)) return; // no dupes
  _batch.push({ action, uid });
  renderBatchQueue();
  refreshBatchPreview();
}

function removeFromBatch(index) {
  _batch.splice(index, 1);
  renderBatchQueue();
  refreshBatchPreview();
}

function renderBatchQueue() {
  const container = el('batch-queue');
  const btn = el('btn-execute');

  if (_batch.length === 0) {
    container.innerHTML = '<div class="empty-state">Batch is empty</div>';
    btn.disabled = true;
    btn.textContent = 'Execute Batch';
    return;
  }

  container.innerHTML = '';
  _batch.forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'batch-queue-item';
    div.innerHTML = `
      <span class="batch-queue-item__action batch-queue-item__action--${item.action.toLowerCase()}">${item.action}</span>
      <span class="batch-queue-item__uid">${escapeHtml(item.uid)}</span>
      <span class="batch-queue-item__remove" data-idx="${i}" title="Remove">✕</span>`;
    div.querySelector('.batch-queue-item__remove').addEventListener('click', (e) => {
      removeFromBatch(parseInt(e.target.dataset.idx));
    });
    container.appendChild(div);
  });

  if (_batch.length === 1) {
    btn.textContent = `${_batch[0].action.charAt(0) + _batch[0].action.slice(1).toLowerCase()} 1 Item`;
  } else {
    btn.textContent = `Execute Batch (${_batch.length} items)`;
  }
  btn.disabled = false;
}

async function refreshBatchPreview() {
  const preview = el('batch-preview');
  if (_batch.length === 0) { preview.classList.add('hidden'); return; }

  try {
    const res = await api('/api/batch/preview', {
      method: 'POST',
      body: JSON.stringify({ items: _batch })
    });

    preview.innerHTML = '';
    preview.classList.remove('hidden');

    (res.preview || []).forEach(row => {
      const div = document.createElement('div');
      div.className = `preview-row preview-row--${row.cost_type}`;
      const sign = row.amount >= 0 ? '+' : '';
      div.innerHTML = `
        <span class="preview-row__uid">${escapeHtml(row.uid)}</span>
        <span class="preview-row__cost">${sign}${row.amount.toFixed(2)}</span>`;
      preview.appendChild(div);
    });

    const total = res.total_cost || 0;
    const balance = res.balance || 0;
    const totalRow = document.createElement('div');
    totalRow.className = `preview-total preview-total--${res.can_afford ? (total < 0 ? 'warn' : 'ok') : 'bad'}`;
    totalRow.innerHTML = `
      <span>Total cost</span>
      <span class="preview-total__val">${total >= 0 ? '+' : ''}${total.toFixed(2)} cr (bal: ${balance.toFixed(1)})</span>`;
    preview.appendChild(totalRow);
  } catch (e) {
    preview.classList.add('hidden');
  }
}

async function executeBatch() {
  if (_batch.length === 0) return;
  el('btn-execute').disabled = true;
  try {
    const res = await api('/api/batch/execute', { method: 'POST', body: JSON.stringify({ items: _batch }) });
    if (res.error) {
      showToast(`❌ ${res.error}`, 'danger');
      return;
    }
    if (res.failed && res.failed.length > 0) {
      showToast(`⚠️ ${res.failed.length} item(s) failed`, 'warn');
    }
    if (res.broadcast > 0) {
      showToast(`✅ Broadcast ${res.broadcast} transaction${res.broadcast !== 1 ? 's' : ''}`, 'ok');
    }
    _batch = [];
    renderBatchQueue();
    el('batch-preview').classList.add('hidden');
  } catch (e) {
    showToast('❌ Network error', 'danger');
  } finally {
    el('btn-execute').disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Toast notification (inline, no external lib)
// ─────────────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'ok') {
  const t = document.createElement('div');
  const colors = { ok: '#3fb950', warn: '#d29922', danger: '#f85149' };
  Object.assign(t.style, {
    position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
    background: '#161b22', border: `1px solid ${colors[type] || colors.ok}`,
    color: colors[type] || colors.ok,
    padding: '8px 18px', borderRadius: '6px', fontSize: '13px', fontWeight: '600',
    zIndex: '9999', boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    transition: 'opacity 0.3s',
  });
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 2500);
}

// ─────────────────────────────────────────────────────────────────────────────
// Connect peer modal
// ─────────────────────────────────────────────────────────────────────────────
function openConnectModal() {
  el('connect-modal').classList.remove('hidden');
  el('modal-backdrop').classList.remove('hidden');
  el('peer-host').focus();
}
function closeConnectModal() {
  el('connect-modal').classList.add('hidden');
  el('modal-backdrop').classList.add('hidden');
}
async function doConnect() {
  const host = el('peer-host').value.trim();
  const port = parseInt(el('peer-port').value);
  if (!host || !port) return;
  closeConnectModal();
  try {
    await api('/api/peers/connect', { method: 'POST', body: JSON.stringify({ host, port }) });
    showToast(`🔗 Connecting to ${host}:${port}`, 'ok');
  } catch (e) {
    showToast('❌ Connection failed', 'danger');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab switching
// ─────────────────────────────────────────────────────────────────────────────
function switchTab(tabName) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('tab--active', t.dataset.tab === tabName));
  document.querySelectorAll('.tab-content').forEach(c => {
    const active = c.id === `tab-${tabName}`;
    c.classList.toggle('tab-content--active', active);
    c.style.display = active ? 'flex' : 'none';
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SSE stream
// ─────────────────────────────────────────────────────────────────────────────
function startStream() {
  const es = new EventSource(`${BASE}/stream`);

  es.addEventListener('initial_state', e => {
    try { renderAll(JSON.parse(e.data).payload || JSON.parse(e.data)); }
    catch (err) { console.error('initial_state parse error', err); }
  });

  es.addEventListener('block_added', e => {
    try {
      const data = JSON.parse(e.data);
      const payload = data.payload || data;
      renderAll(payload, true);
      if (payload.activity_log) {
        const last = payload.activity_log[payload.activity_log.length - 1];
        if (last) addLogEntry(last);
      }
    } catch (err) { console.error('block_added parse error', err); }
  });

  const genericEvents = ['tx_added', 'status_update', 'peer_connected', 'peer_disconnected', 'integrity_update', 'chain_replaced', 'pool_cleared'];
  genericEvents.forEach(evName => {
    es.addEventListener(evName, e => {
      try {
        const data = JSON.parse(e.data);
        renderAll(data.payload || data, false);
      } catch (err) { console.error(`${evName} parse error`, err); }
    });
  });

  es.addEventListener('log_entry', e => {
    try {
      const data = JSON.parse(e.data);
      const entry = (data.payload || data).entry;
      if (entry) addLogEntry(entry);
    } catch (err) {}
  });

  es.onerror = () => {
    setTimeout(startStream, 2000);
    try { es.close(); } catch (_) {}
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Wire up all UI events
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Prevent double init
  initCharts();

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });
  // Init tab display
  document.querySelectorAll('.tab-content').forEach(c => {
    if (!c.classList.contains('tab-content--active')) c.style.display = 'none';
  });

  // Batch: add button
  el('btn-batch-add').addEventListener('click', () => {
    const uid = el('batch-uid').value.trim();
    const action = el('batch-action').value;
    if (uid) { addToBatch(action, uid); el('batch-uid').value = ''; }
  });
  el('batch-uid').addEventListener('keydown', e => {
    if (e.key === 'Enter') { el('btn-batch-add').click(); }
  });

  el('btn-execute').addEventListener('click', executeBatch);
  el('btn-batch-clear').addEventListener('click', () => {
    _batch = [];
    renderBatchQueue();
    el('batch-preview').classList.add('hidden');
  });

  // Mining
  el('btn-mine').addEventListener('click', async () => {
    try {
      const res = await api('/api/mempool/mine', { method: 'POST' });
      if (res.error) showToast(`❌ ${res.error}`, 'danger');
      else showToast('⛏ Mining…', 'ok');
    } catch (e) { showToast('❌ Error', 'danger'); }
  });

  el('chk-auto-mine').addEventListener('change', async (e) => {
    try {
      await api('/api/mempool/auto_mine', { method: 'POST', body: JSON.stringify({ enabled: e.target.checked }) });
    } catch (err) {}
  });

  // Peers
  el('btn-connect-peer').addEventListener('click', openConnectModal);
  el('btn-sync-chain').addEventListener('click', async () => {
    try {
      const res = await api('/api/peers/sync', { method: 'POST' });
      if (res.error) showToast(`❌ ${res.error}`, 'warn');
      else showToast('📡 Sync requested', 'ok');
    } catch (e) {}
  });

  // Modal
  el('modal-connect').addEventListener('click', doConnect);
  el('modal-cancel').addEventListener('click', closeConnectModal);
  el('modal-backdrop').addEventListener('click', closeConnectModal);
  el('peer-host').addEventListener('keydown', e => { if (e.key === 'Enter') doConnect(); });
  el('peer-port').addEventListener('keydown', e => { if (e.key === 'Enter') doConnect(); });

  // Item detail panel close
  el('item-detail-close').addEventListener('click', () => {
    el('item-detail-panel').classList.add('hidden');
    _selectedItem = null;
  });

  // Activity log filters
  document.querySelectorAll('.log-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      const type = btn.dataset.type;
      if (_logFilters.has(type)) {
        _logFilters.delete(type);
        btn.classList.remove('log-filter--active');
      } else {
        _logFilters.add(type);
        btn.classList.add('log-filter--active');
      }
      // Apply filter to existing entries
      document.querySelectorAll('.log-entry').forEach(li => {
        li.classList.toggle('hidden', !_logFilters.has(li.dataset.type));
      });
    });
  });

  el('btn-clear-log').addEventListener('click', () => {
    el('activity-log').innerHTML = '';
  });

  // Dev tools
  el('btn-repair').addEventListener('click', async () => {
    const r = await api('/api/repair', { method: 'POST' });
    showToast(r.repaired ? '✅ Chain repaired' : 'ℹ️ No repair needed', 'ok');
  });
  el('btn-save').addEventListener('click', async () => {
    await api('/api/save', { method: 'POST' });
    showToast('💾 Saved', 'ok');
  });
  el('btn-load').addEventListener('click', async () => {
    const r = await api('/api/load', { method: 'POST' });
    if (r.error) showToast('❌ ' + r.error, 'danger');
    else showToast('📂 Loaded', 'ok');
  });
  el('btn-corrupt').addEventListener('click', async () => {
    const idx = parseInt(el('corrupt-index').value);
    const field = el('corrupt-field').value;
    const value = el('corrupt-value').value;
    if (!idx || !value) { showToast('Fill in all fields', 'warn'); return; }
    const r = await api('/api/corrupt_block', { method: 'POST', body: JSON.stringify({ index: idx, field, value }) });
    if (r.error) showToast('❌ ' + r.error, 'danger');
    else showToast('💀 Block corrupted', 'warn');
  });
  el('btn-clear-pool').addEventListener('click', async () => {
    await api('/api/pool/clear', { method: 'POST' });
    showToast('🗑 Mempool cleared', 'warn');
  });

  // Electron menu actions
  if (window.electronAPI) {
    window.electronAPI.onMenuAction(action => {
      if (action === 'connect-peer') openConnectModal();
      if (action === 'sync-chain')   el('btn-sync-chain').click();
      if (action === 'save-chain')   el('btn-save').click();
      if (action === 'load-chain')   el('btn-load').click();
    });
    window.electronAPI.onBackendDied(code => {
      showToast(`❌ Backend process died (code ${code})`, 'danger');
    });
  }

  // Start SSE and do initial load
  startStream();

  // Fallback fetch on load
  setTimeout(async () => {
    try {
      const [chainRes, statsRes, itemsRes, poolRes] = await Promise.all([
        api('/api/chain'),
        api('/api/stats'),
        api('/api/items'),
        api('/api/pool'),
      ]);
      // Merge into minimal payload for initial render if SSE hasn't fired yet
      if (!_state) {
        const nodeRes = await api('/api/node');
        const summaryRes = await api('/api/summary');
        renderAll({
          chain: chainRes.chain || [],
          stats: statsRes,
          summary: summaryRes,
          items: itemsRes,
          pool: poolRes.pool || [],
          peers: [],
          node: nodeRes,
          balance_history: [],
          activity_log: [],
        });
      }
    } catch (e) {
      console.warn('Fallback fetch failed:', e);
    }
  }, 500);
});
