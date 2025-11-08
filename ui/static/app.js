// Frontend logic: live charts and block visuals using Server-Sent Events (SSE).
// This file replaces periodic manual refresh with a live stream handler.
// Comments explain the behavior and data flow.

async function api(path, opts = {}) {
  // Normalize options: ensure method is uppercase
  opts = Object.assign({}, opts);
  opts.method = (opts.method || "GET").toUpperCase();

  // If it's a POST and caller didn't supply a body, send an explicit empty JSON body.
  if (opts.method === "POST") {
    opts.headers = Object.assign({}, opts.headers);
    // ensure header key is exactly "Content-Type"
    if (!Object.keys(opts.headers).some(k => k.toLowerCase() === "content-type")) {
      opts.headers["Content-Type"] = "application/json";
    }
    if (!("body" in opts) || opts.body === undefined || opts.body === null) {
      opts.body = JSON.stringify({});
    }
  }

  const res = await fetch(path, opts);
  return res.json();
}

function el(id) { return document.getElementById(id); }

// Chart instances
let txsChart = null;
let allocChart = null;

// Initialize charts with empty dataset
function initCharts() {
  const txsCtx = el("txsChart").getContext("2d");
  txsChart = new Chart(txsCtx, {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'Txs per Block', data: [], backgroundColor: '#0d6efd' }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: 'Block' } }, y: { title: { display: true, text: 'Transactions' }, beginAtZero: true } } }
  });

  const allocCtx = el("allocChart").getContext("2d");
  allocChart = new Chart(allocCtx, {
    type: 'pie',
    data: { labels: ['Allocated', 'Available'], datasets: [{ data: [0,0], backgroundColor: ['#dc3545','#198754'] }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
  });
}

// Update stat badges
function updateStats(summary, integrityOk) {
  el("stat-length").textContent = summary.chain_length;
  el("stat-difficulty").textContent = summary.difficulty;
  el("stat-integrity").textContent = integrityOk ? "OK" : "Bad";
  el("stat-integrity").style.color = integrityOk ? "#198754" : "#dc3545";
}

// Render charts with summary data
function renderCharts(summary) {
  txsChart.data.labels = summary.block_indexes.map(i => `#${i}`);
  txsChart.data.datasets[0].data = summary.txs_per_block;
  txsChart.update();

  allocChart.data.datasets[0].data = [summary.allocated_count, summary.available_count];
  allocChart.update();
}

// Render block visual rail from chain data (no raw JSON)
function renderBlockRail(chainData) {
  const rail = el("block-rail");
  rail.innerHTML = ""; // clear

  chainData.forEach(b => {
    const card = document.createElement("div");
    card.className = "block-card";

    // header with index + short hash
    const hdr = document.createElement("div");
    hdr.className = "block-header";
    const idx = document.createElement("div");
    idx.className = "block-index";
    idx.textContent = `#${b.index}`;
    const hsh = document.createElement("div");
    hsh.className = "block-hash";
    hsh.textContent = b.hash ? b.hash.slice(0, 14) + (b.hash.length > 14 ? "…" : "") : "(pending)";
    hdr.appendChild(idx);
    hdr.appendChild(hsh);

    // timestamp
    const ts = document.createElement("div");
    ts.className = "text-muted small mb-2";
    ts.textContent = new Date(b.timestamp * 1000).toLocaleString();

    // transactions as badges
    const txContainer = document.createElement("div");
    txContainer.className = "mb-2";
    (b.transactions || []).forEach(tx => {
      const badge = document.createElement("span");
      badge.className = "tx-badge " + (tx.type == 1 ? "tx-request" : "tx-release");
      const pubshort = (tx.requester || "").slice(0,8);
      badge.textContent = `${tx.type==1 ? "REQ" : "REL"} ${tx.uid} by ${pubshort}`;
      txContainer.appendChild(badge);
    });

    // footer with nonce and tx count
    const footer = document.createElement("div");
    footer.className = "d-flex justify-content-between small text-muted";
    const left = document.createElement("div");
    left.textContent = `nonce: ${b.nonce}`;
    const right = document.createElement("div");
    right.textContent = `${(b.transactions || []).length} txs`;
    footer.appendChild(left);
    footer.appendChild(right);

    // assemble card
    card.appendChild(hdr);
    card.appendChild(ts);
    card.appendChild(txContainer);
    card.appendChild(footer);
    rail.appendChild(card);
  });
}

// Pool list rendering
function renderPoolList(pool) {
  const ul = el("pool-list");
  ul.innerHTML = "";
  (pool || []).slice().reverse().forEach(tx => {
    const li = document.createElement("li");
    li.className = "list-group-item py-1";
    const type = tx.type == 1 ? "Request" : "Release";
    const pubshort = (tx.requester || "").slice(0,8);
    li.textContent = `${type} ${tx.uid} — by ${pubshort}`;
    ul.appendChild(li);
  });
}

// Handle incoming SSE payload (update event)
function handleUpdate(payload) {
  // payload contains: { summary, chain, stats, pool }
  const summary = payload.summary || {};
  const chainData = payload.chain || [];
  const stats = payload.stats || {};
  const pool = payload.pool || [];

  updateStats(summary, stats.integrity_ok);
  renderCharts(summary);
  renderBlockRail(chainData);
  renderPoolList(pool);
}

// Connect to SSE stream and handle reconnection
function startStream() {
  let es = new EventSource("/stream");
  // on 'update' events, receive the latest payload
  es.addEventListener("update", e => {
    try {
      const data = JSON.parse(e.data);
      handleUpdate(data);
    } catch (err) {
      console.error("Failed to parse update event:", err);
    }
  });

  es.onopen = () => {
    console.info("SSE connection opened");
  };

  es.onerror = (err) => {
    console.warn("SSE error, will attempt reconnect in 2s", err);
    // Close and try to reconnect after a delay
    try { es.close(); } catch (e) {}
    setTimeout(startStream, 2000);
  };
}

// Wallet: generate keypair and display short public and full private in text area
async function genKeypair() {
  const r = await api("/api/generate_key", { method: "POST" });
  el("privpem").value = r.privkey_pem;
  el("pubshort").textContent = r.pubkey_hex.slice(0, 20) + (r.pubkey_hex.length>20 ? "…" : "");
}

// Create transaction using private PEM in textarea
async function createTx() {
  const pem = el("privpem").value.trim();
  if (!pem) { alert("Paste or generate a private key first."); return; }
  const uid = el("tx-uid").value.trim();
  if (!uid) { alert("Enter an Item ID."); return; }
  const type = el("tx-type").value;
  const r = await api("/api/create_tx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ privkey_pem: pem, uid: uid, type: type })
  });
  if (r.error) { alert("Error: " + r.error); return; }
  // UI will be updated via SSE stream; optionally update pool list immediately
  // fetch latest pool via API if SSE hasn't arrived yet
  setTimeout(async () => {
    const poolRes = await api("/api/pool");
    renderPoolList(poolRes.tx_pool || []);
  }, 200);
}

