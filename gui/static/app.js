"use strict";

// Race Engineer: la pagina chiede lo stato al server una volta al
// secondo e lo disegna. Tutti i calcoli stanno in Python
// (gui/snapshot.py): qui solo formattazione e grafici SVG, senza
// librerie esterne, così la pagina funziona anche senza internet.

const DRIVER_COLORS = [
  "#4e79a7", "#f28e2b", "#59a14f", "#e15759",
  "#b07aa1", "#76b7b2", "#ff9da7", "#9c755f",
];

const SELECTED_STINT = "Stint selezionato";

let state = null;
let windowKey = load("window") || "Ultimi 10";
let selectedStint = Number(load("stint")) || null;
let activeTab = load("tab") || "race";
let pitShownFor = null;
let startShown = false;
let pollTimer = null;

const $ = (id) => document.getElementById(id);

// ==============================
// FORMATI
// ==============================

function pad(value, size = 2) {
  return String(value).padStart(size, "0");
}

function fmtLap(ms) {
  if (ms == null) return "–";
  const sign = ms < 0 ? "−" : "";
  const total = Math.abs(Math.round(ms));
  const minutes = Math.floor(total / 60000);
  const seconds = Math.floor((total % 60000) / 1000);
  const millis = total % 1000;
  return minutes
    ? `${sign}${minutes}:${pad(seconds)}.${pad(millis, 3)}`
    : `${sign}${seconds}.${pad(millis, 3)}`;
}

function fmtClock(ms) {
  if (ms == null) return "–";
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 3600)}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
}

function fmtDur(ms) {
  if (ms == null) return "–";
  const total = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours
    ? `${hours}:${pad(minutes)}:${pad(total % 60)}`
    : `${minutes}:${pad(total % 60)}`;
}

function fmtDelta(ms, digits = 3) {
  if (ms == null) return "–";
  const sign = ms > 0 ? "+" : ms < 0 ? "−" : "±";
  return sign + (Math.abs(ms) / 1000).toFixed(digits);
}

function fmtStd(ms) {
  return ms == null ? "–" : (ms / 1000).toFixed(3);
}

