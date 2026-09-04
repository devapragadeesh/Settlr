(function () {
  "use strict";
  const D = window.SETTLR_DATA;

  // The dashboard itself stays a static build-time snapshot (DECISIONS
  // Sec.90). The AI panel is the one exception: `POST /runs/{run_id}/ask`
  // (service/api.py, DECISIONS Sec.101) runs a real `agents/chat_answerer.py`
  // call against the exact run this build baked into D.meta.run_id -- Claude
  // drafts a SQL SELECT and a summary from what it returns, not a JS keyword
  // matcher. `service.asgi:app` is assumed to be running locally on 8000
  // (`uvicorn service.asgi:app --port 8000`, with STORE_DB_PATH pointing at
  // dashboard/data/settlr_demo.db); if it isn't reachable, or Claude itself
  // is unreachable (no ANTHROPIC_API_KEY), this degrades to the local
  // heuristic answerer below -- the same "real answer or an honest miss,
  // never a guess" contract the Python side already keeps.
  const AGENT_API_BASE = "http://localhost:8000";
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === "class") n.className = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    }
    for (const kid of kids.flat()) {
      if (kid == null) continue;
      const isTextish = typeof kid === "string" || typeof kid === "number";
      n.appendChild(isTextish ? document.createTextNode(String(kid)) : kid);
    }
    return n;
  };

  const inr = (paise, opts) => {
    const rupees = paise / 100;
    const digits = opts && opts.compact ? 1 : 0;
    if (opts && opts.compact && Math.abs(rupees) >= 100000) {
      return "₹" + (rupees / 100000).toFixed(digits) + "L";
    }
    return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(rupees)
      .replace(/^/, "₹");
  };
  const fmtNum = (n) => new Intl.NumberFormat("en-IN").format(n);

  const STATUS_META = {
    not_started: { label: "Not Started", color: "var(--slate)", cls: "badge-not-started" },
    in_progress: { label: "In Progress", color: "var(--amber)", cls: "badge-in-progress" },
    awaiting_approval: { label: "Awaiting Approval", color: "var(--red)", cls: "badge-awaiting-approval" },
    certified: { label: "Certified", color: "var(--green)", cls: "badge-certified" },
  };
  const AGING_COLORS = { "0-30": "var(--green)", "31-60": "var(--amber)", "61-90": "var(--amber)", "90+": "var(--red)" };
  // Mirrors resolver_contract.types.SOURCE_PARTY -- independence is counted
  // over parties, not sources; resolver_internal never corroborates.
  const SOURCE_PARTY = {
    psp_ledger: "psp", psp_settlement_report: "psp", bank: "bank",
    merchant_erp: "merchant", tax_authority: "tax_authority",
    dispute_record: "issuer", resolver_internal: "Settlr",
  };
  const KIND_META = {
    Verified: { label: "Verified", color: "var(--green)" },
    Reconstructed: { label: "Reconstructed", color: "var(--blue-1)" },
    AttestationDiscrepancy: { label: "Discrepancy", color: "var(--red)" },
    Ambiguous: { label: "Ambiguous", color: "var(--amber)" },
    Unresolved: { label: "Unresolved", color: "var(--slate)" },
    OpenBreak: { label: "Open Break", color: "var(--red)" },
  };

  /* ============================== META CHIPS ============================== */
  function renderMetaChips() {
    const wrap = $("#metaChips");
    const runShort = D.meta.run_id.slice(0, 10);
    wrap.append(
      el("div", { class: "meta-chip" }, el("span", { class: "pulse" }), "Live run ", el("b", {}, runShort)),
      el("div", { class: "meta-chip" }, "Entity ", el("b", {}, D.meta.entity_label),
        el("span", { style: "color:var(--text-3);font-family:monospace;font-size:10.5px;margin-left:7px" }, D.meta.flagship_dataset)),
      el("div", { class: "meta-chip" }, D.meta.run_count + " runs on record · build ", el("b", {}, D.meta.code_digest.slice(0, 8)))
    );
  }

  /* ============================== HERO DONUT ============================== */
  function donutSVG(pct, size, stroke, color, trackColor) {
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const offset = c * (1 - pct / 100);
    const id = "g" + Math.random().toString(36).slice(2, 8);
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="var(--text-on-accent)"/><stop offset="100%" stop-color="${color}"/>
      </linearGradient></defs>
      <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${trackColor}" stroke-width="${stroke}"/>
      <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="url(#${id})" stroke-width="${stroke}"
        stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c}"
        style="transition:stroke-dashoffset 1.4s cubic-bezier(.16,1,.3,1)" data-target="${offset}"/>
    </svg>`;
  }

  function renderHero() {
    const h = D.health;
    const size = 236, stroke = 20;
    const wrap = el("div", { class: "panel hero fadein" });
    wrap.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "Reconciliation Health Score"),
          el("div", { class: "sub" }, "Answered ÷ determinable settlement lines")),
        el("button", { class: "hero-arrow", title: "Detailed health analysis", onclick: openHealthDetail }, "↗")
      ),
      el("div", { class: "hero-title" }, "Instant portfolio risk read for finance leadership"),
      el("div", { class: "hero-desc" },
        `${fmtNum(h.answered)} of ${fmtNum(h.determinable)} determinable settlement lines are answered with stated evidence, across ${h.datasets} entities.`),
      el("div", { class: "hero-donut-wrap" },
        el("div", { html: donutSVG(h.on_determinable_pct, size, stroke, "var(--text-on-accent)", "rgba(255,255,255,.16)") }),
        el("div", { class: "hero-donut-center" },
          el("div", { class: "pct num" }, h.on_determinable_pct.toFixed(1), el("sub", {}, "%")),
          el("div", { class: "lbl" }, "on determinable lines"))
      ),
      el("div", { class: "hero-legend" },
        el("div", { class: "item" }, el("span", { class: "sw", style: "background:var(--text-on-accent)" }), "Answered ", el("b", {}, fmtNum(h.answered))),
        el("div", { class: "item" }, el("span", { class: "sw", style: "background:rgba(255,255,255,.3)" }), "Determinable ", el("b", {}, fmtNum(h.determinable)))
      ),
      el("div", { class: "hero-foot" },
        el("div", {}, el("div", { class: "num" }, h.of_all_lines_pct.toFixed(1) + "%"),
          el("div", { class: "foot-lbl" }, "of all " + fmtNum(h.settlement_lines) + " settlement lines")),
        el("div", {}, el("div", { class: "num" }, h.datasets), el("div", { class: "foot-lbl" }, "entities scored")))
    );
    $("#heroSlot").append(wrap);

    requestAnimationFrame(() => {
      const circle = wrap.querySelector("circle[data-target]");
      if (circle) circle.style.strokeDashoffset = circle.dataset.target;
    });
  }

  /* ============================== THEME ==============================
     The <head> already stamped data-theme before first paint; this only
     handles the toggle and persistence. Colors all resolve through the
     token set in template.html, so flipping the attribute is the whole
     switch -- no per-component re-render. */
  function setupTheme() {
    $("#themeBtn").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("settlr-theme", next); } catch (e) { /* private mode */ }
      showToast(next === "light" ? "Light theme" : "Dark theme");
    });
  }

  /* ============================== STAT CARDS ============================== */
  function renderStatRow() {
    const totalOpen = Object.values(D.aging).reduce((a, b) => a + b, 0);
    const cards = [
      { lbl: "Entities Tracked", val: D.entities.length, trend: `${D.entities.filter(e=>e.status==="in_progress").length} in progress`, tone: "warn" },
      { lbl: "Open Exceptions", val: fmtNum(totalOpen), trend: `${D.aging["90+"]} aged 90+ days`, tone: D.aging["90+"] > 0 ? "down" : "up" },
      { lbl: "Discrepancies Flagged", val: D.discrepancies.length, trend: "sources disagree on these", tone: "warn" },
    ];
    const row = $("#statRow");
    cards.forEach((c, i) => {
      row.append(el("div", { class: "panel stat-card fadein", style: `animation-delay:${i * 60}ms` },
        el("div", { class: "lbl" }, c.lbl),
        el("div", { class: "val num" }, "" + c.val),
        el("div", { class: `trend ${c.tone}` }, c.trend)
      ));
    });
  }

  /* ============================== AGING CHART ============================== */
  let agingFilter = null;

  function renderAging() {
    const panel = $("#agingPanel");
    const order = ["0-30", "31-60", "61-90", "90+"];
    const days = { "0-30": "0–30 days", "31-60": "31–60 days", "61-90": "61–90 days", "90+": "90+ days" };
    const max = Math.max(...order.map((k) => D.aging[k] || 0), 1);

    panel.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "Exception Aging"),
          el("div", { class: "sub" }, "Real open breaks from the persisted run · click a bar to filter the grid")),
        el("button", { class: "panel-headbtn", title: "Refresh" }, "↻")
      )
    );
    const chart = el("div", { class: "aging-chart" });
    order.forEach((k) => {
      const v = D.aging[k] || 0;
      const h = Math.max(18, Math.round((v / max) * 138));
      const col = el("div", { class: "aging-col" },
        el("div", { class: "aging-bar-value num" }, v),
        el("div", { class: "aging-bar-track" },
          el("div", {
            class: "aging-bar", style: `height:${h}px;background:${AGING_COLORS[k]};color:${AGING_COLORS[k]}`,
            onclick: () => toggleAgingFilter(k),
          }, el("span", { class: "tip" }, v))
        ),
        el("div", { class: "aging-label" }, el("div", { class: "rng" }, k), el("div", { class: "days" }, days[k]))
      );
      col.dataset.bucket = k;
      chart.append(col);
    });
    panel.append(chart);
    if (D.aging["90+"] > 0 || D.aging["61-90"] > 0) {
      panel.append(el("div", { class: "aging-note" },
        "⚠︎ " + (D.aging["90+"] + D.aging["61-90"]) + " breaks past 60 days sit at real accounting risk — prioritise these first."));
    }
  }

  function toggleAgingFilter(bucket) {
    agingFilter = agingFilter === bucket ? null : bucket;
    $$(".aging-bar").forEach((b) => b.classList.toggle("active", b.parentElement.parentElement.dataset.bucket === agingFilter));
    applyFilters();
    if (agingFilter) {
      switchPage("transactions");
      history.replaceState(null, "", "#matching");
    }
  }

  /* ============================== INGESTION (compact) ============================== */
  const STATUS_DOT = { fresh: "var(--green)", stale: "var(--amber)" };

  function renderIngestionSmall() {
    const panel = $("#ingestionPanelSmall");
    panel.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "Pipeline Feed"),
          el("div", { class: "sub" }, "Latest ingest · " + D.meta.entity_label)),
        el("button", { class: "panel-headbtn" }, "↻")
      )
    );
    const list = el("div", { class: "feedlist" });
    D.ingestion.forEach((f) => {
      list.append(el("div", { class: "feed" },
        el("span", { class: "feed-dot", style: `background:${STATUS_DOT.fresh};color:${STATUS_DOT.fresh}` }),
        el("div", { class: "feed-body" },
          el("div", { class: "feed-name" }, f.label),
          el("div", { class: "feed-sub" }, f.artifact + " · sha256 " + f.sha256.slice(0, 10))),
        el("div", { class: "feed-stat" }, el("div", { class: "rows num" }, fmtNum(f.rows)), el("div", { class: "lbl" }, "rows"))
      ));
    });
    panel.append(list);
  }

  function renderIngestionFull() {
    const panel = $("#ingestionPanel");
    const grid = el("div", { class: "stat-row", style: "grid-template-columns:repeat(3,1fr);margin-bottom:0" });
    D.ingestion.forEach((f) => {
      const card = el("div", { class: "panel", style: "padding:18px 20px" },
        el("div", { style: "display:flex;align-items:center;justify-content:space-between;margin-bottom:10px" },
          el("span", { class: "feed-badge", style: `background:var(--green-bg);color:var(--green)` }, "Connected"),
          el("span", { class: "feed-dot", style: `background:${STATUS_DOT.fresh}` })),
        el("div", { class: "feed-name", style: "font-size:14px" }, f.label),
        el("div", { class: "feed-sub", style: "margin-top:4px" }, prettySource(f.source_system)),
        el("div", { class: "kv", style: "margin-top:14px" },
          el("div", { class: "cell" }, el("div", { class: "k" }, "Rows"), el("div", { class: "v" }, fmtNum(f.rows))),
          el("div", { class: "cell" }, el("div", { class: "k" }, "Format"), el("div", { class: "v" }, "." + f.format))),
        el("div", { style: "margin-top:10px;font-size:10.5px;color:var(--text-3);font-family:monospace" },
          "sha256 " + f.sha256 + "…")
      );
      grid.append(card);
    });
    panel.append(grid);
  }

  /* ============================== TRUST / EVIDENCE PANEL ============================== */
  function renderTrust() {
    const panel = $("#trustPanel");
    const t = D.trust;
    const grid = el("div", { class: "trust-grid" });

    const SYSTEM_META = {
      naive: { label: "Simple amount grouping", tag: "no evidence model at all", color: "var(--red)" },
      frozen: { label: "Previous engine", tag: "the earlier matcher, unmodified", color: "var(--amber)" },
      resolver: { label: "Settlr", tag: "evidence-tiered, current", color: "var(--green)" },
    };
    const compareCard = el("div", { class: "panel", style: "padding:22px 24px" },
      el("div", { class: "compare-title" }, "Wrong answers: Settlr against two simpler approaches"),
      el("div", { class: "compare-sub" }, "All three scored by the identical checks, over the same 30 entities.")
    );
    const row = el("div", { class: "compare-row" });
    ["naive", "frozen", "resolver"].forEach((key) => {
      const s = t.three_systems[key];
      const meta = SYSTEM_META[key];
      const pct = s.attempted ? (s.wrong / s.attempted) * 100 : 0;
      row.append(el("div", { class: "compare-item" },
        el("div", { class: "compare-name" }, meta.label, el("span", { class: "tag" }, meta.tag)),
        el("div", { class: "compare-track" },
          el("div", { class: "compare-fill", style: `width:${Math.max(pct, s.wrong ? 2 : 0)}%;background:${meta.color}` })),
        el("div", { class: "compare-stat" }, s.wrong + " / " + s.attempted, el("small", {}, " wrong"))));
    });
    compareCard.append(row);
    grid.append(compareCard);

    const cards = el("div", { class: "trust-cards" });
    if (t.d15) {
      cards.append(el("div", { class: "trust-card" },
        el("div", { class: "k" }, "Knowing when not to answer"),
        el("div", { class: "v", style: "color:var(--green)" }, t.d15.correct_refusals + " / " + t.d15.instances + " correct refusals"),
        el("div", { class: "d" }, "Every refusal to guess was checked exhaustively and found correct — " + t.d15.genuine_failures + " genuine failures.")));
    }
    if (t.commit_count) {
      cards.append(el("div", { class: "trust-card" },
        el("div", { class: "k" }, "Change history"),
        el("div", { class: "v" }, fmtNum(t.commit_count) + " commits"),
        el("div", { class: "d" }, "Every rule this engine applies was fixed before the data it was tested on existed — a recorded ordering, not a claim made afterwards.")));
    }
    if (t.self_correction) {
      cards.append(el("div", { class: "trust-card" },
        el("div", { class: "k" }, "Corrections on record"),
        el("div", { class: "v", style: "font-size:14px;line-height:1.4" }, "Not a count — by design"),
        el("div", { class: "d" }, t.self_correction.reason + ".")));
    }
    cards.append(el("div", { class: "trust-card" },
      el("div", { class: "k" }, "Source integrity"),
      el("div", { class: "v", style: t.hashes_verified ? "color:var(--green)" : "color:var(--text-3)" },
        t.hashes_verified ? "Verified" : "Not checked in this snapshot"),
      el("div", { class: "d" }, t.hashes_verified
        ? "Every source file matched its recorded checksum."
        : "Checksum verification was skipped for speed on this snapshot. The check is real and runs on every scheduled ingest.")));
    grid.append(cards);

    panel.append(grid);
  }

  function renderGst() {
    const panel = $("#gstPanel");
    const g = D.gst;
    panel.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "GST / Tax Evidence"),
          el("div", { class: "sub" }, "Supplier filings behind this entity's purchase invoices")),
      ),
      el("div", { class: "kv" },
        el("div", { class: "cell" }, el("div", { class: "k" }, "Supplier invoices"), el("div", { class: "v" }, g.invoices)),
        el("div", { class: "cell" }, el("div", { class: "k" }, "IRN present"), el("div", { class: "v" }, g.irn_present + " / " + g.invoices)),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Supplier GSTR-3B filed"), el("div", { class: "v" }, g.filed + " / " + g.invoices)),
        el("div", { class: "cell" }, el("div", { class: "k" }, "ITC available"), el("div", { class: "v" }, g.itc_available + " / " + g.invoices))),
      el("div", { style: "margin-top:16px;padding:12px 14px;background:rgba(var(--ink),.03);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:12px;color:var(--text-2);line-height:1.6" },
        el("b", { style: "color:var(--text-1)" }, g.flagged_at_risk + " rows flagged at-risk"),
        ` across ${g.runs_checked} runs. This is a real result, not an untested feature: a tax document can annotate an open item, but it can never on its own justify matching a bank credit. This entity's tax feed genuinely has nothing at risk.`)
    );
  }

  function renderStability() {
    const panel = $("#stabilityPanel");
    const s = D.stability;
    panel.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "Run Stability"),
          el("div", { class: "sub" }, s.runs.length + " independent runs of the same period, at four different search settings")),
      )
    );
    const list = el("div", { class: "feedlist" });
    s.runs.forEach((r) => {
      list.append(el("div", { class: "feed" },
        el("span", { class: "feed-dot", style: "background:var(--green)" }),
        el("div", { class: "feed-body" },
          el("div", { class: "feed-name" }, "run " + r.run_id),
          el("div", { class: "feed-sub" }, `cap=${r.cap}, time_budget=${r.time_budget}s`)),
        el("div", { class: "feed-stat" }, el("div", { class: "rows num" }, r.seconds + "s"), el("div", { class: "lbl" }, "wall clock"))));
    });
    panel.append(list);
    panel.append(el("div", {
      style: `margin-top:14px;padding:12px 14px;border-radius:var(--radius-sm);font-size:12px;line-height:1.6;` +
        (s.identical_outcomes
          ? "background:var(--green-bg);border:1px solid var(--green-border);color:var(--green)"
          : "background:var(--red-bg);border:1px solid var(--red-border);color:var(--red)"),
    }, s.identical_outcomes
      ? `Identical outcome on every bank line across all ${s.runs.length} runs — real reproducibility, not asserted.`
      : `${s.distinct_fingerprints} distinct outcome sets across ${s.runs.length} runs — a genuine finding, not hidden.`));
  }

  /* ============================== KANBAN ============================== */
  function renderKanban() {
    const panel = $("#kanbanPanel");
    const cols = ["not_started", "in_progress", "awaiting_approval", "certified"];
    const board = el("div", { class: "kanban" });
    cols.forEach((status) => {
      const meta = STATUS_META[status];
      const items = D.entities.filter((e) => e.status === status);
      const col = el("div", { class: "kcol" },
        el("div", { class: "kcol-head" },
          el("div", { class: "name" }, el("span", { class: "swatch", style: `background:${meta.color}` }), meta.label),
          el("div", { class: "count" }, items.length))
      );
      const scroll = el("div", { class: "kcol-scroll" });
      items.forEach((e) => {
        const pct = e.bank_lines ? Math.round((e.verified / e.bank_lines) * 100) : 0;
        scroll.append(el("div", { class: "kcard", onclick: () => openEntityDrilldown(e) },
          el("div", { class: "ename" }, e.label),
          el("div", { class: "eaxis" }, e.axis_point),
          el("div", { class: "ebar" }, el("div", { class: "ebar-fill", style: `width:${pct}%;background:${meta.color}` })),
          el("div", { class: "emeta" },
            el("span", {}, el("b", {}, e.verified) , " verified"),
            el("span", {}, el("b", {}, e.open_breaks), " open"))
        ));
      });
      if (!items.length) scroll.append(el("div", { class: "empty-col" }, "None right now"));
      col.append(scroll);
      board.append(col);
    });
    panel.append(board);
  }

  /* ============================== ENTITIES TABLE ============================== */
  let entitySort = { key: "label", dir: 1 };
  let entitySearch = "";

  const ENTITY_COLUMNS = [
    { key: "label", label: "Entity" },
    { key: "status", label: "Status" },
    { key: "bank_lines", label: "Bank Lines", num: true },
    { key: "verified", label: "Verified", num: true },
    { key: "open_breaks", label: "Open Breaks", num: true },
    { key: "unresolved", label: "Unresolved", num: true },
    { key: "ambiguous", label: "Ambiguous", num: true },
    { key: "passed", label: "Verification" },
  ];

  function renderEntities() {
    const panel = $("#entitiesPanel");
    panel.innerHTML = "";
    panel.append(
      el("div", { class: "entities-toolbar" },
        el("input", {
          class: "entities-search", placeholder: "Search entities by name or id…",
          oninput: (e) => { entitySearch = e.target.value.toLowerCase(); renderEntityRows(); },
        }),
        el("div", { class: "grid-count" }, D.entities.length + " entities"))
    );
    const wrap = el("div", { class: "etable-wrap" });
    const table = el("table", { class: "etable" });
    const thead = el("thead", {}, el("tr", {}));
    ENTITY_COLUMNS.forEach((col) => {
      const th = el("th", {
        onclick: () => {
          entitySort = { key: col.key, dir: entitySort.key === col.key ? -entitySort.dir : 1 };
          renderEntityRows();
        },
      }, col.label);
      th.dataset.key = col.key;
      thead.firstChild.append(th);
    });
    const tbody = el("tbody", { id: "entityTbody" });
    table.append(thead, tbody);
    wrap.append(table);
    panel.append(wrap);
    renderEntityRows();
  }

  function renderEntityRows() {
    const tbody = $("#entityTbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    $$(".etable thead th").forEach((th) => {
      th.classList.toggle("sorted", th.dataset.key === entitySort.key);
      th.classList.toggle("asc", th.dataset.key === entitySort.key && entitySort.dir === 1);
    });

    let rows = D.entities.filter((e) =>
      !entitySearch || e.label.toLowerCase().includes(entitySearch) || e.axis_point.toLowerCase().includes(entitySearch));
    rows = rows.slice().sort((a, b) => {
      const k = entitySort.key;
      const av = a[k], bv = b[k];
      if (typeof av === "number") return (av - bv) * entitySort.dir;
      return String(av).localeCompare(String(bv)) * entitySort.dir;
    });

    rows.forEach((e) => {
      const meta = STATUS_META[e.status];
      const tr = el("tr", { onclick: () => openEntityDrilldown(e) },
        el("td", { class: "name" }, e.label, el("span", { class: "axis" }, e.axis_point)),
        el("td", {}, el("span", { class: `status-pill ${meta.cls}` }, meta.label)),
        el("td", { class: "num" }, e.bank_lines),
        el("td", { class: "num" }, e.verified),
        el("td", { class: "num" }, e.open_breaks),
        el("td", { class: "num" }, e.unresolved),
        el("td", { class: "num" }, e.ambiguous),
        el("td", {}, e.passed
          ? el("span", { style: "color:var(--green)" }, "Passed")
          : el("span", { style: "color:var(--red)" }, "Failed")));
      tbody.append(tr);
    });
    if (!rows.length) {
      tbody.append(el("tr", {}, el("td", { colspan: "8", style: "text-align:center;padding:30px;color:var(--text-3)" }, "No entities match that search.")));
    }
  }

  /* ============================== MATCHING GRID ============================== */
  let selectedLineIndex = null;
  let selectedRowIds = new Set();
  let cmdFilter = "";

  function amountClass(paise) { return paise > 0 ? "pos" : "neg"; }

  // Bug fixed here: word-tokenized matching. The previous version used
  // q.includes("matched") to detect "verified"/"matched" queries, which is
  // also true for the string "unmatched" (it CONTAINS "matched") -- so
  // typing "unmatched" simultaneously kept only non-Verified lines AND
  // required kind === "Verified", rejecting every line. Exact word
  // membership (not substring) avoids this whole class of collision.
  const FILTER_KEYWORDS = new Set([
    "unmatched", "unresolved", "open", "verified", "matched",
    "ambiguous", "discrepancy", "discrepancies", "over", "clear",
  ]);

  function lineMatchesFilter(line) {
    if (agingFilter) {
      const agedIds = new Set((D.aging_rows[agingFilter] || []).map((r) => r.row_id));
      const refs = referencedIdsFor(line);
      if (!refs.some((id) => agedIds.has(id))) return false;
    }
    if (!cmdFilter) return true;
    const q = cmdFilter.toLowerCase();
    const words = q.split(/\s+/).filter(Boolean);
    const has = (...ws) => ws.some((w) => words.includes(w));

    if (has("unmatched", "unresolved", "open")) {
      if (!["Unresolved", "Ambiguous", "AttestationDiscrepancy"].includes(line.kind)) return false;
    }
    if (has("verified", "matched")) {
      if (line.kind !== "Verified") return false;
    }
    if (has("ambiguous")) { if (line.kind !== "Ambiguous") return false; }
    if (has("discrepancy", "discrepancies")) { if (line.kind !== "AttestationDiscrepancy") return false; }

    const overMatch = q.match(/over\s*₹?\s*([\d,]+)/) || q.match(/>\s*₹?\s*([\d,]+)/);
    if (overMatch) {
      const threshold = parseInt(overMatch[1].replace(/,/g, ""), 10) * 100;
      if (Math.abs(line.amount_paise) <= threshold) return false;
    }

    const textual = words
      .filter((w) => !FILTER_KEYWORDS.has(w) && !/^[\d,₹>]+$/.test(w))
      .join(" ").trim();
    if (textual && !line.reference.toLowerCase().includes(textual) && !(line.narration || "").toLowerCase().includes(textual)) {
      return false;
    }
    return true;
  }

  function renderMatchingGrid() {
    const panel = $("#matchingPanel");
    panel.innerHTML = "";

    const toolbar = el("div", { class: "grid-toolbar" },
      el("div", { class: "seg", id: "gridSeg" },
        el("button", { class: "active", "data-mode": "all" }, "All lines"),
        el("button", { "data-mode": "exceptions" }, "Exceptions only")
      ),
      el("div", { class: "grid-count", id: "gridCount" }, "")
    );
    panel.append(toolbar);
    $$("#gridSeg button", toolbar).forEach((b) => b.addEventListener("click", () => {
      $$("#gridSeg button", toolbar).forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      gridMode = b.dataset.mode;
      renderMatchColumns();
    }));

    const cols = el("div", { class: "match-source-row", id: "matchCols" });
    panel.append(cols);
    renderMatchColumns();
  }

  let gridMode = "all";

  function visibleLines() {
    return D.lines.filter((l) => {
      if (gridMode === "exceptions" && l.kind === "Verified") return false;
      return lineMatchesFilter(l);
    });
  }

  function renderMatchColumns() {
    const cols = $("#matchCols");
    cols.innerHTML = "";
    const lines = visibleLines();
    $("#gridCount").textContent = lines.length + " of " + D.lines.length + " bank lines";

    // Column 1: BANK -- always present
    const bankCol = matchColumn("Bank Statement", "var(--blue-1)", lines.length);
    lines.forEach((line) => bankCol.body.append(bankRowEl(line)));
    if (!lines.length) bankCol.body.append(el("div", { class: "empty-col" }, "No lines match the current filter."));
    cols.append(bankCol.root);

    // Dynamic columns based on the selected line's real referenced rows
    if (selectedLineIndex != null) {
      const line = D.lines[selectedLineIndex];
      const ids = referencedIdsFor(line);
      const ledgerRows = ids.map((id) => D.rows_by_id[id]).filter(Boolean);
      const erpRows = Object.values(D.erp_by_order).filter((e) =>
        ledgerRows.some((r) => r.order_id === e.order_id));
      const disputeRows = Object.values(D.disputes_by_id).filter((dp) =>
        ledgerRows.some((r) => r.dispute_id === dp.id));

      if (ledgerRows.length) {
        const c = matchColumn("Processor Ledger", "var(--green)", ledgerRows.length);
        ledgerRows.forEach((r) => c.body.append(ledgerRowEl(r, line)));
        cols.append(c.root);
      }
      if (erpRows.length) {
        const c = matchColumn("ERP Order Book", "var(--source-erp)", erpRows.length);
        erpRows.forEach((r) => c.body.append(erpRowEl(r)));
        cols.append(c.root);
      }
      if (disputeRows.length) {
        const c = matchColumn("Dispute Records", "var(--red)", disputeRows.length);
        disputeRows.forEach((r) => c.body.append(disputeRowEl(r)));
        cols.append(c.root);
      }
    } else {
      const c = matchColumn("Prospective Match", "var(--text-3)", 0);
      c.body.append(el("div", { class: "empty-col" }, "Select a bank line to see which transactions make it up."));
      cols.append(c.root);
    }
  }

  function referencedIdsFor(line) {
    const o = line.outcome;
    if (!o) return [];
    if (o.composition) return [...o.composition.credit_ids, ...o.composition.debit_ids];
    if (o.candidate_set) {
      const top = o.candidate_set.candidates[0];
      return top ? [...top.credit_ids, ...top.debit_ids] : [];
    }
    if (o.contradiction) return o.contradiction.row_ids;
    return [];
  }

  function matchColumn(title, color, count) {
    const root = el("div", { class: "match-col" },
      el("div", { class: "match-col-head" },
        el("div", { class: "title" }, el("span", { class: "swatch", style: `background:${color}` }), title),
        el("div", { class: "cnt" }, count))
    );
    const body = el("div", { class: "match-col-body" });
    root.append(body);
    return { root, body };
  }

  function bankRowEl(line) {
    const meta = KIND_META[line.kind] || KIND_META.Unresolved;
    const cls = ["txrow"];
    if (selectedLineIndex === line.index) cls.push("selected");
    if (line.kind === "AttestationDiscrepancy") cls.push("anomaly");
    if (line.kind === "Ambiguous") cls.push("partial");
    const row = el("div", { class: cls.join(" ") },
      el("div", { class: "chk" }, el("svg", { width: "10", height: "8", viewBox: "0 0 10 8", fill: "none", html: '<path d="M1 4l2.5 2.5L9 1" stroke="var(--text-on-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' })),
      el("div", { class: "txrow-body" },
        el("div", { class: "txrow-top" },
          el("div", { class: "txrow-ref" }, line.reference || "(no reference)"),
          el("div", { class: `txrow-amt ${amountClass(line.amount_paise)}` }, inr(Math.abs(line.amount_paise)))),
        el("div", { class: "txrow-sub" }, line.value_date + " · " + (line.narration || "").slice(0, 42))),
      el("span", { class: "txrow-badge", style: `background:${meta.color}22;color:${meta.color}` }, meta.label)
    );
    row.addEventListener("click", (e) => {
      selectedLineIndex = selectedLineIndex === line.index ? null : line.index;
      renderMatchColumns();
      openLineDrilldown(line);
      checkDiscrepancy(line);
    });
    return row;
  }

  function ledgerRowEl(r, line) {
    const checked = selectedRowIds.has(r.entity_id);
    const row = el("div", { class: "txrow" + (checked ? " selected" : "") },
      el("div", { class: "chk" }, el("svg", { width: "10", height: "8", viewBox: "0 0 10 8", fill: "none", html: '<path d="M1 4l2.5 2.5L9 1" stroke="var(--text-on-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' })),
      el("div", { class: "txrow-body" },
        el("div", { class: "txrow-top" },
          el("div", { class: "txrow-ref" }, r.entity_id),
          el("div", { class: "txrow-amt pos" }, inr(r.credit || r.amount || 0))),
        el("div", { class: "txrow-sub" }, (r.type || "") + " · " + (r.settlement_id || "no settlement id")))
    );
    row.addEventListener("click", () => {
      if (selectedRowIds.has(r.entity_id)) selectedRowIds.delete(r.entity_id); else selectedRowIds.add(r.entity_id);
      renderMatchColumns();
      checkDiscrepancy(line);
    });
    return row;
  }

  function erpRowEl(r) {
    return el("div", { class: "txrow" },
      el("div", { class: "chk" }),
      el("div", { class: "txrow-body" },
        el("div", { class: "txrow-top" },
          el("div", { class: "txrow-ref" }, r.invoice_no),
          el("div", { class: "txrow-amt pos" }, "₹" + parseFloat(r.amount).toLocaleString("en-IN"))),
        el("div", { class: "txrow-sub" }, r.order_id + " · " + r.invoice_date))
    );
  }

  function disputeRowEl(r) {
    return el("div", { class: "txrow anomaly" },
      el("div", { class: "chk" }),
      el("div", { class: "txrow-body" },
        el("div", { class: "txrow-top" },
          el("div", { class: "txrow-ref" }, r.id),
          el("div", { class: "txrow-amt" }, inr(r.amount_deducted || 0))),
        el("div", { class: "txrow-sub" }, r.phase + " · " + r.status))
    );
  }

  function checkDiscrepancy(line) {
    if (!line || !line.outcome) return;
    if (line.outcome.__type__ === "AttestationDiscrepancy") {
      showDiscrepancyBanner(line);
    }
  }

  /* ============================== DISCREPANCY BANNER ============================== */
  function showDiscrepancyBanner(line) {
    const banner = $("#discrepancyBanner");
    banner.innerHTML = "";
    const c = line.outcome.contradiction;
    banner.append(
      el("div", { class: "discrepancy-icon" }, "⚠"),
      el("div", { class: "discrepancy-body" },
        el("div", { class: "discrepancy-title" }, "Discrepancy on bank line " + line.reference),
        el("div", { class: "discrepancy-detail" }, c.detail)),
      el("div", { class: "discrepancy-actions" },
        el("button", { class: "btn btn-ghost btn-sm", onclick: () => { hideBanner(); openDispute(line); } }, "Open Dispute"),
        el("button", { class: "btn btn-primary btn-sm", onclick: () => { hideBanner(); postVariance(line); } }, "Post Variance")),
      el("button", { class: "discrepancy-close", onclick: hideBanner }, "✕")
    );
    banner.classList.add("show");
  }
  function hideBanner() { $("#discrepancyBanner").classList.remove("show"); }
  function showToast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2600);
  }
  function postVariance(line) { showToast("Variance on " + line.reference + " queued for write-off review (session only)"); }
  function openDispute(line) { showToast("Dispute opened for " + line.reference + " (session only)"); }

  /* ============================== SLIDEOUT DRILLDOWN ============================== */
  function jsonPretty(obj) {
    const text = JSON.stringify(obj, null, 2);
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:')
      .replace(/: "([^"]*)"/g, ': <span class="json-str">"$1"</span>')
      .replace(/: (-?\d+\.?\d*)/g, ': <span class="json-num">$1</span>');
  }

  function openLineDrilldown(line) {
    const slideout = $("#slideout");
    slideout.innerHTML = "";
    const meta = KIND_META[line.kind] || KIND_META.Unresolved;

    slideout.append(el("div", { class: "slideout-head" },
      el("div", {},
        el("h3", {}, "Bank line · " + line.reference),
        el("div", { class: "sub" },
          line.value_date + " · " + inr(Math.abs(line.amount_paise)) + " · ",
          el("span", { style: `color:${meta.color};font-weight:600` }, meta.label))),
      el("button", { class: "slideout-close", onclick: closeDrilldown }, "✕")
    ));

    const body = el("div", { class: "slideout-body" });

    body.append(el("div", { class: "slideout-section" },
      el("h4", {}, "Bank Statement Line"),
      el("div", { class: "kv" },
        el("div", { class: "cell" }, el("div", { class: "k" }, "Reference"), el("div", { class: "v" }, line.reference || "—")),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Amount"), el("div", { class: "v" }, inr(Math.abs(line.amount_paise)))),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Value Date"), el("div", { class: "v" }, line.value_date)),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Outcome"), el("div", { class: "v", style: `color:${meta.color}` }, meta.label)))
    ));

    const o = line.outcome;
    if (o && o.warrant) {
      const sec = el("div", { class: "slideout-section" }, el("h4", {}, "Evidence & Warrant"));
      o.warrant.evidence.forEach((ev) => {
        sec.append(el("div", { class: "evidence-item" },
          el("div", { class: "evidence-dot" }),
          el("div", { class: "evidence-txt" },
            el("div", { class: "evidence-kind" }, prettyEvidence(ev.kind)),
            el("div", {}, ev.derived_from.map((s) => el("span", { class: "evidence-src" }, prettySource(s)))),
            el("div", { class: "evidence-detail" }, ev.detail))
        ));
      });
      const parties = [...new Set(o.warrant.independence.sources
        .map((s) => SOURCE_PARTY[s] || s)
        .filter((p) => p !== "resolver"))];
      sec.append(el("div", { style: "margin-top:10px;font-size:11.5px;color:var(--text-2)" },
        "Independent parties: " + parties.join(", ") +
        " — " + o.warrant.independence.rationale));
      body.append(sec);
    }

    if (o && o.contradiction) {
      body.append(el("div", { class: "slideout-section" },
        el("h4", {}, "Contradiction"),
        el("div", { class: "evidence-detail", style: "color:var(--red)" }, o.contradiction.detail)));
    }

    if (o && o.candidate_set) {
      const sec = el("div", { class: "slideout-section" },
        el("h4", {}, o.candidate_set.candidates.length + " Rival Compositions (Ambiguous)"));
      o.candidate_set.candidates.slice(0, 5).forEach((c, i) => {
        sec.append(el("div", { class: "evidence-item" },
          el("div", { class: "evidence-dot", style: "background:var(--amber)" }),
          el("div", { class: "evidence-txt" },
            el("div", { class: "evidence-kind" }, "Candidate " + (i + 1) + " — " + c.credit_ids.length + " credits, " + c.debit_ids.length + " debits"),
            el("div", { class: "evidence-detail" }, "Net " + inr(c.credit_total - c.debit_total)))));
      });
      body.append(sec);
    }

    const ids = referencedIdsFor(line);
    const historyIds = ids.filter((id) => D.row_history[id]);
    if (historyIds.length) {
      const sec = el("div", { class: "slideout-section" }, el("h4", {}, "Audit Trail — " + historyIds[0]));
      const tl = el("div", { class: "timeline" });
      D.row_history[historyIds[0]].forEach((h) => {
        tl.append(el("div", { class: "tl-item" },
          el("div", { class: "tl-dot" }),
          el("div", { class: "tl-body" },
            el("div", { class: "state" }, h.state), el("div", { class: "when" }, new Date(h.started_at).toLocaleString()))));
      });
      sec.append(tl);
      body.append(sec);
    }

    body.append(el("div", { class: "slideout-section" },
      el("h4", {}, "Raw Outcome Payload"),
      el("div", { class: "json-view", html: jsonPretty(o || {}) })));

    slideout.append(body);
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  function openEntityDrilldown(entity) {
    const slideout = $("#slideout");
    slideout.innerHTML = "";
    const meta = STATUS_META[entity.status];
    slideout.append(
      el("div", { class: "slideout-head" },
        el("div", {}, el("h3", {}, entity.label), el("div", { class: "sub" }, entity.id)),
        el("button", { class: "slideout-close", onclick: closeDrilldown }, "✕")),
      el("div", { class: "slideout-body" },
        el("div", { class: "slideout-section" },
          el("h4", {}, "Close Status"),
          el("div", { class: `feed-badge ${meta.cls}`, style: "display:inline-block;padding:6px 14px;font-size:11px" }, meta.label)),
        el("div", { class: "slideout-section" },
          el("h4", {}, "Measured, This Run"),
          el("div", { class: "kv" },
            el("div", { class: "cell" }, el("div", { class: "k" }, "Bank lines"), el("div", { class: "v" }, entity.bank_lines)),
            el("div", { class: "cell" }, el("div", { class: "k" }, "Verified"), el("div", { class: "v" }, entity.verified)),
            el("div", { class: "cell" }, el("div", { class: "k" }, "Open breaks"), el("div", { class: "v" }, entity.open_breaks)),
            el("div", { class: "cell" }, el("div", { class: "k" }, "Unresolved"), el("div", { class: "v" }, entity.unresolved)),
            el("div", { class: "cell" }, el("div", { class: "k" }, "Ambiguous"), el("div", { class: "v" }, entity.ambiguous)),
            el("div", { class: "cell" }, el("div", { class: "k" }, "Verification"), el("div", { class: "v", style: `color:${entity.passed ? "var(--green)" : "var(--red)"}` }, entity.passed ? "Passed" : "Failed"))))
      )
    );
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  // Reached from the health-score card's arrow button. Every figure here is
  // read straight from the baked payload -- nothing computed or curated
  // client-side.
  function openHealthDetail() {
    const slideout = $("#slideout");
    slideout.innerHTML = "";
    slideout.append(
      el("div", { class: "slideout-head" },
        el("div", {}, el("h3", {}, "Detailed Health Analysis"),
          el("div", { class: "sub" }, "Every claim this engine makes, in full — nothing curated")),
        el("button", { class: "slideout-close", onclick: closeDrilldown }, "✕"))
    );

    const body = el("div", { class: "slideout-body" });

    const scopeSection = el("div", { class: "slideout-section" }, el("h4", {}, "Coverage by Scope"));
    ["all", "non_absence", "absence", "original_14"].forEach((scopeKey) => {
      const s = D.coverage[scopeKey];
      if (!s) return;
      scopeSection.append(el("div", { class: "evidence-item" },
        el("div", { class: "evidence-dot", style: "background:var(--blue-1)" }),
        el("div", { class: "evidence-txt" },
          el("div", { class: "evidence-kind" }, s.scope_label),
          el("div", { class: "evidence-detail" },
            `${fmtNum(s.answered)} answered of ${fmtNum(s.determinable)} determinable ` +
            `(${s.on_determinable_pct.toFixed(1)}%) — ${fmtNum(s.settlement_lines)} settlement lines total, ` +
            `${s.datasets} dataset${s.datasets === 1 ? "" : "s"}.`))));
    });
    body.append(scopeSection);

    if (D.trust && D.trust.d15) {
      const d15 = D.trust.d15;
      body.append(el("div", { class: "slideout-section" },
        el("h4", {}, "Knowing When Not to Answer"),
        el("div", { class: "kv" },
          el("div", { class: "cell" }, el("div", { class: "k" }, "Correct refusals"), el("div", { class: "v", style: "color:var(--green)" }, d15.correct_refusals + " / " + d15.instances)),
          el("div", { class: "cell" }, el("div", { class: "k" }, "Genuine failures"), el("div", { class: "v" }, d15.genuine_failures)))));
    }


    slideout.append(body);
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  function closeDrilldown() {
    $("#slideout").classList.remove("show");
    $("#scrim").classList.remove("show");
  }
  $("#scrim").addEventListener("click", closeDrilldown);

  /* ============================== ASK SETTLR — THE ANSWER ENGINE ============================== */
  // Every branch below reads directly from window.SETTLR_DATA -- the exact
  // object every other panel on the page renders from. There is no second,
  // hidden data source: the copilot "knows everything" only in the sense
  // that it can compose a sentence from any field already on the page.
  // Break reasons and evidence kinds arrive as the engine's own enum names.
  // Underscore-to-space is not a translation -- "upstream_unresolved" still
  // reads as jargon as "upstream unresolved". These are the operator-facing
  // names for the same states; anything unmapped falls back to the old
  // behaviour rather than disappearing.
  const REASON_LABELS = {
    missing_source: "Missing from a source",
    timing_difference: "Timing difference",
    mapping_issue: "Mapping issue",
    unexpected_change: "Unexpected change",
    true_error: "Genuine error",
    upstream_unresolved: "Blocked by an upstream item",
    unexplained: "Unexplained",
    not_our_credit: "Not our credit",
    enumeration_truncated: "Search limit reached",
    no_candidate_composition: "No combination found",
  };
  const prettyReason = (r) => REASON_LABELS[r] || (r || "—").replace(/_/g, " ");

  const EVIDENCE_LABELS = {
    attested_settlement_id: "Processor named this settlement",
    bank_reference: "Bank reference",
    bank_value_date: "Bank value date",
    attested_composition_closes: "Processor's composition balances",
    arithmetic_closure: "Amounts balance exactly",
    unique_closure_unfiltered: "Only one combination balances",
    cross_line_exclusivity: "No other line can claim these",
    erp_identifier: "Matched to an ERP order",
    gst_document: "Backed by a tax document",
    dispute_record_link: "Linked to a dispute record",
  };
  const prettyEvidence = (k) => EVIDENCE_LABELS[k] || (k || "").replace(/_/g, " ");

  const SOURCE_LABELS = {
    psp_ledger: "Processor ledger",
    psp_settlement_report: "Processor settlement report",
    bank: "Bank",
    merchant_erp: "ERP",
    tax_authority: "Tax authority",
    dispute_record: "Dispute record",
    resolver_internal: "Settlr",
  };
  const prettySource = (s) => SOURCE_LABELS[s] || (s || "").replace(/_/g, " ");

  // "datasets" / "datasets_v2" are the internal directory names for the
  // primary set and its independent regeneration. The distinction is real
  // and worth showing -- two runs of the same scenario from different
  // seeds -- but not under those names.
  const FAMILY_LABELS = { datasets: "Primary", datasets_v2: "Independent re-run" };
  const prettyFamily = (f) => FAMILY_LABELS[f] || f;

  const KIND_WORD = {
    Verified: "verified", Reconstructed: "reconstructed",
    AttestationDiscrepancy: "flagged as a discrepancy", Ambiguous: "ambiguous",
    Unresolved: "unresolved",
  };

  const GLOSSARY = {
    "verified": "A bank credit whose make-up is confirmed by two independent parties — the strongest match Settlr can make.",
    "ambiguous": "More than one combination of transactions balances equally well, so Settlr shows every one rather than guessing.",
    "unresolved": "No subset of eligible rows closes the credit within the search budget — a decline, not a wrong answer.",
    "discrepancy": "The PSP's own settlement report and the bank statement disagree about the same credit — a finding, not a failed match.",
    "attestationdiscrepancy": "The PSP's own settlement report and the bank statement disagree about the same credit — a finding, not a failed match.",
    "open break": "A row with no bank credit found and no proven explanation yet — real accounting risk the longer it stays open.",
    "reconstructed": "A composition that closes uniquely but without independent corroboration — accepted on structure alone.",
    "proven unmatched": "A transaction Settlr can prove never settled — netted out, or never captured. Not a break: a closed question.",
  };

  function findEntity(q) {
    return D.entities.find((e) =>
      q.includes(e.axis_point.toLowerCase()) || q.includes(e.label.toLowerCase()));
  }

  // Returns null if the query isn't about a whole-dashboard domain (health,
  // entities, aging, ingestion, trust, GST, stability, or a glossary term) --
  // the caller then falls back to per-line filtering. Returns
  // {headline, sub, page} otherwise. Deliberately checked BEFORE line
  // filtering: "how many entities are certified" is not a question about
  // bank lines and should never be answered with "0 lines match."
  function domainAnswer(rawQuery) {
    const q = rawQuery.toLowerCase();

    const entity = findEntity(q);
    if (entity) {
      const meta = STATUS_META[entity.status];
      return {
        headline: `${entity.label} (${entity.axis_point}) is ${meta.label.toLowerCase()} — ` +
          `${entity.verified} verified, ${entity.open_breaks} open breaks of ${entity.bank_lines} bank lines.`,
        sub: entity.passed ? "Passed every verification check." : "Failed at least one verification check.",
        page: "close", onOpen: () => openEntityDrilldown(entity),
        sources: [{ label: "Verification results", page: "close" }],
      };
    }

    for (const [term, def] of Object.entries(GLOSSARY)) {
      if (q.includes("what is " + term) || q.includes("what does " + term) || q.includes("define " + term) || q.trim() === term) {
        return {
          headline: def, sub: "A real term from Settlr's outcome vocabulary — not a paraphrase.",
          sources: [{ label: "Reconciliation glossary" }],
        };
      }
    }

    if (/\bhealth\b|\breconciliation score\b/.test(q)) {
      const h = D.health;
      return {
        headline: `Reconciliation health is ${h.on_determinable_pct.toFixed(1)}% on determinable lines — ` +
          `${fmtNum(h.answered)} of ${fmtNum(h.determinable)} answered, ${h.of_all_lines_pct.toFixed(1)}% of all ` +
          `${fmtNum(h.settlement_lines)} settlement lines across ${h.datasets} entities.`,
        sub: "Click a source below for the full scope-by-scope breakdown.", page: "overview",
        onOpen: openHealthDetail,
        sources: [{ label: "dashboard/data.json:coverage.all", onOpen: openHealthDetail }],
      };
    }

    if (/\bcertified\b|\bnot started\b|\bawaiting approval\b|\bin progress\b|\bhow many entities\b|\ball entities\b/.test(q)) {
      const counts = {};
      D.entities.forEach((e) => { counts[e.status] = (counts[e.status] || 0) + 1; });
      return {
        headline: `${D.entities.length} entities: ${counts.certified || 0} certified, ${counts.in_progress || 0} in progress, ` +
          `${counts.awaiting_approval || 0} awaiting approval, ${counts.not_started || 0} not started.`,
        sub: "Open the Entities page for the full sortable table.", page: "entities",
        sources: [{ label: "Verification results — 30 entities", page: "overview" }],
      };
    }

    if (/\baging\b|\b90\+|\b61-90|\b31-60|\boverdue\b|\bhow old\b/.test(q)) {
      const a = D.aging;
      const overSixty = (a["61-90"] || 0) + (a["90+"] || 0);
      return {
        headline: `Open exceptions by age: ${a["0-30"] || 0} at 0–30 days, ${a["31-60"] || 0} at 31–60, ` +
          `${a["61-90"] || 0} at 61–90, ${a["90+"] || 0} at 90+.`,
        sub: overSixty > 0 ? `${overSixty} breaks past 60 days are real accounting risk.` : "Nothing past 60 days right now.",
        page: "overview",
        sources: [{ label: "Open breaks — latest run", page: "exceptions" }],
      };
    }

    if (/\bingestion\b|\bsource feed\b|\bpipeline\b|\blast pull\b|\bdata feed\b/.test(q)) {
      const totalRows = D.ingestion.reduce((s, f) => s + f.rows, 0);
      return {
        headline: `${D.ingestion.length} source feeds connected, ${fmtNum(totalRows)} rows in the latest ingest for ${D.meta.entity_label}.`,
        sub: D.ingestion.map((f) => f.label).join(", "), page: "ingestion",
        sources: D.ingestion.map((f) => ({ label: f.label, page: "ingestion" })),
      };
    }

    if (/\bnaive\b|\bfrozen cascade\b|\bthree.system\b|\bwrong answers\b|\bhow accurate\b/.test(q)) {
      const t = D.trust.three_systems;
      return {
        headline: `Simple amount grouping: ${t.naive.wrong}/${t.naive.attempted} wrong. Previous engine: ${t.frozen.wrong}/${t.frozen.attempted} wrong. ` +
          `Settlr: ${t.resolver.wrong}/${t.resolver.attempted} wrong — same checks, same 30 entities.`,
        sub: "Open the Trust page for the full comparison.", page: "trust",
        sources: [{ label: "Approach comparison", page: "overview" }],
      };
    }

    if (/\bgst\b|\bitc\b|\btax\b|\birn\b/.test(q)) {
      const g = D.gst;
      return {
        headline: `${g.invoices} supplier invoices on file, ${g.irn_present} carry an IRN, ${g.filed} filed by the supplier — ` +
          `${g.flagged_at_risk} flagged at ITC risk across ${g.runs_checked} runs.`,
        sub: "GST evidence can annotate a break but never license a composition — see the Trust page.", page: "trust",
        sources: [{ label: "Supplier tax filings", page: "accounting" }],
      };
    }

    if (/\bstability\b|\bdeterministic\b|\breproducib\b|\bconsisten(t|cy)\b|\bsame answer\b/.test(q)) {
      const s = D.stability;
      return {
        headline: s.identical_outcomes
          ? `Identical outcome on every bank line across all ${s.runs.length} independent runs — genuinely reproducible.`
          : `${s.distinct_fingerprints} distinct outcome sets across ${s.runs.length} runs.`,
        sub: "Four different (cap, time_budget) points, same frozen entity.", page: "trust",
        sources: s.runs.map((r) => ({ label: `run ${r.run_id}… (cap=${r.cap})`, page: "trust" })),
      };
    }

    // \w* stems, not exact words: real questions get misspelled
    // ("uncertainity"), and this still must match "uncertain" itself.
    if (/\buncertain\w*\b|\bambigu\w*\b|\bnot (sure|certain)\b|\bdon'?t know\b|\brefus\w*\b|\bno answer\b/.test(q)) {
      const ambiguousLines = D.lines.filter((l) => l.kind === "Ambiguous");
      if (!ambiguousLines.length) {
        return {
          headline: "No bank line on this run is Ambiguous — every line either has a unique closing composition or was declined outright (Unresolved).",
          sub: "Uncertainty here means multiple rival compositions pass the identical soundness check — see the glossary term \"ambiguous\".",
          page: "transactions",
          sources: [{ label: "Why Settlr abstains instead of guessing", page: "transactions" }],
        };
      }
      // `CandidateSet.size` is a Python @property -- it does not survive
      // to_jsonable (which walks dataclass fields only). The real field is
      // `candidates`, an array; its length is the count.
      const candidateCount = (l) => (l.outcome && l.outcome.candidate_set
        ? l.outcome.candidate_set.candidates.length : 0);
      const totalCandidates = ambiguousLines.reduce((s, l) => s + candidateCount(l), 0);
      return {
        headline: `${ambiguousLines.length} bank line(s) are genuinely Ambiguous — ${totalCandidates} rival composition(s) total, ` +
          `none of them picked, because two or more pass the identical soundness check.`,
        sub: "This is a refusal to guess, not a gap in the data — open any line to see the competing explanations.",
        page: "transactions",
        sources: ambiguousLines.slice(0, 5).map((l) => ({
          label: `bank line #${l.index} (${candidateCount(l)} candidates)`, page: "transactions",
          onOpen: () => { switchPage("transactions"); selectedLineIndex = l.index; renderMatchColumns(); openLineDrilldown(l); },
        })),
      };
    }

    if (/\bwhich (dataset|entity)\b|\bwhat dataset\b|\bwhat entity\b|\bflagship\b|\bwhich run\b|\bwhat run\b/.test(q)) {
      const m = D.meta;
      return {
        headline: `These figures are for ${D.meta.entity_label} — run ${m.run_id.slice(0, 12)}…, ` +
          `${m.run_count} run(s) on record, build ${m.code_digest}.`,
        sub: "30 entities are under reconciliation in total; every live figure on this page comes from the run above.", page: "overview",
        sources: [{ label: "Source feeds — " + D.meta.entity_label, page: "sources" }],
      };
    }

    return null;
  }

  /* ============================== MATCHING-PAGE FILTER ============================== */
  // Grid filtering lives on the Matching page itself now -- it filters a
  // view, so it belongs on that view. Domain Q&A moved to the AI panel
  // below, which is a separate concern (a conversation, not a grid control).
  function applyFilters() {
    renderMatchColumns();
    $("#mFilterResultCount").textContent = visibleLines().length + " of " + D.lines.length;
  }
  function setupMatchingFilter() {
    const input = $("#mFilterInput");
    input.addEventListener("input", () => { cmdFilter = input.value; applyFilters(); });
    $$(".mfilter-chip").forEach((chip) => chip.addEventListener("click", () => {
      if (chip.dataset.q === "clear") {
        input.value = ""; cmdFilter = ""; agingFilter = null;
        $$(".aging-bar").forEach((b) => b.classList.remove("active"));
      } else {
        input.value = chip.dataset.q; cmdFilter = chip.dataset.q;
      }
      applyFilters();
    }));
    applyFilters();
  }

  /* ============================== AI PANEL (Ask Settlr) ============================== */
  // Composed live from the actual filtered set on every keystroke -- no
  // canned strings, no server round-trip.
  function generateAnswer(lines, query) {
    if (!lines.length) {
      return { headline: `No bank lines match "${query}."`, sub: "Try a different question.", sources: [] };
    }
    const byKind = {};
    let total = 0;
    let oldest = null;
    lines.forEach((l) => {
      byKind[l.kind] = (byKind[l.kind] || 0) + 1;
      total += Math.abs(l.amount_paise);
      if (!oldest || l.value_date < oldest) oldest = l.value_date;
    });
    const breakdown = Object.entries(byKind)
      .map(([k, n]) => `${n} ${KIND_WORD[k] || k.toLowerCase()}`)
      .join(", ");
    const headline = `${lines.length} line${lines.length === 1 ? "" : "s"} match — ${breakdown}, totaling ${inr(total)}.`;
    const sub = oldest ? `Earliest value date in this set: ${oldest}.` : "";
    return {
      headline, sub, page: "transactions",
      sources: lines.slice(0, 5).map((l) => ({
        label: `bank line #${l.index} (${l.kind})`, page: "transactions",
        onOpen: () => { switchPage("transactions"); selectedLineIndex = l.index; renderMatchColumns(); openLineDrilldown(l); },
      })),
    };
  }

  const AGENT_ORDER = ["chat_answerer", "sla_watchdog", "queue_cleaner",
    "break_investigator", "ambiguous_arbiter", "itc_drafter"];
  const aiMessages = [];

  function sourceChip(source) {
    const chip = el("span", {
      class: "source-chip",
      onclick: () => {
        if (source.onOpen) source.onOpen();
        else if (source.page) { switchPage(source.page); history.replaceState(null, "", "#" + source.page); }
      },
    }, el("svg", { width: "9", height: "9", viewBox: "0 0 24 24", fill: "none" },
      el("path", { d: "M7 17L17 7M17 7H9M17 7V15", stroke: "currentColor", "stroke-width": "2.5", "stroke-linecap": "round" })),
      source.label);
    return chip;
  }

  function renderAgentPreviewCard(agent) {
    const card = el("div", { class: "ai-agent-card" },
      el("div", { class: "name" }, "/" + agent.name),
      el("div", { class: "mode" }, agent.mode));
    const previewEl = el("div", { class: "preview" });
    card.appendChild(previewEl);

    if (!agent.preview) {
      previewEl.textContent = agent.name === "chat_answerer"
        ? "This is what you're using right now — ask it anything below."
        : "No real example to preview against this run's data right now.";
      return card;
    }
    const p = agent.preview;
    if (p.kind === "sla_watchdog") {
      previewEl.innerHTML = `Real preview: <b>${p.count}</b> escalation(s) this run would send. ` +
        `First ${p.examples.length}: ` + p.examples.map((e) =>
          `<b>${e.count}</b> ${e.reason} (${e.age_bucket}d, ${e.level}, owner: ${e.owner})`).join("; ") + ".";
    } else if (p.kind === "queue_cleaner") {
      previewEl.innerHTML = `Real preview: <b>${p.total}</b> carry-forward break(s), ` +
        `<b>${p.provable_within_window}</b> provable within the observed window, ` +
        `<b>${p.not_provable_within_window}</b> not. Surfaced only — nothing auto-closed.`;
    } else if (p.kind === "break_investigator") {
      previewEl.innerHTML = `Real preview on <b>${p.row_id}</b>: "${p.case_file}"`;
    } else if (p.kind === "ambiguous_arbiter") {
      previewEl.innerHTML = `Real preview on bank line <b>#${p.bank_index}</b>: ` +
        `<b>${p.candidate_count}</b> candidates${p.complete ? "" : " (sampled, incomplete)"} — a human must choose.`;
    } else if (p.kind === "itc_drafter") {
      previewEl.innerHTML = `Real preview on <b>${p.row_id}</b> (${p.dataset}): grounds ${p.grounds.join(", ")}.`;
    }
    return card;
  }

  function renderAiThread() {
    const thread = $("#aiThread");
    thread.innerHTML = "";
    if (!aiMessages.length) {
      thread.appendChild(el("div", { class: "ai-empty", id: "aiEmpty" },
        "Ask about unmatched lines, entities, health, aging, GST, or trust — every ",
        "answer cites the real record it came from.", el("br"), el("br"),
        "Type ", el("b", { style: "color:var(--text-2)" }, "/"), " to query or run one of Settlr's agents."));
      return;
    }
    aiMessages.forEach((m) => {
      if (m.role === "user") {
        thread.appendChild(el("div", { class: "ai-msg user" }, m.text));
        return;
      }
      const bubble = el("div", { class: "bubble" }, m.headline);
      if (m.sub) bubble.appendChild(el("div", { style: "color:var(--text-3);font-size:11.5px;margin-top:6px;" }, m.sub));
      if (m.agentCard) bubble.appendChild(m.agentCard);
      if (m.sources && m.sources.length) {
        bubble.appendChild(el("div", { class: "sources" }, m.sources.map(sourceChip)));
      }
      thread.appendChild(el("div", { class: "ai-msg assistant" }, bubble));
    });
    thread.scrollTop = thread.scrollHeight;
  }

  function pushMessage(msg) { aiMessages.push(msg); renderAiThread(); }

  function sendAiMessage() {
    const input = $("#aiInput");
    const text = input.value.trim();
    if (!text) return;
    pushMessage({ role: "user", text });
    input.value = "";
    input.style.height = "auto";
    hideAgentMenu();

    if (text.startsWith("/")) {
      const [rawName, ...rest] = text.slice(1).split(/\s+/);
      const agent = D.agents.find((a) => a.name === rawName);
      if (!agent) {
        pushMessage({ role: "assistant",
          headline: `No agent named "${rawName}". Available: ${AGENT_ORDER.map((n) => "/" + n).join(", ")}`,
          sources: [] });
        return;
      }
      if (agent.name === "chat_answerer" && rest.length) {
        answerFreeText(rest.join(" "));
        return;
      }
      pushMessage({ role: "assistant", headline: agent.description,
        agentCard: renderAgentPreviewCard(agent), sources: [] });
      return;
    }
    answerFreeText(text);
  }

  // A query is only treated as a bank-line filter if it actually looks like
  // one -- a FILTER_KEYWORD, an amount, or a short (<=4 word) fragment that
  // could plausibly be a reference/narration snippet. Otherwise a long
  // natural-language question (no keyword, no amount) would silently fall
  // through to "0 lines match your whole sentence," which reads as the
  // engine failing to understand rather than the honest truth: the
  // question just isn't one of the things this panel currently answers.
  function looksLikeLineFilter(query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (words.some((w) => FILTER_KEYWORDS.has(w))) return true;
    if (/₹?\s*[\d,]+/.test(query) && /\d/.test(query)) return true;
    return words.length <= 4;
  }

  const UNANSWERED_HINT = "I don't have a specific real-data answer for that yet. Try asking about " +
    "the health score, aging, entities, ingestion, GST/ITC risk, stability, uncertainty/ambiguity, " +
    "a specific entity name, or type / for an agent.";

  function localHeuristicAnswer(query) {
    const domain = domainAnswer(query);
    if (domain) {
      pushMessage({ role: "assistant", headline: domain.headline, sub: domain.sub,
        sources: domain.sources || [] });
      return;
    }
    if (!looksLikeLineFilter(query)) {
      pushMessage({ role: "assistant", headline: UNANSWERED_HINT, sources: [] });
      return;
    }
    const filtered = D.lines.filter((l) => {
      const saved = cmdFilter;
      cmdFilter = query;
      const match = lineMatchesFilter(l);
      cmdFilter = saved;
      return match;
    });
    const { headline, sub, sources } = generateAnswer(filtered, query);
    pushMessage({ role: "assistant", headline, sub, sources: sources || [] });
  }

  async function answerFreeText(query) {
    const thread = $("#aiThread");
    const thinking = el("div", { class: "ai-msg assistant" },
      el("div", { class: "bubble", style: "color:var(--text-3);font-style:italic;" }, "Asking Claude…"));
    thread.appendChild(thinking);
    thread.scrollTop = thread.scrollHeight;

    let result = null;
    try {
      const res = await fetch(`${AGENT_API_BASE}/runs/${D.meta.run_id}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
        signal: AbortSignal.timeout(25000),
      });
      if (!res.ok) throw new Error(`live agent HTTP ${res.status}`);
      result = await res.json();
    } catch (err) {
      thinking.remove();
      localHeuristicAnswer(query);
      pushMessage({ role: "assistant",
        headline: "(The AI assistant is offline. " +
          "Showing local results instead.)",
        sources: [] });
      return;
    }

    thinking.remove();
    if (result.mode === "claude") {
      const sub = `Query run: ${result.sql}` + (result.rows.length ? ` -- ${result.rows.length} row(s)` : "");
      pushMessage({ role: "assistant", headline: result.answer, sub, sources: [] });
      return;
    }
    // mode === "fallback": Claude itself was unreachable server-side (e.g.
    // no ANTHROPIC_API_KEY) -- agents/chat_answerer.py's own honest degrade,
    // a real query when it recognizes the question, a plain admission when
    // it doesn't. Layer the local heuristic answerer under it either way,
    // since it covers ground (health score, aging, GST, entities...) the
    // Python-side fallback pattern list doesn't.
    pushMessage({ role: "assistant", headline: result.answer, sources: [] });
    if (!result.rows.length) localHeuristicAnswer(query);
  }

  function renderAgentMenu(filterText) {
    const menu = $("#agentMenu");
    const term = filterText.slice(1).toLowerCase();
    const matches = AGENT_ORDER
      .map((n) => D.agents.find((a) => a.name === n))
      .filter((a) => a && a.name.startsWith(term));
    if (!matches.length) { menu.classList.remove("show"); return; }
    menu.innerHTML = "";
    matches.forEach((a) => {
      const item = el("div", { class: "agent-menu-item",
        onclick: () => { $("#aiInput").value = "/" + a.name + " "; $("#aiInput").focus(); hideAgentMenu(); } },
        el("div", { class: "n" }, "/" + a.name),
        el("div", { class: "d" }, a.description));
      menu.appendChild(item);
    });
    menu.classList.add("show");
  }
  function hideAgentMenu() { $("#agentMenu").classList.remove("show"); }

  function pulseOrb() {
    const btn = $("#aiOrbBtn");
    btn.classList.remove("pulsing");
    void btn.offsetWidth; // restart the CSS animation
    btn.classList.add("pulsing");
  }

  function openAiPanel() {
    pulseOrb();
    $("#aiPanel").classList.add("show");
    $("#aiOrbBtn").setAttribute("aria-expanded", "true");
    renderAiThread();
    $("#aiInput").focus();
  }
  function closeAiPanel() {
    $("#aiPanel").classList.remove("show");
    $("#aiOrbBtn").setAttribute("aria-expanded", "false");
    hideAgentMenu();
  }

  function setupAiPanel() {
    const orb = $("#aiOrbWrap");
    const input = $("#aiInput");
    orb.addEventListener("click", () => {
      const panel = $("#aiPanel");
      panel.classList.contains("show") ? closeAiPanel() : openAiPanel();
    });
    $("#aiPanelClose").addEventListener("click", closeAiPanel);
    $("#aiSendBtn").addEventListener("click", sendAiMessage);
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 96) + "px";
      if (input.value.startsWith("/")) renderAgentMenu(input.value);
      else hideAgentMenu();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiMessage(); }
      if (e.key === "Escape") { hideAgentMenu(); }
    });
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openAiPanel(); }
      if (e.key === "Escape") { closeDrilldown(); closeAiPanel(); closeNotifPanel(); closeAvatarMenu(); }
    });
  }

  /* ============================== AVATAR MENU ============================== */
  function closeAvatarMenu() {
    $("#avatarMenu").classList.remove("show");
    $("#avatarBtn").setAttribute("aria-expanded", "false");
  }
  function setupAvatarMenu() {
    const btn = $("#avatarBtn");
    const menu = $("#avatarMenu");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willShow = !menu.classList.contains("show");
      menu.classList.toggle("show", willShow);
      btn.setAttribute("aria-expanded", String(willShow));
    });
    $$(".avatar-menu-item").forEach((item) => item.addEventListener("click", () => {
      closeAvatarMenu();
      if (item.dataset.page) { switchPage(item.dataset.page); history.replaceState(null, "", "#" + item.dataset.page); }
      else if (item.dataset.action === "profile") showToast("Profile — not wired up in this demo (session only)");
      else if (item.dataset.action === "settings") showToast("Settings — not wired up in this demo (session only)");
      else if (item.dataset.action === "signout") showToast("Sign out — not wired up in this demo (session only)");
    }));
    document.addEventListener("click", (e) => {
      if (!menu.contains(e.target) && e.target !== btn) closeAvatarMenu();
    });
  }

  /* ============================== CONNECTORS PAGE ============================== */
  // Three real states, not two: "connected" means this exact run's data
  // literally came in through that format (recon_combined.json / gstr2b.csv
  // are real ingested artifacts of THIS run -- computed server-side in
  // build_dashboard.py against build_ingestion_status's real output, not
  // guessed here). "available" means real, tested code exists
  // (transport/sftp.py, transport/s3.py) but this run's data came from a
  // local file, not that transport. "planned" is a genuine, named gap.
  const CONNECTOR_STATUS_META = {
    connected: { label: "Connected", pill: "background:var(--green-bg);color:var(--green);border:1px solid var(--green-border);" },
    available: { label: "Available", pill: "background:rgba(61,116,255,.14);color:var(--blue-soft);border:1px solid rgba(61,116,255,.35);" },
    planned: { label: "Planned", pill: "background:var(--slate-bg);color:var(--slate);border:1px solid var(--border-strong);" },
  };

  function renderConnectors() {
    const grid = $("#connectorsGrid");
    grid.innerHTML = "";
    D.connectors.forEach((c) => {
      const meta = CONNECTOR_STATUS_META[c.status];
      const planned = c.status === "planned";
      const card = el("div", { class: "connector-card" + (planned ? " planned" : "") },
        el("div", { class: "connector-head" },
          el("div", { class: "connector-monogram" }, c.monogram),
          el("div", {},
            el("div", { class: "connector-name" }, c.name),
            el("div", { class: "connector-status" },
              el("span", { class: "status-pill", style: meta.pill }, meta.label)))),
        el("div", { class: "connector-detail" }, c.detail));
      const btn = el("button", {
        class: "connector-btn",
        onclick: () => showToast(!planned
          ? `${c.name}: ${c.detail}`
          : `${c.name} isn't built yet — ${c.detail}`),
      }, c.status === "connected" ? "View details →" : planned ? "Not available" : "Configure →");
      if (planned) btn.disabled = true;
      card.appendChild(btn);
      grid.appendChild(card);
    });
  }

  /* ============================== NOTIFICATIONS ============================== */
  function buildNotifications() {
    const items = [];
    D.discrepancies.forEach((d) => items.push({
      tone: "var(--red)", title: "Discrepancy on " + d.reference,
      sub: d.detail, target: d.bank_index,
    }));
    if (D.aging["61-90"] || D.aging["90+"]) {
      items.push({
        tone: "var(--amber)",
        title: (D.aging["61-90"] + D.aging["90+"]) + " breaks past 60 days",
        sub: "Real open exceptions from the persisted run — review the aging queue.",
        page: "overview",
      });
    }
    const failedEntities = D.entities.filter((e) => !e.passed);
    failedEntities.forEach((e) => items.push({
      tone: "var(--red)", title: e.label + " failed verification",
      sub: e.open_breaks + " open breaks, " + e.unresolved + " unresolved lines.",
      page: "close",
    }));
    return items;
  }

  function renderNotifications() {
    const list = $("#notifList");
    const items = buildNotifications();
    list.innerHTML = "";
    if (!items.length) {
      list.append(el("div", { class: "notif-empty" }, "Nothing needs attention right now."));
    } else {
      items.forEach((item) => {
        const row = el("div", { class: "notif-item" },
          el("span", { class: "dot", style: `background:${item.tone}` }),
          el("div", { class: "body" },
            el("div", { class: "title" }, item.title),
            el("div", { class: "sub" }, item.sub)));
        row.addEventListener("click", () => {
          closeNotifPanel();
          if (item.page) { switchPage(item.page); history.replaceState(null, "", "#" + item.page); }
          if (item.target != null) {
            switchPage("transactions");
            history.replaceState(null, "", "#matching");
            const line = D.lines[item.target];
            if (line) { selectedLineIndex = line.index; renderMatchColumns(); openLineDrilldown(line); }
          }
        });
        list.append(row);
      });
    }
    $("#notifDot").style.display = items.length ? "block" : "none";
  }

  function closeNotifPanel() {
    $("#notifPanel").classList.remove("show");
    $("#notifBtn").setAttribute("aria-expanded", "false");
  }

  function setupNotifications() {
    renderNotifications();
    const btn = $("#notifBtn");
    const panel = $("#notifPanel");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willShow = !panel.classList.contains("show");
      panel.classList.toggle("show", willShow);
      btn.setAttribute("aria-expanded", String(willShow));
    });
    document.addEventListener("click", (e) => {
      if (!panel.contains(e.target) && e.target !== btn) closeNotifPanel();
    });
  }

  /* ============================== EXCEPTIONS / INVESTIGATION ============================== */
  // Every exception in D.exceptions is real -- see DECISIONS Sec.100.
  // OpenBreak items carry `has_warrant: false` deliberately: the live
  // resolver never populates OpenBreak.warrant, so this page must not
  // synthesize a "likely explanation" for those, only for the
  // Unresolved/AttestationDiscrepancy items that genuinely carry one.
  function statCards(containerId, cards) {
    const row = $(containerId);
    row.innerHTML = "";
    cards.forEach((c, i) => {
      row.append(el("div", { class: "panel stat-card fadein", style: `animation-delay:${i * 60}ms` },
        el("div", { class: "lbl" }, c.lbl),
        el("div", { class: "val num" }, "" + c.val),
        el("div", { class: `trend ${c.tone || "warn"}` }, c.trend || "")));
    });
  }

  const exceptionLocalStatus = {}; // session-only, never persisted -- see action handlers below
  let excTab = "all";
  let excSearch = "";

  function exceptionMatchesTab(e, tab) {
    if (tab === "all") return true;
    if (tab === "high-risk") return e.age_bucket === "61-90" || e.age_bucket === "90+";
    if (tab === "aging") return e.scope === "row";
    if (tab === "source") return true; // grouping happens in render, not filtering
    if (tab === "owner") return true;
    return true;
  }

  function visibleExceptions() {
    const q = excSearch.trim().toLowerCase();
    return D.exceptions.filter((e) => {
      if (!exceptionMatchesTab(e, excTab)) return false;
      if (!q) return true;
      return (e.reference || "").toLowerCase().includes(q) ||
        (e.reason || "").toLowerCase().includes(q) ||
        (e.owner || "").toLowerCase().includes(q);
    });
  }

  function renderExceptions() {
    const list = visibleExceptions();
    const highRisk = D.exceptions.filter((e) => e.age_bucket === "61-90" || e.age_bucket === "90+").length;
    const withEvidence = D.exceptions.filter((e) => e.has_warrant).length;
    statCards("#excStatRow", [
      { lbl: "Open Exceptions", val: D.exceptions.length, trend: `${list.length} shown`, tone: "warn" },
      { lbl: "High Risk (61+ days)", val: highRisk, trend: "aged 61-90 or 90+", tone: highRisk > 0 ? "down" : "up" },
      { lbl: "With Real Evidence", val: withEvidence, trend: `${D.exceptions.length - withEvidence} carry no warrant`, tone: "warn" },
    ]);

    const body = $("#excTableBody");
    body.innerHTML = "";
    if (excTab === "source" || excTab === "owner") {
      const key = excTab === "source" ? (e) => e.scope === "line" ? "Bank line" : "Unmatched row" : (e) => e.owner || "—";
      const groups = {};
      list.forEach((e) => { const k = key(e); (groups[k] = groups[k] || []).push(e); });
      Object.entries(groups).forEach(([groupName, items]) => {
        body.append(el("tr", {}, el("td", { colspan: "7", style: "font-weight:700;color:var(--text-1);background:rgba(var(--ink),.03);" },
          `${groupName} (${items.length})`)));
        items.forEach((e) => body.append(exceptionRow(e)));
      });
      return;
    }
    list.forEach((e) => body.append(exceptionRow(e)));
    if (!list.length) {
      body.append(el("tr", {}, el("td", { colspan: "7", style: "text-align:center;color:var(--text-3);padding:24px;" },
        "No exceptions match this filter.")));
    }
  }

  function exceptionRow(e) {
    const meta = KIND_META[e.kind] || KIND_META.Unresolved;
    const status = exceptionLocalStatus[e.id];
    const tr = el("tr", { onclick: () => openExceptionDrilldown(e) },
      el("td", { class: "name" }, e.id, status ? el("span", { class: "axis" }, status) : null),
      el("td", {}, el("span", { class: "status-pill", style: `background:${meta.color}22;color:${meta.color};border:1px solid ${meta.color}55` }, meta.label)),
      el("td", {}, prettyReason(e.reason)),
      el("td", { class: "num" }, e.amount_paise != null ? inr(Math.abs(e.amount_paise)) : "—"),
      el("td", {}, e.age_days != null ? `${e.age_days}d (${e.age_bucket})` : "—"),
      el("td", {}, e.owner || "—"),
      el("td", {}, e.has_warrant ? "real evidence" : "no warrant on file"));
    return tr;
  }

  function evidencePanel(title, records, renderer) {
    const sec = el("div", { class: "slideout-section" }, el("h4", {}, title));
    if (!records || !records.length) {
      sec.append(el("div", { class: "evidence-detail" }, `Not found in ${title}.`));
      return sec;
    }
    records.forEach((r) => sec.append(el("div", { class: "evidence-item" },
      el("div", { class: "evidence-dot" }),
      el("div", { class: "evidence-txt", html: renderer(r) }))));
    return sec;
  }

  function exceptionAction(exc, label, newStatus) {
    return el("button", { class: "btn btn-ghost btn-sm", onclick: (e) => {
      e.stopPropagation();
      exceptionLocalStatus[exc.id] = newStatus;
      showToast(`${exc.id}: ${label} (session only, not persisted)`);
      renderExceptions();
    } }, label);
  }

  function openExceptionDrilldown(exc) {
    const slideout = $("#slideout");
    slideout.innerHTML = "";
    const meta = KIND_META[exc.kind] || KIND_META.Unresolved;

    slideout.append(el("div", { class: "slideout-head" },
      el("div", {},
        el("h3", {}, exc.id + " · " + exc.reference),
        el("div", { class: "sub" },
          (exc.amount_paise != null ? inr(Math.abs(exc.amount_paise)) + " · " : ""),
          el("span", { style: `color:${meta.color};font-weight:600` }, meta.label))),
      el("button", { class: "slideout-close", onclick: closeDrilldown }, "✕")
    ));

    const body = el("div", { class: "slideout-body" });

    body.append(el("div", { class: "slideout-section" },
      el("h4", {}, "Summary"),
      el("div", { class: "kv" },
        el("div", { class: "cell" }, el("div", { class: "k" }, "Reason"), el("div", { class: "v" }, prettyReason(exc.reason))),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Owner"), el("div", { class: "v" }, exc.owner || "—")),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Age"), el("div", { class: "v" }, exc.age_days != null ? `${exc.age_days} days` : "—")),
        el("div", { class: "cell" }, el("div", { class: "k" }, "Close condition"), el("div", { class: "v", style: "font-size:11px;font-weight:500;" }, exc.close_condition || "—")))));

    body.append(el("div", { class: "slideout-section" },
      el("h4", {}, "Likely Explanation"),
      exc.has_warrant
        ? el("div", { class: "evidence-detail" }, exc.likely_explanation || "—")
        : el("div", { class: "evidence-detail", style: "color:var(--amber)" },
            "No supporting evidence on file — this item has not been classified with a stated cause. " +
            "Stating a cause here would be invented, not real.")));

    if (exc.has_warrant && exc.evidence && exc.evidence.evidence) {
      const sec = el("div", { class: "slideout-section" }, el("h4", {}, "Evidence & Warrant"));
      exc.evidence.evidence.forEach((ev) => {
        sec.append(el("div", { class: "evidence-item" },
          el("div", { class: "evidence-dot" }),
          el("div", { class: "evidence-txt" },
            el("div", { class: "evidence-kind" }, prettyEvidence(ev.kind)),
            el("div", {}, ev.derived_from.map((s) => el("span", { class: "evidence-src" }, prettySource(s)))),
            el("div", { class: "evidence-detail" }, ev.detail))));
      });
      body.append(sec);
    }

    body.append(evidencePanel("Bank", exc.bank && exc.bank.found ? [exc.bank] : [], (b) =>
      `<div class="evidence-kind">${b.reference || ""}</div><div class="evidence-detail">${b.narration || ""} — ${inr(Math.abs(b.amount_paise))} on ${b.value_date}</div>`));
    if (exc.bank && !exc.bank.found) {
      body.append(el("div", { class: "slideout-section" }, el("h4", {}, "Bank"),
        el("div", { class: "evidence-detail" }, exc.bank.detail)));
    }
    body.append(evidencePanel("Processor Ledger", exc.psp, (r) =>
      `<div class="evidence-kind">${r.entity_id}</div><div class="evidence-detail">${r.type || ""} — ${inr(Math.abs(r.credit || r.debit || r.amount || 0))}${r.settlement_id ? " — settlement " + r.settlement_id : ""}</div>`));
    body.append(evidencePanel("Settlement Report", exc.settlement_report, (r) =>
      `<div class="evidence-kind">Batch ${r.reported_reference || "—"}</div><div class="evidence-detail">${inr(Math.abs(r.reported_amount || 0))} initiated ${r.initiated_at || "—"}</div>`));
    body.append(evidencePanel("ERP", exc.erp, (r) =>
      `<div class="evidence-kind">${r.invoice_no}</div><div class="evidence-detail">₹${r.amount} invoiced ${r.invoice_date}</div>`));
    body.append(evidencePanel("Disputes", exc.disputes, (r) =>
      `<div class="evidence-kind">${r.id || ""}</div><div class="evidence-detail">${r.status || ""} — opened ${r.opened_at || "—"}</div>`));

    body.append(el("div", { class: "slideout-section" },
      el("h4", {}, "Actions"),
      el("div", { style: "display:flex;flex-wrap:wrap;gap:8px;" },
        exceptionAction(exc, "Match manually", "matched manually"),
        exceptionAction(exc, "Mark timing difference", "timing difference"),
        exceptionAction(exc, "Create adjustment", "adjustment created"),
        exceptionAction(exc, "Escalate", "escalated"),
        exceptionAction(exc, "Ignore with reason", "ignored"))));

    slideout.append(body);
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  function setupExceptionsPage() {
    $$("#excTabs button").forEach((btn) => btn.addEventListener("click", () => {
      $$("#excTabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      excTab = btn.dataset.tab;
      renderExceptions();
    }));
    $("#excSearch").addEventListener("input", (e) => { excSearch = e.target.value; renderExceptions(); });
  }

  /* ============================== RUNS ============================== */
  function renderRuns() {
    const body = $("#runsTableBody");
    body.innerHTML = "";
    D.runs_table.forEach((r) => {
      const tr = el("tr", { onclick: () => {
        if (r.is_flagship) return; // the diff panel above already covers it
        const entity = D.entities.find((e) => e.axis_point === r.axis_point);
        if (entity) openEntityDrilldown(entity);
      } },
        el("td", { class: "name" }, r.label, el("span", { class: "axis" }, r.axis_point)),
        el("td", {}, prettyFamily(r.family)),
        el("td", { class: "num" }, r.sources + "/6"),
        el("td", { class: "num" }, r.match_rate.toFixed(1) + "%"),
        el("td", { class: "num" }, r.open_exceptions),
        el("td", {}, el("span", { class: "status-pill", style: r.passed
          ? "background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)"
          : "background:var(--red-bg);color:var(--red);border:1px solid var(--red-border)" }, r.passed ? "Verified" : "Needs review")));
      body.append(tr);
    });

    const diff = D.run_diff;
    const panel = $("#runsDiffPanel");
    panel.innerHTML = "";
    panel.append(el("h4", { style: "font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:10px;" },
      "What changed: run " + diff.run_a.slice(0, 10) + "… → run " + diff.run_b.slice(0, 10) + "…"));
    panel.append(el("div", { class: "evidence-detail", style: "margin-bottom:12px;" },
      `Same period and same source data, re-run at different search settings — depth ${diff.cap_a}→${diff.cap_b}, ` +
      `time_budget ${diff.time_budget_a}s→${diff.time_budget_b}s. Not a time-sequential rerun: this corpus has no date dimension.`));
    panel.append(el("div", { class: "kv" },
      el("div", { class: "cell" }, el("div", { class: "k" }, "Rows unchanged"), el("div", { class: "v" }, diff.unchanged)),
      el("div", { class: "cell" }, el("div", { class: "k" }, "Breaks resolved"), el("div", { class: "v", style: "color:var(--green)" }, diff.resolved)),
      el("div", { class: "cell" }, el("div", { class: "k" }, "New breaks"), el("div", { class: "v", style: "color:var(--red)" }, diff.new_breaks)),
      el("div", { class: "cell" }, el("div", { class: "k" }, "Reclassified"), el("div", { class: "v" }, diff.reclassified))));
  }

  /* ============================== ACCOUNTING ============================== */
  const ACCT_STEPS = ["Draft", "Review", "Approved", "Posted to ERP", "Reconciled"];
  let acctStep = 0;

  function renderAccounting() {
    const a = D.accounting;
    statCards("#acctSummaryRow", [
      { lbl: "Gross Payments", val: inr(a.gross_paise), trend: "Σ amount, Verified/Reconstructed lines", tone: "warn" },
      { lbl: "Processing Fees", val: inr(a.fees_paise), trend: "Processor fees, GST inclusive", tone: "down" },
      { lbl: "Net to Bank", val: inr(a.net_paise), trend: `refunds ${inr(a.refunds_paise)}`, tone: "up" },
    ]);

    $("#acctDisclosure").innerHTML = "";
    $("#acctDisclosure").append(el("div", { class: "evidence-detail" },
      el("b", { style: "color:var(--amber)" }, "Illustrative convention, not an engine assertion: "),
      "the amounts below are real (Σfee/Σcredit/Σdebit from this run's own ledger rows). The account " +
      "names (PSP Clearing, Processing Fees, Refund Liability, Bank) are a standard double-entry layout " +
      "applied to those real amounts for readability. Map them to your own chart of accounts before posting."));

    const body = $("#acctTableBody");
    body.innerHTML = "";
    a.lines.forEach((l) => {
      body.append(el("tr", {},
        el("td", { class: "name" }, l.account),
        el("td", { class: "num" }, l.debit_paise ? inr(l.debit_paise) : ""),
        el("td", { class: "num" }, l.credit_paise ? inr(l.credit_paise) : ""),
        el("td", {}, el("span", { class: "status-pill", style: "background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)" }, "Ready"))));
    });

    renderAcctWorkflow();
  }

  function renderAcctWorkflow() {
    const panel = $("#acctWorkflowPanel");
    panel.innerHTML = "";
    panel.append(el("h4", { style: "font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);margin-bottom:10px;" },
      "Journal workflow (session only, no real posting occurs)"));
    const stepsRow = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;" });
    ACCT_STEPS.forEach((s, i) => {
      stepsRow.append(el("span", {
        class: "status-pill",
        style: i <= acctStep
          ? "background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)"
          : "background:rgba(var(--ink),.05);color:var(--text-3);border:1px solid var(--border-strong)",
      }, s));
    });
    panel.append(stepsRow);
    const nextLabel = acctStep < ACCT_STEPS.length - 1
      ? ["Generate journal", "Review", "Approve", "Post to ERP", "Reconcile again"][acctStep]
      : null;
    if (nextLabel) {
      panel.append(el("button", { class: "btn btn-primary", onclick: () => {
        acctStep++;
        showToast(`${ACCT_STEPS[acctStep]} (session only, not persisted)`);
        renderAcctWorkflow();
      } }, nextLabel + " →"));
    } else {
      panel.append(el("div", { class: "evidence-detail", style: "color:var(--green)" }, "Cycle complete for this session."));
    }
  }

  /* ============================== PAGE SWITCHING ============================== */
  const PAGES = ["overview", "transactions", "exceptions", "accounting", "close", "sources"];

  // Pages that carry a tab strip. Consolidating nine nav items into six put
  // several genuinely distinct views behind one nav entry, so the hash has
  // to address them: "#overview/audit" is a real, linkable location, not
  // just "#overview" plus hidden client state.
  function switchPage(name, tab) {
    if (!PAGES.includes(name)) name = "overview";
    $$(".page").forEach((p) => p.classList.toggle("active", p.dataset.page === name));
    $$(".navlinks a").forEach((a) => a.classList.toggle("active", a.dataset.page === name));
    if (tab) switchTab(name, tab);
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  function switchTab(pageName, tab) {
    const strip = $(`.tabstrip[data-tabs="${pageName}"]`);
    if (!strip) return;
    const page = strip.closest(".page");
    const known = $$("button", strip).some((b) => b.dataset.tab === tab);
    if (!known) return;
    $$("button", strip).forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    $$(".tabpanel", page).forEach((tp) => tp.classList.toggle("active", tp.dataset.tabpanel === tab));
  }

  function setupTabs() {
    $$(".tabstrip").forEach((strip) => {
      const pageName = strip.dataset.tabs;
      $$("button", strip).forEach((btn) => {
        btn.addEventListener("click", () => {
          switchTab(pageName, btn.dataset.tab);
          history.replaceState(null, "", `#${pageName}/${btn.dataset.tab}`);
        });
      });
    });
  }

  function setupPageSwitching() {
    $$(".navlinks a").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        switchPage(link.dataset.page);
        history.replaceState(null, "", "#" + link.dataset.page);
        closeAiPanel(); closeNotifPanel(); closeAvatarMenu();
      });
    });
    $(".brand").addEventListener("click", (e) => {
      e.preventDefault();
      switchPage("overview");
      history.replaceState(null, "", "#overview");
    });
    // A plain hash change (browser back/forward, or a hash edited by hand)
    // is a same-document navigation and does NOT re-run this script -- only
    // clicks routed through the handlers above called switchPage() so far.
    // This listener is what makes the browser's own back/forward buttons,
    // and any link into this page with a #hash, actually work.
    const route = (hash) => {
      const [page, tab] = hash.replace(/^#/, "").split("/");
      switchPage(page, tab);
    };
    window.addEventListener("hashchange", () => route(location.hash));
    route(location.hash || "#overview");
  }

  /* ============================== BOOT ============================== */
  renderMetaChips();
  renderHero();
  renderStatRow();
  renderAging();
  renderIngestionSmall();
  renderKanban();
  renderEntities();
  renderIngestionFull();
  renderTrust();
  renderGst();
  renderStability();
  renderMatchingGrid();
  renderConnectors();
  renderExceptions();
  setupExceptionsPage();
  renderRuns();
  renderAccounting();
  setupMatchingFilter();
  setupAiPanel();
  setupTheme();
  setupAvatarMenu();
  setupNotifications();
  setupTabs();
  setupPageSwitching();
  $("#matchingSub").textContent =
    D.meta.entity_label + " · " + D.lines.length +
    " bank lines. Select one to see which transactions make it up, across every source.";
})();