// Clear the in-memory pool
async function clearPool() {
  await api("/api/clear_pool", { method: "POST" });
  // SSE will update pool; fallback: clear immediately
  renderPoolList([]);
}

// Mine block (use pool)
async function mineBlock() {
  const r = await api("/api/add_block", { method: "POST" });
  if (r.error) { alert("Error: " + r.error); return; }
  alert("Block mined and appended.");
  // SSE will update chain; nothing else needed
}

// Corrupt block for demo
async function corruptBlock() {
  const idx = parseInt(el("corrupt-index").value || "-1");
  const field = el("corrupt-field").value;
  const value = el("corrupt-value").value;
  if (isNaN(idx) || idx <= 0) { alert("Provide a valid index > 0"); return; }
  const r = await api("/api/corrupt_block", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index: idx, field: field, value: value })
  });
  if (r.error) alert("Error: " + r.error);
}

// Repair chain
async function repairChain() {
  const r = await api("/api/repair", { method: "POST" });
  alert("Repair done: " + r.repaired);
}

// Save and load chain
async function saveChain() { await api("/api/save", { method: "POST" }); alert("Saved."); }
async function loadChain() { const r = await api("/api/load", { method: "POST" }); if (r.error) alert("Load err: "+r.error); }

// Wire up UI actions and start SSE
document.addEventListener("DOMContentLoaded", function() {
  initCharts();
  // buttons
  el("btn-gen").addEventListener("click", genKeypair);
  el("btn-create-tx").addEventListener("click", createTx);
  el("btn-mine").addEventListener("click", mineBlock);
  el("btn-clear-pool").addEventListener("click", clearPool);
  el("btn-corrupt").addEventListener("click", corruptBlock);
  el("btn-repair").addEventListener("click", repairChain);
  el("btn-save-chain").addEventListener("click", saveChain);
  el("btn-load-chain").addEventListener("click", loadChain);

  // start SSE stream for live updates
  startStream();

  // initial fallback fetch for UI (in case SSE initial message is delayed)
  setTimeout(async () => {
    const [summary, chainRes, statsRes, poolRes] = await Promise.all([
      api("/api/summary"),
      api("/api/chain"),
      api("/api/stats"),
      api("/api/pool")
    ]);
    updateStats(summary, statsRes.integrity_ok);
    renderCharts(summary);
    renderBlockRail(chainRes.chain || []);
    renderPoolList(poolRes.tx_pool || []);
  }, 200);
});