function fmtTrend(value) {
  if (value == null) return "–";
  return `${value > 0 ? "+" : ""}${Math.round(value)} ms/giro`;
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function driverColor(driverId) {
  const index = (state?.drivers_list || []).findIndex((d) => d.id === driverId);
  return DRIVER_COLORS[(index < 0 ? 0 : index) % DRIVER_COLORS.length];
}

function load(key) {
  try { return localStorage.getItem(`re.${key}`); } catch { return null; }
}

function save(key, value) {
  try { localStorage.setItem(`re.${key}`, value); } catch { /* facoltativo */ }
}

// ==============================
// COMUNICAZIONE CON IL SERVER
// ==============================

async function poll() {
  clearTimeout(pollTimer);

  try {
    const params = new URLSearchParams({ window: windowKey });
    if (selectedStint) params.set("stint", selectedStint);

    const response = await fetch(`/api/state?${params}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    state = await response.json();
    render();
  } catch (error) {
    const feed = $("feed");
    feed.textContent = "GUI scollegata dal programma";
    feed.className = "chip bad";
  } finally {
    pollTimer = setTimeout(poll, 1000);
  }
}

async function post(path, data = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) throw new Error(body.error || `Errore ${response.status}`);

  return body;
}

function toast(message, isError = false) {
  const element = $("toast");
  element.textContent = message;
  element.className = isError ? "toast error" : "toast";
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, isError ? 7000 : 3500);
}

// ==============================
// DISEGNO GENERALE
// ==============================

function render() {
  if (!state) return;

  renderHeader();
  renderBanners();
  renderActions();

  if (activeTab === "race") {
    renderTiles();
    renderWindowChart();
    renderNeighbors();
    renderTimeline();
  } else if (activeTab === "standings") {
    renderStandings();
  } else if (activeTab === "drivers") {
    renderRaceChart();
    renderDriverChart();
    renderDriversTable();
    renderStintsTable();
  } else if (activeTab === "karts") {
    renderKarts();
  } else if (activeTab === "log") {
    renderLog();
  }

  syncDialogs();
}

function renderHeader() {
  const { feed, race, source } = state;

  $("team").textContent = state.team || "–";
  $("k-pos").textContent = feed.position ? `P${feed.position}` : "–";
  $("k-gap").textContent = feed.gap || (feed.position === 1 ? "Primi" : "–");
  $("k-lap").textContent = feed.lap ?? (state.laps.at(-1)?.n ?? "–");
  $("k-time").textContent = fmtClock(race.time);
  $("k-remaining").textContent = fmtClock(race.remaining);

  const flags = {
    lg: ["Bandiera verde", "good"],
    ly: ["Bandiera gialla", "warn"],
    lr: ["Bandiera rossa", "bad"],
    lf: ["Bandiera a scacchi", ""],
    lc: ["Bandiera a scacchi", ""],
  };

  const [flagText, flagClass] = flags[race.flag] || [race.flag ? `Bandiera ${race.flag}` : "Bandiera –", ""];
  $("flag").textContent = flagText;
  $("flag").className = `chip ${flagClass}`;

  let feedClass = "";
  let feedText = source.status;

  if (source.mode === "diretta") {
    feedClass = source.status.startsWith("collegato") ? "good" : source.status.startsWith("caduto") ? "bad" : "warn";
    feedText = `Diretta · ${source.status}`;
  } else if (source.mode === "rilettura") {
    feedClass = "good";
    feedText = `Rilettura x${source.speed} · ${source.status.startsWith("rilettura terminata") ? "terminata" : "in corso"}`;
  } else {
    feedClass = "warn";
    feedText = "Manuale · nessun feed";
  }

  if (source.mode !== "manuale" && !source.bound) {
    feedClass = "warn";
    feedText += " · squadra non agganciata";
  }

  $("feed").textContent = feedText;
  $("feed").className = `chip ${feedClass}`;

  const select = $("window");
  if (select.options.length !== state.window.keys.length) {
    select.innerHTML = state.window.keys.map((key) => `<option>${esc(key)}</option>`).join("");
  }
  select.value = state.window.key;
}

function renderBanners() {
  const banners = [];
  const pending = state.pending_pit;
  const now = state.race.time;

  if (pending) {
    const inPit = pending.out_time == null && pending.in_time != null && now != null
      ? `ai box da ${fmtDur(now - pending.in_time)}`
      : pending.measured != null ? `sosta misurata ${fmtLap(pending.measured)}` : "";

    const chosen = pending.driver
      ? ` · riparte ${esc(pending.driver)}, kart dal feed all'uscita`
      : "";

    banners.push({
      cls: pending.driver ? "warn" : "bad pulse",
      text: `PIT IN dopo il giro ${pending.lap_before}` +
        (inPit ? ` · ${inPit}` : "") +
        chosen +
        (pending.feed_kart ? ` · kart ora nel feed #${esc(pending.feed_kart)}` : "") +
        (state.pending_laps ? ` · giri in sospeso: ${state.pending_laps}` : ""),
      buttons: [[pending.driver ? "Cambia pilota" : "Conferma pit", "danger", openPit], ["Falso allarme", "", discardPit]],
    });
  }

  const auto = state.auto_start;

  if (!state.current && auto?.enabled && auto.started && !auto.driver) {
    banners.push({
      cls: "bad pulse",
      text: "GARA PARTITA: scegliere il pilota di partenza. Tempo e giro del via sono già presi dal feed" +
        (state.pending_laps ? `; giri in sospeso: ${state.pending_laps}.` : "."),
      buttons: [["Scegli pilota", "danger", openStart]],
    });
  } else if (!state.current && auto?.enabled) {
    banners.push({
      cls: "warn",
      text: (auto.practice
        ? `Sessione "${esc(state.race.title)}": la gara si avvierà da sola quando parte la sessione di gara.`
        : "In attesa del via: la gara si avvia da sola dal feed.") +
        (auto.driver ? ` Pilota di partenza: ${esc(auto.driver)}.` : " Scegliere il pilota di partenza.") +
        (state.source.bound ? "" : " Squadra non ancora agganciata."),
      buttons: [[auto.driver ? "Cambia pilota" : "Scegli pilota di partenza", "primary", openStart]],
    });
  } else if (!state.current && (state.pending_laps || state.source.bound)) {
    banners.push({
      cls: "warn",
      text: "Gara non avviata: scegliere pilota e kart di partenza." +
        (state.pending_laps ? ` Giri in sospeso: ${state.pending_laps}.` : ""),
      buttons: [["Avvia gara", "primary", openStart]],
    });
  }

  const current = state.current;
  if (current && !pending && state.feed.kart && String(current.kart) !== String(state.feed.kart)) {
    banners.push({
      cls: "warn",
      text: `Kart diverso: lo stint è sul kart #${current.kart}, il feed dice #${esc(state.feed.kart)}. Verificare.`,
    });
  }

  for (const warning of state.plan?.warnings || []) {
    if (warning.startsWith("Piloti ancora")) continue;
    banners.push({ cls: warning.startsWith("Stint oltre") ? "bad" : "warn", text: esc(warning) });
  }

  if (state.source.mode === "diretta" && state.source.status.startsWith("caduto")) {
    banners.push({
      cls: "bad",
      text: `Feed caduto (${esc(state.source.status)}). Si può continuare a mano: Giro a mano e PIT.`,
    });
  }

  const container = $("banners");
  container.innerHTML = "";

  for (const banner of banners) {
    const element = document.createElement("div");
    element.className = `banner ${banner.cls}`;
    element.innerHTML = `<span class="banner-text">${banner.text}</span>`;

    for (const [label, cls, handler] of banner.buttons || []) {
      const button = document.createElement("button");
      button.textContent = label;
      button.className = cls;
      button.onclick = handler;
      element.append(button);
    }

    container.append(element);
  }
}

function renderActions() {
  $("btn-start").hidden = Boolean(state.current);
  $("btn-pit").hidden = !state.current;
}

// ==============================
// SCHEDA GARA
// ==============================

function renderTiles() {
  const { current, plan, ours, race } = state;
  const now = race.time;
  const lastLap = state.laps.at(-1);
  const bestLap = state.laps.reduce((best, lap) => (best == null || lap.t < best ? lap.t : best), null);

  const tiles = [];

  tiles.push({
    label: "Pilota",
    value: current ? esc(current.driver) : "–",
    note: current ? `Stint ${current.stint_number} · ${current.stint_laps} giri` : "gara non avviata",
  });

  let kartNote = "classifica kart: dati insufficienti";
  let kartClass = "";
  if (current?.kart_delta != null) {
    const slow = current.kart_delta > 0;
    kartNote = `<span class="${slow ? "bad-text" : "good-text"}">${fmtDelta(current.kart_delta)} s</span> dal passo abituale (${current.kart_delta_laps} giri)`;
    if (current.kart_delta > 250) kartClass = "warn";
  }
  tiles.push({
    label: "Kart",
    value: current?.kart != null ? `#${current.kart}` : "–",
    note: kartNote,
    cls: kartClass,
  });

  if (plan && now != null) {
    const toLimit = plan.stint_limit - now;
    const share = Math.min(1, plan.stint_elapsed / race.max_stint);
    const bandFrom = plan.window_open != null ? (plan.window_open - plan.stint_start) / race.max_stint : null;
    const bandTo = plan.window_close != null ? (plan.window_close - plan.stint_start) / race.max_stint : null;
    const fillColor = toLimit < 0 ? css("--bad") : toLimit < 5 * 60000 ? css("--warn") : css("--good");

    tiles.push({
      label: "Stint",
      value: fmtDur(plan.stint_elapsed),
      html: `<div class="progress">
          ${bandFrom != null ? `<div class="progress-band" style="left:${Math.max(0, bandFrom) * 100}%;width:${Math.max(0, bandTo - Math.max(0, bandFrom)) * 100}%"></div>` : ""}
          <div class="progress-fill" style="width:${share * 100}%;background:${fillColor}"></div>
        </div>`,
      note: `limite ${fmtDur(race.max_stint)} · mancano ${toLimit >= 0 ? fmtDur(toLimit) : "0:00"}`,
      cls: toLimit < 0 ? "bad" : toLimit < 5 * 60000 ? "warn" : "",
    });
  } else {
    tiles.push({ label: "Stint", value: "–", note: "" });
  }

  const lastDelta = lastLap && ours.avg != null ? lastLap.t - ours.avg : null;
  tiles.push({
    label: "Ultimo giro",
    value: fmtLap(lastLap?.t),
    note: lastDelta == null ? "" : `<span class="${lastDelta <= 0 ? "good-text" : "bad-text"}">${fmtDelta(lastDelta)}</span> dalla media`,
  });

  tiles.push({
    label: `Media · ${esc(windowKey)}`,
    value: fmtLap(ours.avg),
    note: `σ ${fmtStd(ours.std)} s · ${ours.laps} giri`,
  });

  tiles.push({
    label: `Migliore · ${esc(windowKey)}`,
    value: fmtLap(ours.best),
    note: `in gara ${fmtLap(bestLap)}`,
  });

  if (plan && now != null) {
    const done = plan.pits_done;
    const total = plan.pits_done + plan.pits_remaining;

    if (!plan.pits_remaining) {
      tiles.push({ label: "Prossimo pit", value: "Nessuno", note: `pit fatti ${done} · obbligo rispettato` });
    } else {
      const open = plan.window_open;
      const close = plan.window_close;
      let value = `tra ${fmtDur(plan.target_pit - now)}`;
      let cls = "";

      if (now > close) {
        value = "IN RITARDO";
        cls = "bad";
      } else if (now >= open) {
        value = "FINESTRA APERTA";
        cls = "warn";
      }

      tiles.push({
        label: "Prossimo pit",
        value,
        note: `al minuto ${fmtDur(open - plan.stint_start)}–${fmtDur(close - plan.stint_start)} dello stint · pit ${done + 1} di ${total}`,
        cls,
      });
    }
  } else {
    tiles.push({ label: "Prossimo pit", value: "–", note: "" });
  }

  $("tiles").innerHTML = tiles.map((tile) => `
    <div class="tile ${tile.cls || ""}">
      <div class="tile-label">${tile.label}</div>
      <div class="tile-value">${tile.value}</div>
      ${tile.html || ""}
      <div class="tile-note">${tile.note || ""}</div>
    </div>`).join("");
}

function competitorOutliers(points) {
  const sorted = points.map((p) => p[1]).sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  return (value) => value > median * 1.07;
}

function renderWindowChart() {
  const windowLaps = new Set(state.window.laps);
  const drivers = Object.fromEntries(state.drivers_list.map((d) => [d.id, d.name]));

  const ourPoints = state.laps
    .filter((lap) => windowLaps.has(lap.n) && lap.rt != null)
    .map((lap) => ({
      x: lap.rt,
      y: lap.t,
      outlier: !lap.clean,
      tip: `<b>Noi</b> · giro ${lap.n}<br>${fmtLap(lap.t)} · ${esc(drivers[lap.d] || "")} · kart #${lap.k ?? "–"}`,
    }));

  const series = [{ label: "Noi", color: css("--us"), width: 2.5, points: ourPoints }];

  for (const [side, color, name] of [["ahead", "--ahead", "Davanti"], ["behind", "--behind", "Dietro"]]) {
    const row = state.neighbors[side];
    if (!row || !row.points.length) continue;
    const isOutlier = competitorOutliers(row.points);
    series.push({
      label: `${name}: ${row.team}`,
      color: css(color),
      width: 1.5,
      points: row.points.map(([x, y]) => ({
        x, y, outlier: isOutlier(y),
        tip: `<b>${esc(row.team)}</b> (${name.toLowerCase()})<br>${fmtLap(y)} · kart #${esc(row.kart)}`,
      })),
    });
  }

  const vlines = state.stints
    .filter((stint) => stint.start != null && stint.number > 1)
    .map((stint) => ({ x: stint.start, label: `S${stint.number}` }));

  $("chart-window-sub").textContent = `${windowKey}${windowKey === SELECTED_STINT && selectedStint ? ` ${selectedStint}` : ""} · asse orizzontale: tempo di gara`;

  lineChart($("chart-window"), {
    series,
    vlines,
    hlines: state.ours.avg != null ? [{ y: state.ours.avg, color: css("--us"), label: "media" }] : [],
    xTicks: timeTicks,
    xPad: 30000,
    empty: "Nessun giro nella finestra scelta.",
  });

  $("legend-window").innerHTML = series
    .map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`)
    .join("") + `<span><i style="background:${css("--us")};opacity:.5"></i>media dei giri puliti (tratteggio)</span>`;
}

function renderNeighbors() {
  const ours = state.ours;
  const cards = [];

  for (const [side, label] of [["ahead", "Davanti"], ["behind", "Dietro"]]) {
    const row = state.neighbors[side];

    if (!row) {
      cards.push(`<div class="neighbor ${side}"><div class="neighbor-head"><span>${label.toUpperCase()}</span></div><div class="neighbor-team">–</div></div>`);
      continue;
    }

    const interval = side === "ahead" ? state.feed.interval_ahead : row.interval;
    const gapText = interval != null ? fmtLap(interval) : esc(row.gap || "–");
    const theirAvg = row.window.avg;
    let verdict = "Passo non confrontabile: servono giri puliti nella finestra.";

    if (theirAvg != null && ours.avg != null) {
      const diff = theirAvg - ours.avg;
      const faster = diff > 0;
      const perLap = `${(Math.abs(diff) / 1000).toFixed(3)} s/giro`;

      if (Math.abs(diff) < 20) {
        verdict = "Stesso passo.";
      } else if (side === "ahead") {
        verdict = faster
          ? `<span class="good-text">Recuperiamo ${perLap}</span>` + (interval != null ? ` · aggancio in ~${Math.ceil(interval / diff)} giri` : "")
          : `<span class="bad-text">Ci staccano di ${perLap}</span>`;
      } else {
        verdict = faster
          ? `<span class="good-text">Guadagniamo ${perLap}</span>`
          : `<span class="bad-text">Ci recuperano ${perLap}</span>` + (interval != null ? ` · ci prendono in ~${Math.ceil(interval / -diff)} giri` : "");
      }
    }

    cards.push(`
      <div class="neighbor ${side}">
        <div class="neighbor-head">
          <span>${label.toUpperCase()} · P${row.pos ?? "–"} · kart #${esc(row.kart)}</span>
          ${row.in_pit ? '<span class="badge warn">AI BOX</span>' : ""}
        </div>
        <div class="neighbor-team">${esc(row.team)}</div>
        <div class="neighbor-grid">
          <div><span>Distacco</span><b>${gapText}</b></div>
          <div><span>Ultimo</span><b>${fmtLap(row.last)}</b></div>
          <div><span>Media finestra</span><b>${fmtLap(theirAvg)}</b></div>
        </div>
        <div class="neighbor-verdict">${verdict}</div>
      </div>`);
  }

  $("neighbors").innerHTML = cards.join("");
}

function renderTimeline() {
  const { race, plan } = state;
  const element = $("timeline");
  const width = element.clientWidth;
  const height = element.clientHeight;
  if (!width) return;

  const margin = { l: 10, r: 10, t: 22, b: 22 };
  const X = (ms) => margin.l + (Math.max(0, Math.min(ms, race.duration)) / race.duration) * (width - margin.l - margin.r);
  const barTop = margin.t + 6;
  const barHeight = height - margin.t - margin.b - 18;
  const now = race.time ?? 0;
  const parts = [];

  for (let hour = 0; hour * 3600000 <= race.duration; hour++) {
    const x = X(hour * 3600000);
    parts.push(`<line x1="${x}" x2="${x}" y1="${margin.t}" y2="${height - margin.b}" stroke="${css("--grid")}"/>`);
    parts.push(`<text x="${x}" y="${height - 6}" text-anchor="middle" class="label">${hour}h</text>`);
  }

  if (plan && plan.window_open != null) {
    const x0 = X(plan.window_open);
    const x1 = X(plan.window_close);
    parts.push(`<rect x="${x0}" y="${margin.t}" width="${Math.max(1, x1 - x0)}" height="${height - margin.t - margin.b}" fill="${css("--band")}"/>`);
    parts.push(`<line x1="${X(plan.target_pit)}" x2="${X(plan.target_pit)}" y1="${margin.t}" y2="${height - margin.b}" stroke="${css("--accent")}" stroke-dasharray="4 3"/>`);
    parts.push(`<text x="${X(plan.target_pit)}" y="${margin.t - 8}" text-anchor="middle" class="label">pit obiettivo ${fmtClock(plan.target_pit)}</text>`);

    // Stint futuri previsti, a durata uguale.
    let start = plan.target_pit + plan.average_pit;
    for (let index = 1; index < plan.pits_remaining + 1 && start < race.duration; index++) {
      const end = index < plan.pits_remaining ? start + plan.target_stint : race.duration;
      parts.push(`<rect x="${X(start)}" y="${barTop}" width="${Math.max(1, X(end) - X(start))}" height="${barHeight}" fill="none" stroke="${css("--muted")}" stroke-dasharray="3 3" rx="3"/>`);
      start = end + plan.average_pit;
    }
  }

  if (plan && plan.stint_limit <= race.duration) {
    const x = X(plan.stint_limit);
    parts.push(`<line x1="${x}" x2="${x}" y1="${margin.t}" y2="${height - margin.b}" stroke="${css("--bad")}" stroke-width="2"/>`);
    parts.push(`<text x="${x + 4}" y="${height - margin.b - 4}" class="label" style="fill:${css("--bad")}">limite</text>`);
  }

  const hover = [];

  for (const stint of state.stints) {
    if (stint.start == null) continue;
    const end = stint.open ? now : stint.start + (stint.duration ?? 0);
    const x0 = X(stint.start);
    const x1 = X(end);
    const color = driverColor(stint.driver_id);
    parts.push(`<rect x="${x0}" y="${barTop}" width="${Math.max(1, x1 - x0 - 1)}" height="${barHeight}" fill="${color}" rx="3"/>`);
    if (x1 - x0 > 46) {
      parts.push(`<text x="${(x0 + x1) / 2}" y="${barTop + barHeight / 2 + 4}" text-anchor="middle" style="fill:#fff;font-size:11px;font-weight:600">${esc(stint.driver.slice(0, 10))}</text>`);
    }
    hover.push({
      x0, x1,
      tip: `<b>Stint ${stint.number}</b> · ${esc(stint.driver)} · kart #${stint.kart ?? "–"}<br>` +
        `${fmtClock(stint.start)} → ${stint.open ? "in corso" : fmtClock(end)} · ${fmtDur(stint.duration)} · ${stint.pace.laps} giri<br>` +
        `media ${fmtLap(stint.pace.avg)} · σ ${fmtStd(stint.pace.std)}`,
    });
  }

  for (const stint of state.stints.slice(1)) {
    if (stint.start == null) continue;
    const x = X(stint.start);
    parts.push(`<line x1="${x}" x2="${x}" y1="${barTop - 4}" y2="${barTop + barHeight + 4}" stroke="${css("--text")}" stroke-width="2"/>`);
  }

  const nowX = X(now);
  parts.push(`<line x1="${nowX}" x2="${nowX}" y1="${margin.t - 2}" y2="${height - margin.b}" stroke="${css("--text")}" stroke-width="1.5"/>`);

  element.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${parts.join("")}</svg>`;

  element.onmousemove = (event) => {
    const x = event.clientX - element.getBoundingClientRect().left;
    const hit = hover.find((item) => x >= item.x0 && x <= item.x1);
    if (hit) showTip(event, hit.tip); else hideTip();
  };
  element.onmouseleave = hideTip;

  $("timeline-sub").textContent = plan
    ? `pit ${plan.pits_done} fatti, ${plan.pits_remaining} da fare · sosta media ${fmtLap(plan.average_pit)} · stint obiettivo ${fmtDur(plan.target_stint)}` +
      (plan.unused_drivers.length ? ` · da schierare: ${plan.unused_drivers.join(", ")}` : "")
    : "la finestra compare quando la gara è avviata";
}

// ==============================
// CLASSIFICA
// ==============================

function renderStandings() {
  $("standings-sub").textContent = `media, migliore e σ sulla finestra: ${windowKey}`;

  if (!state.competitors.length) {
    $("standings-table").innerHTML = '<div class="empty">Nessun dato dal feed.</div>';
    return;
  }

  const rows = state.competitors.map((row) => `
    <tr class="${row.is_us ? "us" : ""}">
      <td class="r">${row.pos ?? "–"}</td>
      <td class="r">${esc(row.kart)}</td>
      <td>${esc(row.team)}</td>
      <td class="r">${row.laps ?? "–"}</td>
      <td class="r">${fmtLap(row.last)}</td>
      <td class="r">${fmtLap(row.best)}</td>
      <td class="r">${fmtLap(row.window.avg)}</td>
      <td class="r">${fmtLap(row.window.best)}</td>
      <td class="r">${fmtStd(row.window.std)}</td>
      <td class="r">${esc(row.gap || "")}</td>
      <td class="r">${row.interval != null ? fmtLap(row.interval) : ""}</td>
      <td class="r">${row.pits ?? "–"}</td>
      <td>${row.in_pit ? '<span class="badge warn">AI BOX</span>' : ""}</td>
    </tr>`).join("");

  $("standings-table").innerHTML = `
    <table>
      <thead><tr>
        <th class="r">Pos</th><th class="r">Kart</th><th>Squadra</th><th class="r">Giri</th>
        <th class="r">Ultimo</th><th class="r">Migliore</th><th class="r">Media finestra</th>
        <th class="r">Migliore finestra</th><th class="r">σ</th><th class="r">Distacco</th>
        <th class="r">Interv.</th><th class="r">Pit</th><th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ==============================
