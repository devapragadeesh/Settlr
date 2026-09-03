(function () {
  "use strict";
  const D = window.SETTLR_DATA;
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
  const AGING_COLORS = { "0-30": "#2ecf7a", "31-60": "#f5c453", "61-90": "#f5a524", "90+": "#f0475a" };
  // Mirrors resolver_contract.types.SOURCE_PARTY -- independence is counted
  // over parties, not sources; resolver_internal never corroborates.
  const SOURCE_PARTY = {
    psp_ledger: "psp", psp_settlement_report: "psp", bank: "bank",
    merchant_erp: "merchant", tax_authority: "tax_authority",
    dispute_record: "issuer", resolver_internal: "resolver",
  };
  const KIND_META = {
    Verified: { label: "Verified", color: "var(--green)" },
    Reconstructed: { label: "Reconstructed", color: "var(--blue-1)" },
    AttestationDiscrepancy: { label: "Discrepancy", color: "var(--red)" },
    Ambiguous: { label: "Ambiguous", color: "var(--amber)" },
    Unresolved: { label: "Unresolved", color: "var(--slate)" },
  };

  /* ============================== META CHIPS ============================== */
  function renderMetaChips() {
    const wrap = $("#metaChips");
    const runShort = D.meta.run_id.slice(0, 10);
    wrap.append(
      el("div", { class: "meta-chip" }, el("span", { class: "pulse" }), "Live run ", el("b", {}, runShort)),
      el("div", { class: "meta-chip" }, "Flagship entity ", el("b", {}, D.meta.flagship_dataset)),
      el("div", { class: "meta-chip" }, D.meta.run_count + " persisted runs · code ", el("b", {}, D.meta.code_digest.slice(0, 8)))
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
        <stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="${color}"/>
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
        el("div", { html: donutSVG(h.on_determinable_pct, size, stroke, "#ffffff", "rgba(255,255,255,.16)") }),
        el("div", { class: "hero-donut-center" },
          el("div", { class: "pct num" }, h.on_determinable_pct.toFixed(1), el("sub", {}, "%")),
          el("div", { class: "lbl" }, "on determinable lines"))
      ),
      el("div", { class: "hero-legend" },
        el("div", { class: "item" }, el("span", { class: "sw", style: "background:#fff" }), "Answered ", el("b", {}, fmtNum(h.answered))),
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

  /* ============================== STAT CARDS ============================== */
  function renderStatRow() {
    const totalOpen = Object.values(D.aging).reduce((a, b) => a + b, 0);
    const cards = [
      { lbl: "Entities Tracked", val: D.entities.length, trend: `${D.entities.filter(e=>e.status==="in_progress").length} in progress`, tone: "warn" },
      { lbl: "Open Exceptions", val: fmtNum(totalOpen), trend: `${D.aging["90+"]} aged 90+ days`, tone: D.aging["90+"] > 0 ? "down" : "up" },
      { lbl: "Discrepancies Flagged", val: D.discrepancies.length, trend: "real, from the flagship run", tone: "warn" },
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
      $("#matching").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  /* ============================== INGESTION (compact) ============================== */
  const STATUS_DOT = { fresh: "var(--green)", stale: "var(--amber)" };

  function renderIngestionSmall() {
    const panel = $("#ingestionPanelSmall");
    panel.append(
      el("div", { class: "panel-head" },
        el("div", {}, el("h3", {}, "Pipeline Feed"),
          el("div", { class: "sub" }, "Last local ingest · flagship entity")),
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
        el("div", { class: "feed-sub", style: "margin-top:4px" }, f.source_system.replace(/_/g, " ")),
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
        const c = matchColumn("PSP Ledger", "var(--green)", ledgerRows.length);
        ledgerRows.forEach((r) => c.body.append(ledgerRowEl(r, line)));
        cols.append(c.root);
      }
      if (erpRows.length) {
        const c = matchColumn("ERP Order Book", "#c98bff", erpRows.length);
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
      c.body.append(el("div", { class: "empty-col" }, "Select a bank line to reveal its resolver-suggested composition."));
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
      el("div", { class: "chk" }, el("svg", { width: "10", height: "8", viewBox: "0 0 10 8", fill: "none", html: '<path d="M1 4l2.5 2.5L9 1" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' })),
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
      el("div", { class: "chk" }, el("svg", { width: "10", height: "8", viewBox: "0 0 10 8", fill: "none", html: '<path d="M1 4l2.5 2.5L9 1" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' })),
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
            el("div", { class: "evidence-kind" }, ev.kind.replace(/_/g, " ")),
            el("div", {}, ev.derived_from.map((s) => el("span", { class: "evidence-src" }, s.replace(/_/g, " ")))),
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
        el("div", { class: "evidence-detail", style: "color:#ff9aa5" }, o.contradiction.detail)));
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
            el("div", { class: "cell" }, el("div", { class: "k" }, "Oracle gate"), el("div", { class: "v", style: `color:${entity.passed ? "var(--green)" : "var(--red)"}` }, entity.passed ? "Passed" : "Failed"))))
      )
    );
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  // Reached from the health-score card's ↗ button. Every figure here is
  // read straight from dashboard/data.json (corpus/coverage.py's four
  // scopes, corpus/claims_ledger.py's full 25-row ledger) -- nothing
  // computed or curated client-side.
  function openHealthDetail() {
    const slideout = $("#slideout");
    slideout.innerHTML = "";
    slideout.append(
      el("div", { class: "slideout-head" },
        el("div", {}, el("h3", {}, "Detailed Health Analysis"),
          el("div", { class: "sub" }, "corpus/coverage.py and corpus/claims_ledger.py, in full — nothing curated")),
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

    const claimsSection = el("div", { class: "slideout-section" },
      el("h4", {}, D.claims.length + " Claims in the Ledger"));
    const claimsList = el("div", {});
    D.claims.forEach((c) => {
      claimsList.append(el("div", { class: "evidence-item" },
        el("div", { class: "evidence-dot", style: "background:var(--slate)" }),
        el("div", { class: "evidence-txt" },
          el("div", { class: "evidence-kind" }, c.claim),
          el("div", { class: "evidence-detail" },
            el("b", { style: "color:var(--text-1)" }, String(c.value)), " of ", c.denom, " — ", c.scope))));
    });
    claimsSection.append(claimsList);
    body.append(claimsSection);

    slideout.append(body);
    $("#scrim").classList.add("show");
    slideout.classList.add("show");
  }

  function closeDrilldown() {
    $("#slideout").classList.remove("show");
    $("#scrim").classList.remove("show");
  }
  $("#scrim").addEventListener("click", closeDrilldown);

  /* ============================== COMMAND BAR ============================== */
  const KIND_WORD = {
    Verified: "verified", Reconstructed: "reconstructed",
    AttestationDiscrepancy: "flagged as a discrepancy", Ambiguous: "ambiguous",
    Unresolved: "unresolved",
  };

  // Composed live from the actual filtered set on every keystroke -- no
  // canned strings, no server round-trip. This is what "real time, right
  // under the search bar" means here: a sentence built from D.lines, not a
  // scripted response.
  function generateAnswer(lines, query) {
    if (!query) {
      return {
        headline: "Ask about unmatched lines, entities, or amounts — Settlr answers from this run's real data.",
        sub: "",
      };
    }
    if (!lines.length) {
      return {
        headline: `No bank lines match “${query}.”`,
        sub: "Try one of the quick filters below, or clear the search.",
      };
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
    return { headline, sub };
  }

  function renderAnswer() {
    const lines = visibleLines();
    const { headline, sub } = generateAnswer(lines, cmdFilter.trim());
    const answerEl = $("#cmdAnswer");
    answerEl.textContent = headline;
    $("#cmdSub").textContent = sub;
  }

  function applyFilters() {
    renderMatchColumns();
    renderAnswer();
    $("#cmdResultCount").textContent = visibleLines().length + " of " + D.lines.length;
  }
  function setupCommandBar() {
    const input = $("#cmdInput");
    const hint = $("#cmdHint");
    const cmdbar = $(".cmdbar");
    const openHint = () => { renderAnswer(); hint.classList.add("show"); };
    const closeHint = () => hint.classList.remove("show");

    input.addEventListener("focus", openHint);
    input.addEventListener("input", () => { cmdFilter = input.value; applyFilters(); });
    $$(".chip", hint).forEach((chip) => chip.addEventListener("mousedown", (e) => {
      e.preventDefault();
      if (chip.dataset.q === "clear") { input.value = ""; cmdFilter = ""; agingFilter = null; $$(".aging-bar").forEach(b=>b.classList.remove("active")); }
      else { input.value = chip.dataset.q; cmdFilter = chip.dataset.q; }
      applyFilters();
    }));
    // Belt-and-braces: close on any click outside the command bar (covers nav
    // link clicks, section scrolls, and any case a plain blur doesn't fire in
    // time), not just on input blur.
    document.addEventListener("click", (e) => {
      if (!cmdbar.contains(e.target)) closeHint();
    });
    $$(".navlinks a").forEach((link) => link.addEventListener("click", closeHint));
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.focus(); openHint(); }
      if (e.key === "Escape") { closeDrilldown(); closeHint(); closeNotifPanel(); }
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
        scrollTo: "#aging-section",
      });
    }
    const failedEntities = D.entities.filter((e) => !e.passed);
    failedEntities.forEach((e) => items.push({
      tone: "var(--red)", title: e.label + " failed its oracle gate",
      sub: e.open_breaks + " open breaks, " + e.unresolved + " unresolved lines.",
      scrollTo: "#close",
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
          if (item.scrollTo) document.querySelector(item.scrollTo)?.scrollIntoView({ behavior: "smooth" });
          if (item.target != null) {
            document.querySelector("#matching")?.scrollIntoView({ behavior: "smooth" });
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

  /* ============================== BOOT ============================== */
  renderMetaChips();
  renderHero();
  renderStatRow();
  renderAging();
  renderIngestionSmall();
  renderKanban();
  renderIngestionFull();
  renderMatchingGrid();
  setupCommandBar();
  setupNotifications();
  $("#matchingSub").textContent =
    "Flagship entity " + D.meta.flagship_dataset + " · " + D.lines.length +
    " real bank lines. Select a line to reveal the resolver's actual suggested composition across live source columns.";
})();
