const C = { maroon: "#5A0E18", crimson: "#8E1B26", red: "#E23744", rose: "#D9636E", pink: "#F8E4E6", light: "#EBC1C6" };
let charts = {}, current = null;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (x, d = 2) => (x === null || x === undefined) ? "n/a" : Number(x).toFixed(d);
const pct = x => (x === null || x === undefined) ? "n/a" : (x * 100).toFixed(0) + "%";
const sc = x => x === null || x === undefined ? "s-na" : x >= 3.5 ? "s-hi" : x >= 2.9 ? "s-mid" : "s-lo";
const tonecls = t => t === null || t === undefined ? "" : t < -0.05 ? "neg" : t > 0.05 ? "pos" : "";

Chart.defaults.font.family = "Calibri, 'Segoe UI', Arial, sans-serif";
Chart.defaults.font.size = 13;
Chart.defaults.color = "#374151";

function chart(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart($(id), cfg); }

$("f").addEventListener("submit", async e => {
  e.preventDefault();
  const fd = Object.fromEntries(new FormData(e.target).entries());
  busy(true);
  const steps = ["Collecting news headlines…", "Reading community posts…", "Fetching share prices…", "Reading app-store reviews…", "Checking Instagram and X…", "Scoring RepTrak dimensions…", "Applying the toolkit…"];
  let k = 0; const t = setInterval(() => { $("ptext").textContent = steps[k++ % steps.length]; }, 2500);
  try {
    const r = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fd) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Request failed");
    render(j);
  } catch (err) { banner("Analysis failed: " + err.message, true); }
  finally { clearInterval(t); busy(false); }
});

$("demo").addEventListener("click", async () => {
  busy(true); $("ptext").textContent = "Loading saved Eternal demo…";
  try { const r = await fetch("/api/demo"); render(await r.json()); }
  catch (err) { banner("Could not load demo: " + err.message, true); }
  finally { busy(false); }
});

