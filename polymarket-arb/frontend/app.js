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

  renderSubstats(s);
  renderCycle(s);
  drawDecisionTree(s);
  drawCandles(s.equity_curve);
  renderHeatmap(s);
  renderMM(s.market_making, s.mode);
  renderFillReport(s.fill_report);
  renderStrategies(s.by_strategy);
  renderOpps(s.live_opportunities);
  renderTrades(s.recent_trades);
  drawChart(s.equity_curve, s.starting_bankroll, "chart");
  drawChart(s.equity_curve, s.starting_bankroll, "curve");
  $("curve-val").textContent = fmt(s.bankroll);
}

// ---- Header sub-stats (the small green ticker row) --------------------
function renderSubstats(s) {
  const el = $("substats");
  if (!el) return;
  const items = [
    ["MODE", (s.mode || "arbitrage").toUpperCase().replace("_", " ")],
    ["EQUITY", fmt(s.bankroll)],
    ["P/L", (s.realized_pnl >= 0 ? "+" : "") + fmt(s.realized_pnl)],
    ["FILL", s.win_rate + "%"],
    ["SIGNALS", s.opportunities_found],
    ["TICK", s.tick],
  ];
  el.innerHTML = items.map(([l, v]) =>
    `<span class="ss"><span class="ss-l">${l}</span> <span class="ss-v">${v}</span></span>`).join("");
}

// ---- Execution cycle bar ---------------------------------------------
const CYCLE_STAGES = ["SCAN", "DETECT", "OPTIMIZE", "SIZE", "EXECUTE", "SETTLE"];
function renderCycle(s) {
  const el = $("exec-cycle");
  if (!el) return;
  const active = (s.tick || 0) % CYCLE_STAGES.length;
  el.innerHTML = CYCLE_STAGES.map((name, i) =>
    `<div class="seg ${i === active ? "on" : (i < active ? "done" : "")}">
       <span class="seg-i">${i + 1}</span> ${name}</div>`).join("");
  $("cyc-lat").textContent = (s.last_scan_ms || 0) + "ms · " + CYCLE_STAGES[active];
}