// PILOTI E STINT
// ==============================

function renderRaceChart() {
  const drivers = Object.fromEntries(state.drivers_list.map((d) => [d.id, d.name]));
  const byStint = new Map();

  for (const lap of state.laps) {
    if (!byStint.has(lap.s)) byStint.set(lap.s, []);
    byStint.get(lap.s).push(lap);
  }

  const series = [...byStint.values()].map((laps) => ({
    color: driverColor(laps[0].d),
    width: 1.5,
    points: laps.map((lap) => ({
      x: lap.n,
      y: lap.t,
      outlier: !lap.clean,
      tip: `Giro ${lap.n} · <b>${fmtLap(lap.t)}</b><br>${esc(drivers[lap.d] || "")} · stint ${lap.s ?? "–"} · kart #${lap.k ?? "–"}`,
    })),
  }));

  const windowLaps = state.window.laps;
  const bands = windowLaps.length
    ? [{ x0: Math.min(...windowLaps) - 0.5, x1: Math.max(...windowLaps) + 0.5 }]
    : [];

  lineChart($("chart-race"), {
    series,
    bands,
    vlines: state.stints.filter((s) => s.number > 1 && s.start_lap != null).map((s) => ({ x: s.start_lap + 0.5, label: `S${s.number}` })),
    xTicks: lapTicks,
    xPad: 1,
    empty: "Nessun giro registrato.",
  });

  $("legend-race").innerHTML = state.drivers_list
    .map((d) => `<span><i style="background:${driverColor(d.id)}"></i>${esc(d.name)}</span>`)
    .join("") + `<span><i style="background:${css("--band")}"></i>finestra di analisi</span>`;
}

