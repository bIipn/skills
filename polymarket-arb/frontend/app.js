// Live dashboard: WebSocket stream with REST fallback + canvas equity chart.
const $ = (id) => document.getElementById(id);
const fmt = (n) => "$" + Number(n).toLocaleString(undefined, {maximumFractionDigits: 2});

let lastTradeKey = "";

function render(s) {
  $("equity").textContent = fmt(s.bankroll);
  const pnlEl = $("pnl");
  const sign = s.realized_pnl >= 0 ? "+" : "";
  pnlEl.textContent = `${sign}${fmt(s.realized_pnl)} (${sign}${s.pnl_pct}%)`;
  pnlEl.classList.toggle("neg", s.realized_pnl < 0);

  $("k-trades").textContent = s.trades_total;
  $("k-winrate").textContent = s.win_rate + "%";
  $("k-avg").textContent = fmt(s.avg_profit);
  $("k-opps").textContent = s.opportunities_found;
  $("k-scan").textContent = s.last_scan_ms + "ms";
  $("k-markets").textContent = s.markets_scanned;

  // mode pills
  const dm = $("data-mode");
  dm.textContent = "DATA: " + s.data_mode.toUpperCase();
  dm.className = "pill " + (s.data_mode === "live" ? "ok" : "paper");
  const em = $("exec-mode");
  em.textContent = "EXEC: " + (s.execution_live ? "LIVE" : "PAPER");
  em.className = "pill " + (s.execution_live ? "live" : "paper");

  renderFillReport(s.fill_report);
  renderStrategies(s.by_strategy);
  renderOpps(s.live_opportunities);
  renderTrades(s.recent_trades);
  drawChart(s.equity_curve, s.starting_bankroll);
}

function renderFillReport(r) {
  if (!r) return;
  const rateClass = r.overall_fill_rate >= 70 ? "pos"
    : (r.overall_fill_rate >= 45 ? "" : "neg");
  const per = Object.entries(r.by_strategy || {})
    .map(([k, v]) => `<div class="strat-cell">
        <div class="tag ${k}">${k.replace("_", " ")}</div>
        <div class="strat-pnl ${v.fill_rate >= 70 ? "pos" : (v.fill_rate >= 45 ? "" : "neg")}">${v.fill_rate}%</div>
        <div class="muted small">${v.wins}/${v.trades} filled</div>
      </div>`).join("");
  $("fillreport").innerHTML =
    `<div class="subrow"><span class="big-inline ${rateClass}">${r.overall_fill_rate}% fill rate</span>
       <span class="muted">${r.filled} filled · ${r.slipped} slipped · ${r.skipped_no_capital} skipped (no capital) · ${r.opportunities_found} opportunities seen</span></div>
     <div class="strat-grid" style="margin-top:10px">${per}</div>
     <div class="muted small" style="margin-top:8px">In the demo this is your go/no-go signal: a high fill rate on real prices means the edge is real. The paper saw ~87% single-condition, ~45% combinatorial.</div>`;
}

const STRAT_LABELS = {
  single_condition: "Single-condition (YES+NO<$1)",
  rebalance: "Rebalance (buy-all outcomes)",
  combinatorial: "Combinatorial (LP / dependencies)",
};

function renderStrategies(by) {
  if (!by) return;
  $("strategies").innerHTML = Object.entries(by).map(([kind, v]) => {
    const cls = v.pnl >= 0 ? "pos" : "neg";
    return `<div class="strat-cell">
      <div class="tag ${kind}">${kind.replace("_", " ")}</div>
      <div class="strat-pnl ${cls}">${v.pnl >= 0 ? "+" : ""}${fmt(v.pnl)}</div>
      <div class="muted">${v.trades} trades</div>
      <div class="muted small">${STRAT_LABELS[kind] || ""}</div>
    </div>`;
  }).join("");
}

function renderOpps(opps) {
  $("opp-count").textContent = `(${opps.length})`;
  const tb = $("opps");
  tb.innerHTML = opps.map(o => `
    <tr>
      <td><span class="tag ${o.kind}">${o.kind.replace("_", " ")}</span></td>
      <td>${escapeHtml(o.description)}</td>
      <td>${fmt(o.cost)}</td>
      <td>${fmt(o.guaranteed_payoff)}</td>
      <td class="pos">+${fmt(o.profit)}</td>
      <td class="pos">${o.edge_pct}%</td>
      <td title="Bregman divergence = max extractable profit/unit">${o.bregman}</td>
      <td title="Frank-Wolfe iterations to converge">${o.fw_iters}</td>
      <td>${(o.confidence * 100).toFixed(0)}%</td>
    </tr>`).join("") || `<tr><td colspan="9" class="muted">scanning…</td></tr>`;
}