$("dl").addEventListener("click", () => {
  if (!current) return;
  const b = new Blob([JSON.stringify(current, null, 1)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(b);
  a.download = (current.company || "reptrak").replace(/\W+/g, "_") + "_reptrak.json"; a.click();
});

$("filter").addEventListener("input", () => current && renderItems(current.items, $("filter").value));

function busy(on) { $("progress").classList.toggle("hidden", !on); $("run").disabled = on; $("demo").disabled = on; }
function banner(msg, warn) { const b = $("banner"); b.innerHTML = msg; b.className = "banner" + (warn ? " warn" : ""); }

function render(d) {
  current = d;
  $("results").classList.remove("hidden");
  const notes = [];
  if (d.demo) notes.push("<b>Saved demo.</b> " + esc(d.note));
  else notes.push(`<b>Live analysis</b> of ${esc(d.company)} · collected ${esc(d.collected_at)} · ${d.n_items} items`);
  if (d.warning) notes.push("<b>Warning:</b> " + esc(d.warning));
  banner(notes.join("<br>"), !!d.warning);
  kpis(d); sources(d); radar(d); pulse(d); dimTable(d); actions(d); stakeholders(d); crisis(d);
  frames(d); monthly(d); stock(d); digital(d); reality(d); renderItems(d.items, "");
  window.scrollTo({ top: $("banner").offsetTop - 10, behavior: "smooth" });
}

function kpis(d) {
  const tt = d.two_track || {};
  const fired = d.stakeholders.filter(s => s.status === "fired").length;
  $("kpis").innerHTML = `
    <div class="kpi"><div class="v">${fmt(d.reptrak.score)}</div><div class="l">RepTrak score (1-5)</div><span class="b">${esc(d.reptrak.band)}</span></div>
    <div class="kpi alt"><div class="v">${fmt(d.pulse.score)}</div><div class="l">RepTrak Pulse</div><span class="b">${esc(d.pulse.band)}</span></div>
    <div class="kpi alt"><div class="v">${fmt(d.stakeholder_index)}</div><div class="l">Stakeholder index (toolkit weights)</div><span class="b">target 3.8</span></div>
    <div class="kpi light"><div class="v">${fired}/8</div><div class="l">Stakeholder triggers fired</div><span class="b">${d.actionables.length} actionables</span></div>
    <div class="kpi light"><div class="v">${d.n_items}</div><div class="l">Items analysed</div><span class="b">${Object.keys(d.counts).length} source${Object.keys(d.counts).length === 1 ? "" : "s"}</span></div>`;
}

function sources(d) {
  const names = { google_news: "Google News", bing_news: "Bing News", reddit: "Reddit", stock: "Share price", play_store: "Google Play", instagram: "Instagram", x: "X" };
  $("sources").innerHTML = Object.entries(d.status).map(([k, v]) =>
    `<span class="chip ${v.ok ? "ok" : "bad"}" title="${esc(v.error || v.note || "")}">${names[k] || k}: ${v.ok ? (v.n ?? "") + " items" : "unavailable"} <small>${esc(v.note || (v.ok ? "" : (v.error || "")).slice(0, 60))}</small></span>`).join("");
}

function radar(d) {
  const dims = Object.keys(d.reptrak.dimensions);
  chart("radar", {
    type: "radar",
    data: { labels: dims, datasets: [{ label: "Score", data: dims.map(k => d.reptrak.dimensions[k].score ?? 3), borderColor: C.red, backgroundColor: "rgba(226,55,68,.18)", pointBackgroundColor: C.maroon, borderWidth: 2.5 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { r: { min: 1, max: 5, ticks: { stepSize: 1, backdropColor: "transparent" }, grid: { color: C.light }, angleLines: { color: C.light }, pointLabels: { font: { size: 13, weight: "bold" }, color: C.maroon } } } }
  });
}

function pulse(d) {
  $("pulse").innerHTML = Object.entries(d.pulse.items).map(([k, v]) => `
    <div class="pulse-row"><span>${k}</span><div class="bar"><div style="width:${(v - 1) / 4 * 100}%;background:${v >= 3.5 ? C.maroon : v >= 2.9 ? C.rose : C.red}"></div></div><span>${fmt(v)}</span></div>`).join("");
  const t = d.two_track || {};
  $("twotrack").innerHTML = `
    <div class="tt"><div class="v pos">${pct(t.financial_positive_share)}</div><div class="small">of financial items positive (n=${t.financial_n ?? 0})</div></div>
    <div class="tt"><div class="v neg">${pct(t.nonfinancial_negative_share)}</div><div class="small">of non-financial items negative (n=${t.nonfinancial_n ?? 0})</div></div>`;
}

function dimTable(d) {
  const rows = Object.entries(d.reptrak.dimensions).map(([k, v]) => `
    <tr><td><b>${k}</b><div class="muted small">${esc(v.basis)}</div></td>
    <td><span class="score ${sc(v.score)}">${fmt(v.score)}</span></td><td>${v.n}</td><td class="${tonecls(v.tone)}">${fmt(v.tone)}</td>
    <td class="small">${v.worst.slice(0, 2).map(e => `${esc(e.text)} <span class="muted">(${esc(e.date || "")})</span>`).join("<br>") || "<span class='muted'>no items</span>"}</td></tr>`).join("");
  $("dimtable").innerHTML = `<tr><th>Dimension</th><th>Score</th><th>Items</th><th>Tone</th><th>Most negative evidence</th></tr>` + rows;
}

function actions(d) {
  if (!d.actionables.length) { $("actions").innerHTML = "<p class='muted'>No toolkit triggers fired.</p>"; return; }
  $("actions").innerHTML = d.actionables.map(a => `
    <div class="act ${a.status}"><div class="rank">${a.rank}</div><div>
      <h4>${esc(a.stakeholder)} <span class="status st-${a.status}">${a.status === "fired" ? "trigger fired" : "watch"}</span>
        <span class="pill">${esc(a.horizon)}</span>${a.scct ? `<span class="pill">SCCT: ${esc(a.scct)}</span>` : ""}<span class="pill">priority ${a.priority}</span></h4>
      <div class="grid">
        <div><b>Why</b>${esc(a.why)}</div>
        <div><b>Response rule</b>${esc(a.do)}</div>
        <div><b>Recommendation</b>${esc(a.recommendation || "")}</div>
        <div><b>Channel & cadence</b>${esc(a.channel)}</div>
        <div><b>Message frame</b>${esc(a.frame)}</div>
        <div><b>KPI · owner</b>${esc(a.kpi)} · ${esc(a.owner)}</div>
        ${a.scct_response ? `<div style="grid-column:1/-1"><b>SCCT posture</b>${esc(a.scct_response)}</div>` : ""}
      </div>
      ${a.evidence.length ? `<div class="ev">Evidence: ${a.evidence.map(e => `“${esc(e.text)}” (${esc(e.date || "")})`).join(" · ")}</div>` : ""}
    </div></div>`).join("");
}

function stakeholders(d) {
  $("sindex").textContent = `Weighted index ${fmt(d.stakeholder_index)} / 5`;
  $("stable").innerHTML = `<tr><th>Stakeholder</th><th>Salience</th><th>Weight</th><th>Items</th><th>Tone</th><th>Score</th><th>Status</th><th>Early-warning trigger</th></tr>` +
    d.stakeholders.map(s => `<tr><td><b>${esc(s.name)}</b><div class="muted small">${esc(s.example)}</div></td><td>${esc(s.salience)}</td><td>${s.weight}%</td><td>${s.n}</td>
      <td class="${tonecls(s.tone)}">${fmt(s.tone)}</td><td><span class="score ${sc(s.score)}">${fmt(s.score)}</span></td>
      <td><span class="status st-${s.status}">${s.status}</span></td><td class="small">${esc(s.trigger)}</td></tr>`).join("");
}

function crisis(d) {
  if (!d.crisis_radar.length) { $("radarcrisis").innerHTML = "<p class='muted'>No crisis-cue items detected.</p>"; return; }
  $("radarcrisis").innerHTML = d.crisis_radar.map(c => `
    <div class="cluster"><h4>${esc(c.cluster)} cluster · ${c.n} items</h4>
      <div class="small"><b>Prescribed:</b> ${esc(c.response)} <span class="pill">${esc(c.posture)}</span></div>
      <ul>${c.items.slice(0, 4).map(i => `<li>${esc(i.text)} <span class="muted">(${esc(i.date || "")})</span></li>`).join("")}</ul></div>`).join("");
}

function frames(d) {
  const f = Object.entries(d.frames).sort((a, b) => (b[1].negative + b[1].neutral + b[1].positive) - (a[1].negative + a[1].neutral + a[1].positive));
  chart("frames", {
    type: "bar",
    data: { labels: f.map(x => x[0]), datasets: [
      { label: "Negative", data: f.map(x => x[1].negative), backgroundColor: C.red, borderRadius: 6 },
      { label: "Neutral", data: f.map(x => x[1].neutral), backgroundColor: C.light, borderRadius: 6 },
      { label: "Positive", data: f.map(x => x[1].positive), backgroundColor: C.maroon, borderRadius: 6 }] },
    options: { indexAxis: "y", maintainAspectRatio: false, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { display: false } } }, plugins: { legend: { position: "bottom" } } }
  });
}

function monthly(d) {
  const m = d.monthly_tone || [];
  chart("monthly", {
    type: "bar",
    data: { labels: m.map(x => x.month), datasets: [{ label: "Average tone", data: m.map(x => x.tone), backgroundColor: m.map(x => x.tone >= 0 ? C.maroon : C.red), borderRadius: 6 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: c => "items: " + m[c.dataIndex].n } } }, scales: { y: { min: -1, max: 1, grid: { color: C.pink } }, x: { grid: { display: false } } } }
  });
}

function stock(d) {
  const s = d.stock_series || [], m = d.stock;
  $("stockmeta").textContent = m ? `${d.inputs.ticker || ""} · 1y ${pct(m.r1y)} · 3m ${pct(m.r3m)} · market score ${fmt(m.market_score)}${m.indicative ? " · indicative points" : ""}` : "no market data";
  chart("stock", {
    type: "line",
    data: { labels: s.map(p => p[0]), datasets: [{ label: "Close", data: s.map(p => p[1]), borderColor: C.red, backgroundColor: "rgba(226,55,68,.12)", fill: true, pointRadius: s.length > 40 ? 0 : 4, tension: .2 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { grid: { color: C.pink } } } }
  });
}

function digital(d) {
  const g = d.digital || {}, p = d.play;
  const box = (v, l) => `<div class="tt"><div class="v">${v}</div><div class="small">${l}</div></div>`;
  let h = "<div class='dig'>";
  h += g.instagram ? box((g.instagram.followers || 0).toLocaleString(), "Instagram followers") + box(g.instagram.engagement_rate !== null && g.instagram.engagement_rate !== undefined ? (g.instagram.engagement_rate * 100).toFixed(2) + "%" : "n/a", "Instagram engagement rate (recent posts)") : box("n/a", "Instagram not available");
  h += g.x ? box(g.x.followers ? g.x.followers.toLocaleString() : "n/a", "X followers") + box(fmt(g.x.tone), "Tone of recent posts") : box("n/a", "X not available");
  h += p ? box(fmt(p.score, 2) + "★", `${esc(p.app || "App")} · ${(p.ratings || 0).toLocaleString()} ratings`) + box(pct(p.one_star_share), "1-star share of recent reviews") : box("n/a", "App store not available");
  $("digital").innerHTML = h + "</div>";
}

function reality(d) {
  if (!d.reality_check.length) { $("reality").innerHTML = "<p class='muted'>No operating proxies available.</p>"; return; }
  $("reality").innerHTML = `<table><tr><th>Proxy</th><th>Coverage-based score</th><th>Operating proxy</th><th>Gap</th></tr>` +
    d.reality_check.map(r => `<tr><td><b>${esc(r.proxy)}</b></td><td>${fmt(r.perception)}</td><td>${fmt(r.value)}</td><td class="${(r.perception - r.value) > 0.2 ? "neg" : "pos"}">${fmt(r.perception - r.value)}</td></tr>`).join("") + "</table>";
}

function renderItems(items, q) {
  q = (q || "").toLowerCase();
  const f = items.filter(i => !q || [i.text, i.source, i.publisher, (i.stakeholders || []).join(" "), (i.dims || []).join(" "), i.frame].join(" ").toLowerCase().includes(q));
  $("items").innerHTML = `<tr><th>Date</th><th>Item</th><th>Source</th><th>Tone</th><th>Frame</th><th>Dimensions</th><th>Stakeholders</th><th>SCCT</th></tr>` +
    f.slice(0, 250).map(i => `<tr><td class="small">${esc(i.date || "")}</td><td>${i.url ? `<a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.text)}</a>` : esc(i.text)}</td>
      <td class="small">${esc(i.source)}${i.publisher ? "<br><span class='muted'>" + esc(i.publisher) + "</span>" : ""}</td>
      <td class="${tonecls(i.sentiment)}">${fmt(i.sentiment)}</td><td class="small">${esc(i.frame)}</td><td class="small">${esc((i.dims || []).join(", "))}</td>
      <td class="small">${esc((i.stakeholders || []).join(", "))}</td><td class="small">${esc(i.crisis || "")}</td></tr>`).join("");
}