function renderDriverChart() {
  const withPace = state.drivers.filter((d) => d.pace.avg != null);
  const fastest = Math.min(...withPace.map((d) => d.pace.avg));

  barChart($("chart-drivers"), withPace.map((d) => ({
    label: d.name,
    value: d.pace.avg - fastest,
    err: d.pace.std,
    color: driverColor(d.id),
    text: `${fmtDelta(d.pace.avg - fastest)} · ${fmtLap(d.pace.avg)}`,
    tip: `<b>${esc(d.name)}</b><br>media ${fmtLap(d.pace.avg)} · σ ${fmtStd(d.pace.std)}<br>${d.pace.clean} giri puliti su ${d.pace.laps}`,
  })), { empty: "Nessun pilota ha ancora giri puliti." });
}

function renderDriversTable() {
  const averages = state.drivers.map((d) => d.pace.avg).filter((v) => v != null);
  const fastest = averages.length ? Math.min(...averages) : null;

  const rows = state.drivers.map((d) => `
    <tr>
      <td><span class="swatch" style="background:${driverColor(d.id)}"></span>${esc(d.name)}</td>
      <td class="r">${d.stints}</td>
      <td class="r">${fmtDur(d.driving)}</td>
      <td class="r">${d.pace.laps}</td>
      <td class="r">${fmtLap(d.pace.best)}</td>
      <td class="r">${fmtLap(d.pace.avg)}</td>
      <td class="r">${fmtLap(d.pace.median)}</td>
      <td class="r">${fmtStd(d.pace.std)}</td>
      <td class="r">${fmtTrend(d.pace.trend)}</td>
      <td class="r">${d.pace.avg != null && fastest != null ? fmtDelta(d.pace.avg - fastest) : "–"}</td>
    </tr>`).join("");

  $("drivers-table").innerHTML = `
    <table>
      <thead><tr>
        <th>Pilota</th><th class="r">Stint</th><th class="r">Guida</th><th class="r">Giri</th>
        <th class="r">Migliore</th><th class="r">Media</th><th class="r">Mediana</th><th class="r">σ</th>
        <th class="r">Tendenza</th><th class="r">Δ</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderStintsTable() {
  if (!state.stints.length) {
    $("stints-table").innerHTML = '<div class="empty">Nessuno stint.</div>';
    return;
  }

  const rows = state.stints.map((s) => `
    <tr class="clickable ${windowKey === SELECTED_STINT && selectedStint === s.number ? "selected" : ""}" data-stint="${s.number}">
      <td class="r">${s.number}</td>
      <td><span class="swatch" style="background:${driverColor(s.driver_id)}"></span>${esc(s.driver)}</td>
      <td class="r">#${s.kart ?? "–"}</td>
      <td class="r">${s.start_lap ?? "–"}–${s.end_lap ?? "…"}</td>
      <td class="r">${s.pace.laps}</td>
      <td class="r">${fmtDur(s.duration)}</td>
      <td class="r">${fmtLap(s.pace.best)}</td>
      <td class="r">${fmtLap(s.pace.avg)}</td>
      <td class="r">${fmtStd(s.pace.std)}</td>
      <td class="r">${fmtTrend(s.pace.trend)}</td>
      <td>${s.open ? '<span class="badge good">in corso</span>' : ""}</td>
    </tr>`).join("");

  $("stints-table").innerHTML = `
    <table>
      <thead><tr>
        <th class="r">#</th><th>Pilota</th><th class="r">Kart</th><th class="r">Giri (da–a)</th>
        <th class="r">N.</th><th class="r">Durata</th><th class="r">Migliore</th><th class="r">Media</th>
        <th class="r">σ</th><th class="r">Tendenza</th><th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  for (const row of $("stints-table").querySelectorAll("tr[data-stint]")) {
    row.onclick = () => {
      selectedStint = Number(row.dataset.stint);
      windowKey = SELECTED_STINT;
      save("stint", selectedStint);
      save("window", windowKey);
      poll();
    };
  }
}