// ---- Strategy decision tree (canvas node graph) ----------------------
function drawDecisionTree(s) {
  const c = $("dtree");
  if (!c) return;
  const ctx = c.getContext("2d");
  const w = c.width = c.clientWidth * devicePixelRatio;
  const h = c.height = 240 * devicePixelRatio;
  const P = devicePixelRatio;
  ctx.clearRect(0, 0, w, h);
  ctx.lineWidth = 1.5 * P;
  ctx.font = `${11 * P}px -apple-system, sans-serif`;
  ctx.textBaseline = "middle";

  const by = s.by_strategy || {};
  const fr = s.fill_report || {};
  const green = "#30d158", dim = "#1e2b3a", txt = "#d7e2ee", mut = "#6b7c91";

  // Node columns: Markets → strategies → Optimize → Size → Execute → Result
  const root = { x: 0.06 * w, y: h / 2, label: "MARKETS", sub: (s.markets_scanned || 0) + "" };
  const strats = [
    ["single_condition", "SINGLE"],
    ["rebalance", "REBALANCE"],
    ["combinatorial", "COMBO"],
    ["cross_venue", "X-VENUE"],
  ];
  const sx = 0.28 * w;
  const stratNodes = strats.map(([k, lbl], i) => ({
    x: sx, y: (i + 1) * h / (strats.length + 1),
    label: lbl, sub: (by[k]?.trades || 0) + " tr",
    val: by[k]?.pnl || 0,
  }));
  const opt = { x: 0.52 * w, y: h / 2, label: "OPTIMIZE", sub: "Bregman/FW" };
  const size = { x: 0.68 * w, y: h / 2, label: "SIZE", sub: "Kelly+depth" };
  const exec = { x: 0.84 * w, y: h / 2, label: "EXECUTE", sub: (fr.overall_fill_rate ?? 0) + "% fill" };
  const result = { x: 0.96 * w, y: h / 2, label: fmt(s.realized_pnl || 0),
                   sub: "P/L", big: true };

  function edge(a, b, col) {
    ctx.strokeStyle = col || dim;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.bezierCurveTo((a.x + b.x) / 2, a.y, (a.x + b.x) / 2, b.y, b.x, b.y);
    ctx.stroke();
  }
  function node(n, accent) {
    const rw = (n.big ? 60 : 50) * P, rh = 30 * P;
    ctx.fillStyle = "#0f1620";
    ctx.strokeStyle = accent ? green : dim;
    ctx.lineWidth = 1.5 * P;
    roundRect(ctx, n.x - rw / 2, n.y - rh / 2, rw, rh, 6 * P);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = accent ? green : txt;
    ctx.textAlign = "center";
    ctx.font = `${(n.big ? 12 : 10.5) * P}px -apple-system, sans-serif`;
    ctx.fillText(n.label, n.x, n.y - 4 * P);
    ctx.fillStyle = mut;
    ctx.font = `${8.5 * P}px -apple-system, sans-serif`;
    ctx.fillText(n.sub, n.x, n.y + 8 * P);
  }

  stratNodes.forEach(n => edge(root, n, n.val > 0 ? green : dim));
  stratNodes.forEach(n => edge(n, opt, n.val > 0 ? green : dim));
  edge(opt, size, green); edge(size, exec, green); edge(exec, result, green);
  node(root, true);
  stratNodes.forEach(n => node(n, n.val > 0));
  node(opt, true); node(size, true); node(exec, true); node(result, true);

  // headline fill % near execute
  ctx.fillStyle = green;
  ctx.textAlign = "center";
  ctx.font = `700 ${18 * P}px -apple-system, sans-serif`;
  ctx.fillText((fr.overall_fill_rate ?? 0) + "%", exec.x, 22 * P);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// ---- Equity candlesticks ---------------------------------------------
function drawCandles(curve) {
  const c = $("candles");
  if (!c) return;
  const ctx = c.getContext("2d");
  const w = c.width = c.clientWidth * devicePixelRatio;
  const h = c.height = 150 * devicePixelRatio;
  ctx.clearRect(0, 0, w, h);
  if (!curve || curve.length < 4) return;
  // Bucket the equity curve into candles (OHLC of equity within each bucket).
  const N = Math.min(28, Math.floor(curve.length / 2));
  const per = Math.max(1, Math.floor(curve.length / N));
  const candles = [];
  for (let i = 0; i < curve.length; i += per) {
    const seg = curve.slice(i, i + per).map(p => p.equity);
    if (!seg.length) continue;
    candles.push({ o: seg[0], c: seg[seg.length - 1],
                   hi: Math.max(...seg), lo: Math.min(...seg) });
  }
  const vals = candles.flatMap(k => [k.hi, k.lo]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || 1;
  const y = v => h - ((v - (lo - pad)) / ((hi + pad) - (lo - pad))) * h;
  const cw = w / candles.length;
  candles.forEach((k, i) => {
    const x = i * cw + cw / 2;
    const up = k.c >= k.o;
    ctx.strokeStyle = up ? "#30d158" : "#ff453a";
    ctx.fillStyle = up ? "#30d158" : "#ff453a";
    ctx.lineWidth = 1 * devicePixelRatio;
    ctx.beginPath(); ctx.moveTo(x, y(k.hi)); ctx.lineTo(x, y(k.lo)); ctx.stroke();
    const bw = Math.max(cw * 0.6, 2);
    const yo = y(k.o), yc = y(k.c);
    ctx.fillRect(x - bw / 2, Math.min(yo, yc), bw, Math.max(Math.abs(yc - yo), 1));
  });
  $("cdl-val").textContent = fmt(candles[candles.length - 1].c);
}

// ---- Orderbook / fill heatmap ----------------------------------------
function renderHeatmap(s) {
  const el = $("heatmap");
  if (!el) return;
  const trades = s.recent_trades || [];
  const COLS = 16, ROWS = 6, total = COLS * ROWS;
  let cells = "";
  for (let i = 0; i < total; i++) {
    const t = trades[i];
    let cls = "hm-empty", title = "";
    if (t) {
      const pl = t.realized_profit;
      cls = pl > 0 ? "hm-g" : (pl < 0 ? "hm-r" : "hm-y");
      const mag = Math.min(1, Math.abs(pl) / 50);
      title = `${t.kind} ${pl >= 0 ? "+" : ""}$${pl.toFixed(2)}`;
      cells += `<div class="hm ${cls}" style="opacity:${0.35 + 0.65 * mag}" title="${title}"></div>`;
      continue;
    }
    cells += `<div class="hm ${cls}"></div>`;
  }
  el.innerHTML = cells;
  $("hm-fill").textContent = (s.fill_report?.overall_fill_rate ?? 0) + "% fill";
}


function renderMM(mm, mode) {
  const card = $("mm-card");
  if (!mm || (mode !== "market_making" && mm.quotes_posted === 0)) {
    if (card) card.style.display = "none";
    return;
  }
  card.style.display = "";
  const cells = [
    ["NET P/L", fmt(mm.net_pnl), mm.net_pnl >= 0 ? "pos" : "neg"],
    ["REWARDS", fmt(mm.rewards), "pos"],
    ["SPREAD CAPTURE", fmt(mm.spread_pnl), mm.spread_pnl >= 0 ? "pos" : "neg"],
    ["INVENTORY P/L", fmt(mm.inventory_pnl), mm.inventory_pnl >= 0 ? "pos" : "neg"],
    ["QUOTES POSTED", mm.quotes_posted, ""],
    ["FILLS", mm.fills, ""],
    ["OPEN INVENTORY", mm.open_inventory + " sh", ""],
    ["MARKETS QUOTED", mm.markets_quoted, ""],
  ];
  $("mm").innerHTML =
    `<div class="strat-grid" style="grid-template-columns:repeat(4,1fr)">` +
    cells.map(([l, v, c]) =>
      `<div class="strat-cell"><div class="kpi-lbl">${l}</div>
         <div class="strat-pnl ${c}">${v}</div></div>`).join("") +
    `</div><div class="muted small" style="margin-top:8px">Market-making earns the liquidity reward + spread without racing for fills — the realistic edge on a regulated venue. Risk is inventory; quoting is capped at ${"" }the inventory limit. (Reward figures are a simulation of Kalshi's program in demo mode.)</div>`;
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
  cross_venue: "Cross-venue (Polymarket ↔ Kalshi)",
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
      <td class="route">${routeOf(o)}</td>
      <td>${escapeHtml(o.description)}</td>
      <td>${fmt(o.cost)}</td>
      <td>${fmt(o.guaranteed_payoff)}</td>
      <td class="pos">+${fmt(o.profit)}</td>
      <td class="pos">${o.edge_pct}%</td>
      <td class="${(o.fill_score ?? 1) >= 0.7 ? "pos" : ((o.fill_score ?? 1) >= 0.45 ? "" : "neg")}"
          title="Predicted fill score (TimesFM/heuristic): will the spread stay open to fill both legs?">${Math.round((o.fill_score ?? 1) * 100)}%</td>
      <td title="Bregman divergence = max extractable profit/unit">${o.bregman}</td>
      <td title="Frank-Wolfe iterations to converge">${o.fw_iters}</td>
      <td>${(o.confidence * 100).toFixed(0)}%</td>
    </tr>`).join("") || `<tr><td colspan="10" class="muted">scanning…</td></tr>`;
}

const VENUE_SHORT = { polymarket: "POLY", kalshi: "KALSHI" };
function routeOf(o) {
  const vs = [...new Set((o.legs || []).map(l => l.venue || "polymarket"))];
  if (vs.length > 1) return vs.map(v => VENUE_SHORT[v] || v.toUpperCase()).join(" ↔ ");
  return VENUE_SHORT[vs[0]] || (vs[0] || "POLY").toUpperCase();
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

function drawChart(curve, base, id) {
  const c = $(id || "chart");
  if (!c) return;
  const ctx = c.getContext("2d");
  const w = c.width = c.clientWidth * devicePixelRatio;
  const h = c.height = (c.clientHeight || 150) * devicePixelRatio;
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