function renderTrades(trades) {
  const tb = $("trades");
  const topKey = trades.length ? `${trades[0].executed_at}` : "";
  tb.innerHTML = trades.map((t, i) => {
    const pl = t.realized_profit;
    const cls = pl >= 0 ? "pos" : "neg";
    const flash = (i === 0 && topKey !== lastTradeKey) ? "flash" : "";
    return `<tr class="${flash}">
      <td>${escapeHtml(t.description)}</td>
      <td><span class="tag ${t.kind}">${t.kind.replace("_", " ")}</span></td>
      <td>${fmt(t.realized_cost)}</td>
      <td class="${cls}">${pl >= 0 ? "+" : ""}${fmt(pl)}</td>
      <td class="${cls}">${escapeHtml(t.note)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="5" class="muted">no trades yet</td></tr>`;
  lastTradeKey = topKey;
}

function drawChart(curve, base) {
  const c = $("chart");
  const ctx = c.getContext("2d");
  const w = c.width = c.clientWidth * devicePixelRatio;
  const h = c.height = 160 * devicePixelRatio;
  ctx.clearRect(0, 0, w, h);
  if (!curve || curve.length < 2) return;

  const vals = curve.map(p => p.equity);
  const min = Math.min(...vals, base), max = Math.max(...vals, base);
  const pad = (max - min) * 0.1 || 1;
  const lo = min - pad, hi = max + pad;
  const x = i => (i / (curve.length - 1)) * w;
  const y = v => h - ((v - lo) / (hi - lo)) * h;

  // baseline
  ctx.strokeStyle = "#1e2b3a"; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(0, y(base)); ctx.lineTo(w, y(base)); ctx.stroke();
  ctx.setLineDash([]);

  // area + line
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(22,217,127,0.25)");
  grad.addColorStop(1, "rgba(22,217,127,0)");
  ctx.beginPath(); ctx.moveTo(0, h);
  curve.forEach((p, i) => ctx.lineTo(x(i), y(p.equity)));
  ctx.lineTo(w, h); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  ctx.beginPath();
  curve.forEach((p, i) => i ? ctx.lineTo(x(i), y(p.equity)) : ctx.moveTo(x(i), y(p.equity)));
  ctx.strokeStyle = "#16d97f"; ctx.lineWidth = 2 * devicePixelRatio; ctx.stroke();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

let wsEverOpened = false;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const conn = $("conn");
  ws.onopen = () => { wsEverOpened = true; conn.textContent = "● live"; conn.className = "pill ok"; };
  ws.onmessage = (e) => render(JSON.parse(e.data));
  ws.onclose = () => {
    if (wsEverOpened) {
      // Live host (local FastAPI) dropped — reconnect and poll meanwhile.
      conn.textContent = "● reconnecting"; conn.className = "pill pill-dim";
      pollFallback();
      setTimeout(connect, 3000);
    } else {
      // WebSocket never connected → we're on a static host (Vercel). Poll the
      // serverless /api/state, which serves the Mac mini's pushed snapshot.
      cloudMode();
    }
  };
  ws.onerror = () => ws.close();
}

// Where the hosted dashboard reads state from (overridable via config.js).
const STATE_URL = window.CLOUD_STATE_URL || "/api/state";

let pollTimer = null;
function pollFallback() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const j = await (await fetch(STATE_URL, { cache: "no-store" })).json();
      if (j && j.bankroll !== undefined) render(j);
    } catch (_) {}
  }, 2500);
}

function cloudMode() {
  const conn = $("conn");
  const btCard = btBtn && btBtn.closest(".card");
  if (btCard) btCard.style.display = "none";  // backtest needs the local backend
  async function tick() {
    try {
      const j = await (await fetch(STATE_URL, { cache: "no-store" })).json();
      if (j && j.bankroll !== undefined) {
        render(j);
        const age = j._synced_at ? Math.round((Date.now() - j._synced_at) / 1000) : null;
        conn.textContent = (age !== null && age < 30) ? "● live (cloud)"
          : (age !== null ? `● ${age}s ago` : "● cloud");
        conn.className = (age === null || age < 30) ? "pill ok" : "pill pill-dim";
      } else {
        conn.textContent = "● waiting for bot"; conn.className = "pill pill-dim";
      }
    } catch (_) {
      conn.textContent = "● offline"; conn.className = "pill pill-dim";
    }
  }
  tick();
  setInterval(tick, 3000);
}

// Backtest runner
const btBtn = $("bt-run");
if (btBtn) {
  btBtn.addEventListener("click", async () => {
    btBtn.disabled = true;
    $("backtest").textContent = "Running backtest…";
    try {
      const r = await fetch("/api/backtest?ticks=500");
      const b = await r.json();
      const strat = Object.entries(b.by_strategy)
        .map(([k, v]) => `${k.replace("_", " ")} +${fmt(v.pnl)} (${v.trades})`)
        .join(" · ");
      $("backtest").innerHTML =
        `<span class="pos big-inline">${b.return_pct >= 0 ? "+" : ""}${b.return_pct}%</span> ` +
        `over ${b.ticks} ticks — ${fmt(b.starting_bankroll)} → ${fmt(b.final_bankroll)}<br/>` +
        `${b.trades} trades · win rate ${b.win_rate}% · avg ${fmt(b.avg_profit)}/trade · ` +
        `max drawdown ${b.max_drawdown_pct}%<br/><span class="muted">${escapeHtml(strat)}</span>`;
    } catch (e) {
      $("backtest").textContent = "Backtest failed: " + e;
    } finally {
      btBtn.disabled = false;
    }
  });
}

// Try WebSocket first (local FastAPI). If it never connects, connect()'s
// onclose switches to cloud polling automatically. Also paint once up front.
connect();
fetch(STATE_URL, { cache: "no-store" })
  .then(r => r.json())
  .then(j => { if (j && j.bankroll !== undefined) render(j); })
  .catch(() => {});