// ==============================
// KART
// ==============================

function renderKarts() {
  const karts = state.karts;
  const element = $("chart-karts");
  element.style.height = `${Math.max(240, karts.length * 22 + 40)}px`;

  barChart(element, karts.map((k) => ({
    label: `#${k.number}${k.current ? " ◀" : ""}`,
    value: k.delta,
    color: k.delta > 0 ? css("--bad") : css("--good"),
    highlight: k.current,
    text: fmtDelta(k.delta),
    tip: `<b>Kart #${esc(k.number)}</b>${k.current ? " (il nostro)" : ""}<br>${fmtDelta(k.delta)} s · ${k.laps} giri · ${k.teams} squadre`,
  })), { diverging: true, empty: "Servono almeno 5 giri puliti per kart: i dati arrivano dal feed." });

  $("karts-table").innerHTML = karts.length ? `
    <table>
      <thead><tr><th>Kart</th><th class="r">Scarto</th><th class="r">Giri</th><th class="r">Squadre</th></tr></thead>
      <tbody>${karts.map((k) => `
        <tr class="${k.current ? "us" : ""}">
          <td>#${esc(k.number)}${k.current ? " (nostro)" : ""}</td>
          <td class="r ${k.delta > 0 ? "bad-text" : "good-text"}">${fmtDelta(k.delta)}</td>
          <td class="r">${k.laps}</td>
          <td class="r">${k.teams}</td>
        </tr>`).join("")}</tbody>
    </table>` : "";
}

