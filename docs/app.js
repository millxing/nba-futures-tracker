/* NBA Futures Tracker */
(() => {
  "use strict";

  const SHORT_SERIES = {
    "NBA: 2027 Champion": "NBA Champion",
    "NBA: 2027 Eastern Conference Champion": "East Champion",
    "NBA: 2027 Western Conference Champion": "West Champion",
    "NBA: Team to Make Playoffs": "Make Playoffs",
    "NBA Playoffs: Team to advance to Eastern Conference Semifinals": "East Semis",
    "NBA Playoffs: Team to advance to Western Conference Semifinals": "West Semis",
    "NBA Playoffs: Team to advance to Eastern Conference Finals": "East Finals",
    "NBA Playoffs: Team to advance to Western Conference Finals": "West Finals",
    "NBA: 2026-27 Rookie of the Year": "Rookie of Year",
  };
  const shortSeries = (s) => SHORT_SERIES[s] || s.replace(/^NBA(?: Playoffs)?:\s*/, "");

  // Categorical slots (validated dark-mode order) for time-series lines.
  const SERIES_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
  const MAX_LINES = 8;

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => (v == null ? "—" : v.toFixed(1));

  let DATA = null;
  const selectedMarkets = []; // market ids, insertion order = color slot

  // "Pre Week 1", plus "(partial)" when the snapshot predates the week's last game
  const snapLabel = (s) => s.label + (s.partial ? " (partial)" : "");
  // "Pre Week 1 · Sep 10, 8:00 PM ET (partial)" — friendly label with exact time
  const snapFull = (s) => (s.label === s.time ? s.time : `${s.label} · ${s.time}`) + (s.partial ? " (partial)" : "");

  fetch("data/data.json?t=" + Date.now())
    .then((r) => r.json())
    .then((d) => {
      DATA = d;
      init();
    })
    .catch((e) => {
      $("movers-list").innerHTML = `<div class="empty-note">Failed to load data: ${e}</div>`;
    });

  function init() {
    $("gen-note").textContent = `Data generated ${DATA.generated} · ${DATA.markets.length} markets · ${DATA.snapshots.length} snapshots`;
    buildSnapshotSelects();
    buildSeriesFilters();
    bindTabs();
    bindMoversControls();
    bindTimeSeriesControls();
    renderMovers();
    renderTimeSeries();
  }

  /* ---------------- tabs ---------------- */

  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchView(tab.dataset.view));
    });
  }

  function switchView(view) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.view === view;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on);
    });
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    $(`view-${view}`).classList.add("active");
    if (view === "series") renderTimeSeries();
  }

  /* ---------------- movers view ---------------- */

  function buildSnapshotSelects() {
    const from = $("from-select");
    const to = $("to-select");
    DATA.snapshots.forEach((s, i) => {
      const optF = new Option(snapLabel(s), i);
      const optT = new Option(snapLabel(s), i);
      optF.title = optT.title = s.time;
      from.add(optF);
      to.add(optT);
    });
    from.value = 0;
    to.value = DATA.snapshots.length - 1;
  }

  function buildSeriesFilters() {
    const teamSet = new Set(DATA.teamSeries);
    for (const sel of [$("series-filter"), $("ts-series-select")]) {
      sel.add(new Option(sel.id === "series-filter" ? "All markets" : "All series", "all"));
      const teams = document.createElement("optgroup");
      teams.label = "Team series";
      const indiv = document.createElement("optgroup");
      indiv.label = "Individual awards";
      DATA.series.forEach((s) => {
        (teamSet.has(s) ? teams : indiv).append(new Option(shortSeries(s), s));
      });
      sel.append(teams, indiv);
    }
  }

  const moversSort = { key: "delta", asc: false };

  function bindMoversControls() {
    ["from-select", "to-select", "series-filter"].forEach((id) =>
      $(id).addEventListener("change", renderMovers)
    );
    $("search-input").addEventListener("input", renderMovers);
    document.querySelectorAll(".col-sort").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.sort;
        if (moversSort.key === key) moversSort.asc = !moversSort.asc;
        else { moversSort.key = key; moversSort.asc = false; }
        renderMovers();
      });
    });
  }

  function renderMovers() {
    const fromIdx = +$("from-select").value;
    const toIdx = +$("to-select").value;
    const series = $("series-filter").value;
    const q = $("search-input").value.trim().toLowerCase();

    let rows = DATA.markets
      .filter((m) => series === "all" || m.series === series)
      .filter((m) => !q || m.name.toLowerCase().includes(q) || m.question.toLowerCase().includes(q))
      .map((m) => {
        const a = m.prices[fromIdx];
        const b = m.prices[toIdx];
        return { m, a, b, d: a != null && b != null ? b - a : null };
      });

    const keyFn = { delta: (r) => (r.d == null ? null : Math.abs(r.d)), from: (r) => r.a, to: (r) => r.b }[moversSort.key];
    rows.sort((x, y) => {
      const kx = keyFn(x);
      const ky = keyFn(y);
      if (kx == null) return 1;      // nulls always sink to the bottom
      if (ky == null) return -1;
      return moversSort.asc ? kx - ky : ky - kx;
    });
    document.querySelectorAll(".col-sort").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sort === moversSort.key);
      btn.classList.toggle("asc", btn.dataset.sort === moversSort.key && moversSort.asc);
    });

    const maxAbs = Math.max(0.5, ...rows.map((r) => Math.abs(r.d ?? 0)));
    const list = $("movers-list");
    list.innerHTML = "";
    const frag = document.createDocumentFragment();

    rows.forEach((r, i) => {
      const btn = document.createElement("button");
      btn.className = "mover-row";
      btn.type = "button";
      btn.title = `${r.m.question}\nChart this market`;
      const d = r.d;
      const cls = d == null || Math.abs(d) < 0.05 ? "zero" : d > 0 ? "pos" : "neg";
      const w = d == null ? 0 : (Math.abs(d) / maxAbs) * 50;
      btn.innerHTML = `
        <span class="rank">${i + 1}</span>
        <span class="name">${esc(r.m.name)}${series === "all" ? `<span class="stag">${esc(shortSeries(r.m.series))}</span>` : ""}</span>
        <span class="price">${fmt(r.a)}</span>
        <span class="price">${fmt(r.b)}</span>
        <span class="barcell"><span class="axis"></span>${
          d == null || Math.abs(d) < 0.05
            ? ""
            : `<span class="bar ${d > 0 ? "pos" : "neg"}" style="width:${w}%"></span>`
        }</span>
        <span class="delta ${cls}">${d == null ? "—" : (d > 0 ? "+" : "") + d.toFixed(1)}</span>`;
      btn.addEventListener("click", () => {
        addMarket(r.m.id, true);
        switchView("series");
      });
      frag.append(btn);
    });
    list.append(frag);

    const fromLabel = snapFull(DATA.snapshots[fromIdx]);
    const toLabel = snapFull(DATA.snapshots[toIdx]);
    const sortName = { delta: "absolute change", from: "From price", to: "To price" }[moversSort.key];
    $("movers-summary").textContent = `${rows.length} markets · ${fromLabel} → ${toLabel} · sorted by ${sortName} (${moversSort.asc ? "low to high" : "high to low"}) · click a row to chart it`;
    if (fromIdx === toIdx) {
      $("movers-summary").textContent += " · from and to are the same snapshot";
    }
  }

  /* ---------------- time-series view ---------------- */

  function bindTimeSeriesControls() {
    const input = $("ts-market-search");
    const sugg = $("ts-suggestions");

    const update = () => {
      const q = input.value.trim().toLowerCase();
      const series = $("ts-series-select").value;
      let pool = DATA.markets.filter((m) => series === "all" || m.series === series);
      if (q) pool = pool.filter((m) => m.name.toLowerCase().includes(q) || m.question.toLowerCase().includes(q));
      if (!q && series === "all") {
        sugg.hidden = true;
        return;
      }
      if (series === "all") pool = pool.slice(0, 20);
      sugg.innerHTML = "";
      pool.forEach((m) => {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = `<span>${esc(m.name)}</span><span class="sser">${esc(shortSeries(m.series))}</span>`;
        b.addEventListener("mousedown", (e) => {
          e.preventDefault();
          addMarket(m.id);
          input.value = "";
          sugg.hidden = true;
          renderTimeSeries();
        });
        sugg.append(b);
      });
      sugg.hidden = pool.length === 0;
    };

    input.addEventListener("input", update);
    input.addEventListener("focus", update);
    input.addEventListener("blur", () => setTimeout(() => (sugg.hidden = true), 150));
    $("ts-series-select").addEventListener("change", update);
  }

  function addMarket(id, exclusiveIfFull) {
    if (selectedMarkets.includes(id)) return;
    if (selectedMarkets.length >= MAX_LINES) {
      if (exclusiveIfFull) selectedMarkets.length = 0;
      else return;
    }
    selectedMarkets.push(id);
    renderTimeSeries();
  }

  function removeMarket(id) {
    const i = selectedMarkets.indexOf(id);
    if (i >= 0) selectedMarkets.splice(i, 1);
    renderTimeSeries();
  }

  function renderTimeSeries() {
    const chips = $("ts-chips");
    chips.innerHTML = "";
    selectedMarkets.forEach((id, i) => {
      const m = DATA.markets.find((x) => x.id === id);
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<span class="dot" style="background:${SERIES_COLORS[i]}"></span>
        <span>${esc(m.name)} <span class="chip-series">· ${esc(shortSeries(m.series))}</span></span>`;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "✕";
      x.setAttribute("aria-label", `Remove ${m.name}`);
      x.addEventListener("click", () => removeMarket(id));
      chip.append(x);
      chips.append(chip);
    });

    const empty = selectedMarkets.length === 0;
    $("ts-empty").style.display = empty ? "" : "none";
    $("ts-chart-wrap").style.display = empty ? "none" : "";
    $("ts-table-wrap").innerHTML = "";
    if (empty) return;

    drawChart();
    drawTable();
  }

  function drawTable() {
    const wrap = $("ts-table-wrap");
    const head = DATA.snapshots.map((s) => `<th title="${esc(s.time)}">${esc(snapLabel(s))}</th>`).join("");
    const body = selectedMarkets
      .map((id) => {
        const m = DATA.markets.find((x) => x.id === id);
        const cells = m.prices.map((p) => `<td>${fmt(p)}</td>`).join("");
        return `<tr><td>${esc(m.name)}</td>${cells}</tr>`;
      })
      .join("");
    wrap.innerHTML = `<table><thead><tr><th>Market (%)</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function drawChart() {
    const svg = $("ts-chart");
    const wrap = $("ts-chart-wrap");
    const W = Math.max(320, wrap.clientWidth - 10);
    const H = 420;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const markets = selectedMarkets.map((id) => DATA.markets.find((x) => x.id === id));
    const n = DATA.snapshots.length;
    const pad = { top: 18, right: 130, bottom: 34, left: 44 };
    const iw = W - pad.left - pad.right;
    const ih = H - pad.top - pad.bottom;

    const allVals = markets.flatMap((m) => m.prices).filter((v) => v != null);
    let yMax = Math.min(100, Math.ceil((Math.max(5, ...allVals) * 1.12) / 5) * 5);
    const yMin = 0;

    const xPos = (i) => pad.left + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
    const yPos = (v) => pad.top + ih - ((v - yMin) / (yMax - yMin)) * ih;

    const NS = "http://www.w3.org/2000/svg";
    const el = (tag, attrs, text) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
      if (text != null) e.textContent = text;
      svg.append(e);
      return e;
    };

    // gridlines + y ticks
    const step = yMax <= 25 ? 5 : yMax <= 50 ? 10 : 20;
    for (let v = yMin; v <= yMax; v += step) {
      const y = yPos(v);
      el("line", { x1: pad.left, x2: W - pad.right, y1: y, y2: y, class: v === 0 ? "axisline" : "gridline" });
      el("text", { x: pad.left - 8, y: y + 4, "text-anchor": "end", class: "ticktext" }, v + "%");
    }
    // x ticks
    DATA.snapshots.forEach((s, i) => {
      const anchor = n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle";
      const x = anchor === "start" ? xPos(i) - 30 : anchor === "end" ? xPos(i) + 30 : xPos(i);
      el("text", { x, y: H - pad.bottom + 18, "text-anchor": anchor, class: "ticktext" }, snapLabel(s));
    });

    // lines + points
    markets.forEach((m, mi) => {
      const color = SERIES_COLORS[mi];
      let dPath = "";
      let started = false;
      m.prices.forEach((p, i) => {
        if (p == null) { started = false; return; }
        dPath += `${started ? "L" : "M"}${xPos(i)},${yPos(p)}`;
        started = true;
      });
      if (dPath) el("path", { d: dPath, stroke: color, class: "series-line" });
      m.prices.forEach((p, i) => {
        if (p == null) return;
        el("circle", { cx: xPos(i), cy: yPos(p), r: 4, fill: color, class: "series-pt" });
      });
    });

    // direct end labels, collision-shifted
    const labels = markets
      .map((m, mi) => {
        const lastIdx = m.prices.map((p, i) => (p != null ? i : -1)).reduce((a, b) => Math.max(a, b), -1);
        return lastIdx < 0 ? null : { mi, y: yPos(m.prices[lastIdx]), v: m.prices[lastIdx], name: m.name };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) {
      if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    }
    labels.forEach((L) => {
      el("text", { x: W - pad.right + 8, y: L.y + 4, fill: SERIES_COLORS[L.mi], class: "end-label" },
        `${truncate(L.name, 14)} ${L.v.toFixed(1)}`);
    });

    // hover crosshair + tooltip
    const tooltip = $("ts-tooltip");
    const cross = el("line", { x1: 0, x2: 0, y1: pad.top, y2: H - pad.bottom, class: "crosshair", visibility: "hidden" });
    const overlay = el("rect", { x: pad.left, y: pad.top, width: iw, height: ih, fill: "transparent" });

    overlay.addEventListener("mousemove", (ev) => {
      const rect = svg.getBoundingClientRect();
      const mx = ((ev.clientX - rect.left) / rect.width) * W;
      let idx = 0;
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        const d = Math.abs(xPos(i) - mx);
        if (d < best) { best = d; idx = i; }
      }
      cross.setAttribute("x1", xPos(idx));
      cross.setAttribute("x2", xPos(idx));
      cross.setAttribute("visibility", "visible");
      const rowsHtml = markets
        .map((m, mi) => ({ m, mi, v: m.prices[idx] }))
        .filter((r) => r.v != null)
        .sort((a, b) => b.v - a.v)
        .map((r) => `<div class="tt-row"><span class="dot" style="background:${SERIES_COLORS[r.mi]}"></span>
             <span>${esc(truncate(r.m.name, 22))}</span><span class="v">${r.v.toFixed(1)}%</span></div>`)
        .join("");
      tooltip.innerHTML = `<div class="tt-date">${esc(snapFull(DATA.snapshots[idx]))}</div>${rowsHtml}`;
      tooltip.hidden = false;
      const wr = wrap.getBoundingClientRect();
      let left = ev.clientX - wr.left + 16;
      if (left + 230 > wr.width) left = ev.clientX - wr.left - 240;
      tooltip.style.left = left + "px";
      tooltip.style.top = Math.max(8, ev.clientY - wr.top - 30) + "px";
    });
    overlay.addEventListener("mouseleave", () => {
      tooltip.hidden = true;
      cross.setAttribute("visibility", "hidden");
    });
  }

  window.addEventListener("resize", () => {
    if (selectedMarkets.length && $("view-series").classList.contains("active")) drawChart();
  });

  /* ---------------- utils ---------------- */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function truncate(s, len) {
    return s.length > len ? s.slice(0, len - 1) + "…" : s;
  }
})();