// ==============================
// REGOLE E REGISTRO
// ==============================

function renderLog() {
  const statusBadge = { ok: ["OK", "good"], warning: ["ATTENZIONE", "warn"], violation: ["VIOLAZIONE", "bad"] };
  const order = { violation: 0, warning: 1, ok: 2 };
  const rules = [...state.rules].sort((a, b) => order[a.status] - order[b.status]);
  const counts = rules.reduce((acc, rule) => ({ ...acc, [rule.status]: (acc[rule.status] || 0) + 1 }), {});

  $("rules-sub").textContent = `${counts.violation || 0} violazioni · ${counts.warning || 0} attenzioni · ${counts.ok || 0} ok`;

  $("rules").innerHTML = rules.map((rule) => {
    const [text, cls] = statusBadge[rule.status] || [rule.status, ""];
    return `<div class="rule"><span class="badge ${cls}">${text}</span><span><b>${esc(rule.rule)}</b> · ${esc(rule.message)}</span></div>`;
  }).join("");

  $("alerts").innerHTML = state.alerts.length
    ? state.alerts.map((alert) => `<div class="alert ${alert.level}"><time>${fmtClock(alert.time)}</time><span>${esc(alert.message)}</span></div>`).join("")
    : '<div class="empty">Nessun avviso.</div>';

  $("pits-table").innerHTML = state.pit_stops.length ? `
    <table>
      <thead><tr><th class="r">Dopo giro</th><th>Kart</th><th>Pilota</th><th class="r">Durata</th><th></th></tr></thead>
      <tbody>${state.pit_stops.map((pit) => `
        <tr>
          <td class="r">${pit.lap}</td>
          <td>#${pit.kart_out ?? "–"} → #${pit.kart_in ?? "–"}</td>
          <td>${esc(pit.driver_out)} → ${esc(pit.driver_in)}</td>
          <td class="r ${pit.ok ? "" : "bad-text"}">${fmtLap(pit.duration)}</td>
          <td>${pit.refuel ? '<span class="badge">benzina</span> ' : ""}${pit.tire_change ? '<span class="badge">gomme</span>' : ""}</td>
        </tr>`).join("")}</tbody>
    </table>` : '<div class="empty">Nessun pit stop.</div>';

  $("events-table").innerHTML = state.events.length ? `
    <table>
      <thead><tr><th class="r">Tempo gara</th><th>Evento</th><th class="r">Penalità</th></tr></thead>
      <tbody>${state.events.map((event) => `
        <tr>
          <td class="r">${fmtClock(event.time)}</td>
          <td>${esc(event.description)}</td>
          <td class="r">${event.penalty ? `${(event.penalty / 1000).toFixed(1)} s` : ""}</td>
        </tr>`).join("")}</tbody>
    </table>` : '<div class="empty">Nessun evento.</div>';
}

// ==============================
// GRAFICI SVG
// ==============================

function niceStep(span, count) {
  const raw = span / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (raw <= factor * power) return factor * power;
  }
  return 10 * power;
}

function timeTicks(x0, x1) {
  const steps = [15, 30, 60, 120, 300, 600, 900, 1800, 3600].map((s) => s * 1000);
  const step = steps.find((s) => (x1 - x0) / s <= 7) || 3600000;
  const ticks = [];
  for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) ticks.push({ v, label: fmtClock(v) });
  return ticks;
}

function lapTicks(x0, x1) {
  const step = Math.max(1, niceStep(x1 - x0, 8));
  const ticks = [];
  for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) ticks.push({ v, label: String(Math.round(v)) });
  return ticks;
}

function lineChart(element, options) {
  const width = element.clientWidth;
  const height = element.clientHeight;
  if (!width) return;

  const all = options.series.flatMap((s) => s.points);

  if (!all.length) {
    element.innerHTML = `<div class="empty">${options.empty || "Nessun dato."}</div>`;
    element.onmousemove = null;
    return;
  }

  const margin = { l: 50, r: 12, t: 14, b: 24 };
  const clean = all.filter((p) => !p.outlier);
  const values = (clean.length ? clean : all).map((p) => p.y);
  for (const line of options.hlines || []) values.push(line.y);

  let y0 = Math.min(...values);
  let y1 = Math.max(...values);
  const yPad = Math.max((y1 - y0) * 0.12, 200);
  y0 -= yPad;
  y1 += yPad;

  let x0 = Math.min(...all.map((p) => p.x));
  let x1 = Math.max(...all.map((p) => p.x));
  if (x0 === x1) {
    x0 -= options.xPad || 1;
    x1 += options.xPad || 1;
  }

  const plotW = width - margin.l - margin.r;
  const plotH = height - margin.t - margin.b;
  const X = (v) => margin.l + ((v - x0) / (x1 - x0)) * plotW;
  const Y = (v) => margin.t + (1 - (Math.max(y0, Math.min(v, y1)) - y0) / (y1 - y0)) * plotH;

  const parts = [];
  const grid = css("--grid");
  const muted = css("--muted");

  const yStep = niceStep(y1 - y0, 5);
  for (let v = Math.ceil(y0 / yStep) * yStep; v <= y1; v += yStep) {
    parts.push(`<line class="gridline" x1="${margin.l}" x2="${width - margin.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="${grid}"/>`);
    parts.push(`<text x="${margin.l - 6}" y="${Y(v) + 4}" text-anchor="end" class="label">${(v / 1000).toFixed(yStep < 1000 ? 1 : 0)}</text>`);
  }

  for (const tick of options.xTicks(x0, x1)) {
    parts.push(`<text x="${X(tick.v)}" y="${height - 6}" text-anchor="middle" class="label">${tick.label}</text>`);
  }

  for (const band of options.bands || []) {
    const bx0 = X(Math.max(x0, band.x0));
    const bx1 = X(Math.min(x1, band.x1));
    if (bx1 > bx0) parts.push(`<rect x="${bx0}" y="${margin.t}" width="${bx1 - bx0}" height="${plotH}" fill="${css("--band")}"/>`);
  }

  for (const line of options.vlines || []) {
    if (line.x < x0 || line.x > x1) continue;
    parts.push(`<line x1="${X(line.x)}" x2="${X(line.x)}" y1="${margin.t}" y2="${margin.t + plotH}" stroke="${muted}" stroke-dasharray="2 3"/>`);
    parts.push(`<text x="${X(line.x) + 3}" y="${margin.t + 10}" class="label">${esc(line.label)}</text>`);
  }

  for (const line of options.hlines || []) {
    parts.push(`<line x1="${margin.l}" x2="${width - margin.r}" y1="${Y(line.y)}" y2="${Y(line.y)}" stroke="${line.color}" stroke-dasharray="6 4" opacity="0.7"/>`);
  }

  const hover = [];
  const radius = all.length > 200 ? 2 : 3;

  for (const s of options.series) {
    const inRange = s.points.filter((p) => !p.outlier);
    if (inRange.length > 1) {
      const d = inRange.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
      parts.push(`<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.5}" stroke-linejoin="round" opacity="0.9"/>`);
    }

    for (const p of s.points) {
      const px = X(p.x);
      if (p.outlier) {
        const py = margin.t + 2;
        parts.push(`<path d="M${px - 4},${py} L${px + 4},${py} L${px},${py + 7} Z" fill="${s.color}" opacity="0.8"/>`);
        hover.push({ px, py: py + 3, tip: `${p.tip}<br><i>fuori scala: pit o bandiera</i>` });
      } else {
        const py = Y(p.y);
        parts.push(`<circle cx="${px}" cy="${py}" r="${radius}" fill="${s.color}"/>`);
        hover.push({ px, py, tip: p.tip });
      }
    }
  }

  parts.push(`<line class="baseline" x1="${margin.l}" x2="${width - margin.r}" y1="${margin.t + plotH}" y2="${margin.t + plotH}" stroke="${muted}"/>`);

  element.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${parts.join("")}</svg>`;

  element.onmousemove = (event) => {
    const rect = element.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;
    let best = null;
    let bestDistance = Infinity;
    for (const point of hover) {
      const distance = (point.px - mx) ** 2 + ((point.py - my) ** 2) * 0.25;
      if (distance < bestDistance) {
        best = point;
        bestDistance = distance;
      }
    }
    if (best && bestDistance < 900) showTip(event, best.tip); else hideTip();
  };
  element.onmouseleave = hideTip;
}

function barChart(element, items, options = {}) {
  const width = element.clientWidth;
  const height = element.clientHeight;
  if (!width) return;

  if (!items.length) {
    element.innerHTML = `<div class="empty">${options.empty || "Nessun dato."}</div>`;
    element.onmousemove = null;
    return;
  }

  const margin = { l: 90, r: 110, t: 8, b: 8 };
  const rowH = Math.min(30, (height - margin.t - margin.b) / items.length);
  const plotW = width - margin.l - margin.r;

  let lo;
  let hi;
  if (options.diverging) {
    const extent = Math.max(100, ...items.map((i) => Math.abs(i.value)));
    lo = -extent;
    hi = extent;
  } else {
    lo = 0;
    hi = Math.max(100, ...items.map((i) => i.value + (i.err || 0)));
  }

  const X = (v) => margin.l + ((v - lo) / (hi - lo)) * plotW;
  const parts = [];
  const hover = [];
  const text = css("--text");

  parts.push(`<line x1="${X(0)}" x2="${X(0)}" y1="${margin.t}" y2="${margin.t + rowH * items.length}" stroke="${css("--muted")}"/>`);

  items.forEach((item, index) => {
    const y = margin.t + index * rowH;
    const barH = Math.max(4, rowH * 0.62);
    const by = y + (rowH - barH) / 2;
    const xa = X(Math.min(0, item.value));
    const xb = X(Math.max(0, item.value));

    parts.push(`<text x="${margin.l - 8}" y="${y + rowH / 2 + 4}" text-anchor="end" style="fill:${text};font-size:12px;font-weight:${item.highlight ? 700 : 400}">${esc(item.label)}</text>`);
    parts.push(`<rect x="${xa}" y="${by}" width="${Math.max(1, xb - xa)}" height="${barH}" fill="${item.color}" rx="2" ${item.highlight ? `stroke="${text}" stroke-width="2"` : ""}/>`);

    if (item.err) {
      const e0 = X(Math.max(lo, item.value - item.err));
      const e1 = X(Math.min(hi, item.value + item.err));
      const ey = y + rowH / 2;
      parts.push(`<line x1="${e0}" x2="${e1}" y1="${ey}" y2="${ey}" stroke="${text}" stroke-width="1.5" opacity="0.6"/>`);
    }

    const labelX = options.diverging ? width - margin.r + 8 : Math.max(xb, X(item.value + (item.err || 0))) + 6;
    parts.push(`<text x="${labelX}" y="${y + rowH / 2 + 4}" class="label" style="fill:${css("--muted")}">${esc(item.text || "")}</text>`);

    hover.push({ y0: y, y1: y + rowH, tip: item.tip });
  });

  element.innerHTML = `<svg viewBox="0 0 ${width} ${height}">${parts.join("")}</svg>`;

  element.onmousemove = (event) => {
    const y = event.clientY - element.getBoundingClientRect().top;
    const hit = hover.find((h) => y >= h.y0 && y < h.y1);
    if (hit?.tip) showTip(event, hit.tip); else hideTip();
  };
  element.onmouseleave = hideTip;
}

function showTip(event, html) {
  const tip = $("tooltip");
  tip.innerHTML = html;
  tip.hidden = false;
  const x = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(event.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}

function hideTip() {
  $("tooltip").hidden = true;
}

// ==============================
// FINESTRE DI DIALOGO
// ==============================

// L'ordine dei piloti non è quello degli stint: nessuno è proposto,
// e accanto a ogni nome ci sono stint e tempo di guida.
function fillDrivers(select, selectedId = null) {
  const stats = new Map((state.drivers || []).map((d) => [d.id, d]));
  const options = state.drivers_list.map((d) => {
    const s = stats.get(d.id);
    const info = s ? ` · ${s.stints} stint, ${fmtDur(s.driving)}` : "";
    return `<option value="${d.id}" ${d.id === selectedId ? "selected" : ""}>${esc(d.name)}${info}</option>`;
  });
  select.innerHTML =
    `<option value="" disabled ${selectedId == null ? "selected" : ""}>— scegliere —</option>` +
    options.join("");
}

function openStart() {
  if (!state) return;
  const form = $("dlg-start").querySelector("form");
  const auto = state.auto_start;
  fillDrivers(form.driver_id, auto?.driver_id ?? null);
  form.kart_number.value = "";
  form.kart_number.placeholder = state.feed.kart ? `#${state.feed.kart}` : "";
  form.querySelector("button.primary").textContent = auto?.enabled ? "Conferma" : "Avvia";

  const kartHint = state.feed.kart
    ? `Kart dal feed: #${state.feed.kart}.`
    : "Nessun kart dal feed.";

  $("start-hint").textContent = auto?.enabled
    ? (auto.started
      ? "Gara partita: tempo e giro del via sono già presi dal feed. "
      : "La gara parte da sola al via, con tempo, giro e kart dal feed. ") +
      kartHint + " Scrivere un kart solo per avviarla subito a mano."
    : state.feed.kart
      ? `${kartHint} Lasciare vuoto per usarlo.`
      : "Nessun kart dal feed: inserirlo a mano.";

  if (auto?.started) startShown = true;
  $("dlg-start").showModal();
  form.driver_id.focus();
}

function openPit() {
  if (!state || !state.current) return;
  const form = $("dlg-pit").querySelector("form");
  const pending = state.pending_pit;
  const current = state.current;

  $("pit-current").innerHTML = `Ora in pista: <b>${esc(current.driver)}</b> sul kart <b>#${current.kart}</b>`;

  const feedKart = state.feed.kart || "";
  const inPit = pending && !pending.out_seen;

  form.kart_number.value = "";
  form.kart_number.placeholder = inPit ? "dal feed all'uscita" : feedKart ? `#${feedKart}` : "";
  fillDrivers(form.driver_id, pending?.driver_id ?? null);
  form.duration_s.value = pending?.measured != null ? (pending.measured / 1000).toFixed(1) : "";
  form.refuel.checked = false;
  form.tire_change.checked = false;

  $("pit-hint").textContent = pending
    ? `Ingresso dopo il giro ${pending.lap_before}.` +
      (inPit
        ? " Scegliere il pilota: il kart nuovo si prende dal feed all'uscita dai box."
        : feedKart ? ` Kart dal feed: #${feedKart}.` : " Il feed non indica il kart: inserirlo a mano.") +
      (pending.measured == null ? " Durata: si riempie all'uscita dai box." : "")
    : "Pit inserito a mano: vale dopo l'ultimo giro registrato." +
      (feedKart ? ` Kart vuoto = #${feedKart} dal feed.` : " Inserire il kart.");

  $("btn-discard").hidden = !pending;
  pitShownFor = pending ? pending.lap_before : pitShownFor;
  $("dlg-pit").showModal();
  form.driver_id.focus();
}

async function discardPit() {
  try {
    await post("/api/pit/discard");
    $("dlg-pit").close();
    toast("Pit annullato: i giri in sospeso vanno allo stint in corso.");
    poll();
  } catch (error) {
    toast(error.message, true);
  }
}

function syncDialogs() {
  const pending = state.pending_pit;
  const dialog = $("dlg-pit");

  // Si apre da sola al PitIn, una volta per pit.
  if (pending && pitShownFor !== pending.lap_before && !dialog.open && !document.querySelector("dialog[open]")) {
    openPit();
  }

  // Al via senza pilota di partenza la scelta si apre da sola, una volta.
  const auto = state.auto_start;
  if (!state.current && auto?.enabled && auto.started && !auto.driver && !startShown && !document.querySelector("dialog[open]")) {
    openStart();
  }

  if (!pending && dialog.open && $("btn-discard").hidden === false) {
    dialog.close();
  }

  // Durata misurata arrivata mentre la finestra è aperta.
  if (pending && dialog.open && pending.measured != null) {
    const input = dialog.querySelector("form").duration_s;
    if (!input.value) input.value = (pending.measured / 1000).toFixed(1);
  }
}

function setupForms() {
  for (const dialog of document.querySelectorAll("dialog")) {
    const form = dialog.querySelector("form");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const action = event.submitter?.value || "ok";

      if (action === "cancel") {
        dialog.close();
        return;
      }

      if (action === "discard") {
        await discardPit();
        return;
      }

      if (!form.reportValidity()) return;

      const data = {};
      for (const element of form.elements) {
        if (!element.name) continue;
        data[element.name] = element.type === "checkbox" ? element.checked : element.value;
      }

      try {
        await post(form.dataset.action, data);
        dialog.close();
        toast("Registrato.");
        poll();
      } catch (error) {
        toast(error.message, true);
      }
    });
  }
}

// ==============================
// AVVIO
// ==============================

function setTab(name) {
  if (!$(`tab-${name}`)) name = "race";
  activeTab = name;
  save("tab", name);
  history.replaceState(null, "", `#${name}`);
  for (const button of document.querySelectorAll(".tab-buttons button")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const section of document.querySelectorAll(".tab")) {
    section.classList.toggle("active", section.id === `tab-${name}`);
  }
  render();
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function setup() {
  applyTheme(load("theme"));

  $("btn-theme").onclick = () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    applyTheme(next);
    save("theme", next);
    render();
  };

  for (const button of document.querySelectorAll(".tab-buttons button")) {
    button.onclick = () => setTab(button.dataset.tab);
  }

  $("window").onchange = (event) => {
    windowKey = event.target.value;
    save("window", windowKey);
    if (windowKey === SELECTED_STINT && !selectedStint) {
      selectedStint = state?.current?.stint_number || 1;
    }
    poll();
  };

  $("btn-start").onclick = openStart;
  $("btn-pit").onclick = openPit;
  $("btn-lap").onclick = () => $("dlg-lap").showModal();
  $("btn-event").onclick = () => $("dlg-event").showModal();
  $("btn-export").onclick = async () => {
    try {
      const result = await post("/api/export");
      toast(`Gara esportata in ${result.folder}`);
    } catch (error) {
      toast(error.message, true);
    }
  };

  setupForms();
  window.addEventListener("resize", render);
  setTab(location.hash.slice(1) || activeTab);
  poll();
}

setup();
