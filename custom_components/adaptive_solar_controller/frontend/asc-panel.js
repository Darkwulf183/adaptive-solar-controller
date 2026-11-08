/* Adaptive Solar Controller – Sidebar-Panel (v0.4.6 RC4, Design 2)
 * Tabs: Übersicht · Planer & Prognose · Batterie & Lernen · Sicherheit · Steuerung
 * Alle Entity-IDs, Services und der CSV-Import sind unverändert zur Vorversion.
 */

// Deutsche Anzeigetexte für technische Zustandswerte. Unbekannte Werte werden
// automatisch lesbar gemacht ("foo_bar" -> "Foo bar"); der Rohwert steht im Tooltip.
const T = {
  none: "keiner", ok: "OK", unknown: "unbekannt", unavailable: "nicht verfügbar",
  active: "Aktiv", paused: "Pausiert", initializing: "Startet", warmup: "Aufwärmphase",
  solar_release_off: "Solar-Freigabe aus", grid_sensor_stale: "Netzsensor veraltet",
  healthy_energy_surplus: "Gesunder Energieüberschuss", within_energy_corridor: "Im Energiekorridor",
  target_energy_reserve_reached: "Zielreserve erreicht", battery_energy_recovery: "Batterie erholt sich",
  learning_energy_state: "Lernt Energiezustand", learning_total_gap_demand: "Lernt Gesamtbedarf",
  use_energy: "Energie nutzen", preserve: "Energie sparen", recovery: "Erholung", balanced: "Ausgeglichen",
  full_priority: "Vollladung hat Vorrang", learning: "Lernt",
  lead_normal: "Normalbetrieb", lead_building_toward_full: "Baut auf Vollladung hin",
  lead_daily_full: "Tägliche Vollladung", lead_full_hold: "Vollladung: Halten", lead_near_full: "Fast voll",
  lead_post_full: "Nach Vollladung", lead_preserve_for_tomorrow: "Energie für morgen sparen",
  lead_full_charging_lock: "Vollladung: Entladesperre", lead_full_emergency: "Vollladung dringend",
  lead_full_priority: "Vollladung priorisiert",
  tomorrow: "Morgen", today: "Heute", building: "Im Aufbau", emergency: "Dringend", fulfilled: "Erfüllt",
  full_hold: "Halten", daily_plan: "Tagesplan",
  lead_acid: "Blei-Säure", lifepo4: "LiFePO₄",
  synced: "Synchron", degraded: "Eingeschränkt", invalid: "Ungültig",
  trusted: "Vertrauenswürdig", reliable: "Zuverlässig",
  counting: "Zählt", full_confirmed: "FULL bestätigt", full_lockout: "FULL-Sperre", paused_discharge: "Pausiert (Entladung)",
  waiting_voltage: "Wartet auf Spannung", reset_stale: "Zurückgesetzt (veraltet)", full_reached: "Vollladung erreicht",
  chemistry_changed: "Chemie gewechselt",
  off: "Aus", monitor: "Monitor", adaptive: "Adaptiv", predictive: "Prädiktiv", idle: "Ruhend",
  undervoltage_pending: "Unterspannung – Bestätigung läuft", sensor_invalid_pending: "Sensor ungültig – Wartezeit läuft",
  cutoff_latched: "Abschaltung verriegelt", cutoff_switch_off_sent: "Abschaltung ausgelöst",
  cutoff_switch_error: "Abschaltung fehlgeschlagen", cutoff_no_dedicated_switch: "Kein Power-Schalter konfiguriert",
  cutoff_controller_disabled: "Verriegelt (Regler aus)",
  recovered_manual_reenable_if_needed: "Erholt – Wechselrichter ggf. manuell einschalten",
};
const SENSOR_NAMES = { battery_voltage: "Batteriespannung", battery_current: "Batteriestrom", grid: "Netzleistung", inverter_output: "Inverter-Ausgang" };
const pretty = (s) => { s = String(s).replace(/_/g, " ").trim(); return s ? s[0].toUpperCase() + s.slice(1) : s; };

class AdaptiveSolarControllerPanel extends HTMLElement {
  constructor() {
    super();
    this._tab = "overview";
    this._hist = null; this._histAt = 0; this._histBusy = false;
  }

  /* ---------- Entities ---------- */
  get cfg() { return {
    mode:"select.adaptive_solar_controller_control_mode",chem:"select.adaptive_solar_controller_battery_chemistry",
    enabled:"switch.adaptive_solar_controller_controller_enabled",recorder:"switch.adaptive_solar_controller_14_day_flight_recorder",calibration:"switch.adaptive_solar_controller_battery_calibration",
    state:"sensor.adaptive_solar_controller_controller_state",reason:"sensor.adaptive_solar_controller_blocked_reason",grid:"sensor.e320_power_in",target:"input_number.inverter_target_power",
    recommended:"sensor.adaptive_solar_controller_recommended_target",applied:"sensor.adaptive_solar_controller_applied_target",limit:"sensor.adaptive_solar_controller_effective_inverter_limit",
    stored:"sensor.adaptive_solar_controller_estimated_stored_battery_energy",capacity:"sensor.adaptive_solar_controller_learned_usable_battery_capacity",capacityConf:"sensor.adaptive_solar_controller_battery_capacity_confidence",
    reserve:"sensor.adaptive_solar_controller_estimated_battery_reserve",targetReserve:"sensor.adaptive_solar_controller_target_reserve_at_next_pv_charge",energyConf:"sensor.adaptive_solar_controller_battery_energy_state_confidence",
    envelope:"sensor.adaptive_solar_controller_battery_power_envelope",envelopeConf:"sensor.adaptive_solar_controller_battery_power_envelope_confidence",gamma:"sensor.adaptive_solar_controller_progressive_release_gamma",
    release:"sensor.adaptive_solar_controller_progressive_release_factor",planningConf:"sensor.adaptive_solar_controller_planning_confidence",planAdj:"sensor.adaptive_solar_controller_learned_planning_reserve_adjustment",
    evaluation:"sensor.adaptive_solar_controller_last_planner_self_evaluation",budget:"sensor.adaptive_solar_controller_battery_energy_budget",budgetState:"sensor.adaptive_solar_controller_battery_energy_budget_state",
    plannerReason:"sensor.adaptive_solar_controller_energy_planner_reason",fullPriority:"sensor.adaptive_solar_controller_lead_full_charge_priority",fullOpportunity:"sensor.adaptive_solar_controller_full_charge_opportunity",chemStrategy:"sensor.adaptive_solar_controller_battery_chemistry_strategy",daysFull:"sensor.adaptive_solar_controller_days_since_battery_full",h24:"sensor.adaptive_solar_controller_energy_horizon_24h_balance",h48:"sensor.adaptive_solar_controller_energy_horizon_48h_balance",h72:"sensor.adaptive_solar_controller_energy_horizon_72h_balance",
    actualToday:"sensor.adaptive_solar_controller_actual_pv_production_today",correctedToday:"sensor.adaptive_solar_controller_corrected_pv_forecast_today_total",forecast:"sensor.adaptive_solar_controller_solar_forecast_trust",forecastrep:"sensor.adaptive_solar_controller_solar_forecast_reputation",
    totalNeed:"sensor.adaptive_solar_controller_learned_total_energy_until_next_pv_charge",typical:"sensor.adaptive_solar_controller_typical_energy_demand_until_next_pv_charge",recent:"sensor.adaptive_solar_controller_recent_energy_demand_until_next_pv_charge",
    surplusPower:"sensor.adaptive_solar_controller_available_surplus_power",surplusEnergy:"sensor.adaptive_solar_controller_available_surplus_energy",surplusConf:"sensor.adaptive_solar_controller_surplus_confidence",
    absorptionElapsed:"sensor.adaptive_solar_controller_full_absorption_elapsed",absorptionRequired:"number.adaptive_solar_controller_full_absorption_required",absorptionRemaining:"sensor.adaptive_solar_controller_full_absorption_remaining",absorptionStatus:"sensor.adaptive_solar_controller_full_absorption_status",anchorSource:"sensor.adaptive_solar_controller_full_anchor_source",

    cutoffSetting:"number.adaptive_solar_controller_battery_hard_cutoff_voltage",emergencySetting:"number.adaptive_solar_controller_battery_emergency_terminal_cutoff_voltage",
    cutoffStatus:"sensor.adaptive_solar_controller_battery_hard_cutoff_status",cutoffActual:"sensor.adaptive_solar_controller_battery_hard_cutoff_voltage",
    reboundBins:"sensor.adaptive_solar_controller_rebound_valid_power_bins",reboundSag:"sensor.adaptive_solar_controller_rebound_predicted_voltage_sag",
    lowPhase:"sensor.adaptive_solar_controller_low_recovery_phase",lowRemaining:"sensor.adaptive_solar_controller_low_recovery_remaining",
    measureQuality:"sensor.adaptive_solar_controller_battery_measurement_quality",seasonalToday:"sensor.adaptive_solar_controller_seasonal_expected_pv_today",
    seasonalTomorrow:"sensor.adaptive_solar_controller_seasonal_expected_pv_tomorrow",seasonalConf:"sensor.adaptive_solar_controller_seasonal_confidence",
    inverterMax:"number.adaptive_solar_controller_inverter_max_power",lowMode:"select.adaptive_solar_controller_low_recovery_calibration_mode",
    lowStatus:"sensor.adaptive_solar_controller_low_recovery_status",lowStep:"sensor.adaptive_solar_controller_low_recovery_step",lowRuns:"sensor.adaptive_solar_controller_low_recovery_successful_runs",
    historyDays:"sensor.adaptive_solar_controller_seasonal_history_days",
    battery:"sensor.solar_average_voltage",current:"sensor.solar_complete_ampere",pv:"sensor.solar_watt_aktuell",events:"sensor.adaptive_solar_controller_asc_event_marker",flight:"sensor.adaptive_solar_controller_flight_recorder_file",
    load:"sensor.adaptive_solar_controller_estimated_house_load",predLoad:"sensor.adaptive_solar_controller_predicted_load"
  }; }
  get ids() { return this._ids || (this._ids = Object.values(this.cfg)); }

  /* ---------- Lifecycle ---------- */
  set hass(h) {
    this._hass = h;
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
      this._root.addEventListener("click", (e) => this._onClick(e));
      this._root.addEventListener("change", (e) => this._onChange(e));
    }
    if (Date.now() - this._histAt > 300000) this._loadHist();
    const sig = this._tab + "\u0002" + this._histAt + "\u0002" +
      this.ids.map((id) => { const e = h.states[id]; return e ? e.state + "|" + (e.attributes?.unit_of_measurement || "") : "-"; }).join("\u0001");
    if (sig === this._sig && this._root.firstChild) return;
    this._sig = sig; this.render();
  }
  set panel(p) { this._panel = p; if (this._hass) this.render(); }

  /* ---------- 24 h history for the trend charts ---------- */
  async _loadHist() {
    if (this._histBusy || !this._hass) return;
    this._histBusy = true;
    try {
      const c = this.cfg, ids = [c.battery, c.current, c.grid, c.applied, c.pv];
      const end = new Date(), start = new Date(end.getTime() - 24 * 3600 * 1000);
      const r = await this._hass.callWS({
        type: "history/history_during_period", start_time: start.toISOString(), end_time: end.toISOString(),
        entity_ids: ids, minimal_response: true, no_attributes: true, significant_changes_only: false,
      });
      const out = {};
      for (const id of ids) {
        const pts = [];
        for (const p of (r && r[id]) || []) {
          const v = parseFloat(p.s ?? p.state);
          let t = p.lu ?? p.lc ?? p.last_updated ?? p.last_changed;
          if (typeof t === "string") t = Date.parse(t) / 1000;
          if (Number.isFinite(v) && Number.isFinite(t)) pts.push([t, v]);
        }
        out[id] = pts;
      }
      this._hist = out;
    } catch (e) { /* Verlauf ist optional; nächster Versuch in 5 min */ }
    finally { this._histAt = Date.now(); this._histBusy = false; this._sig = null; this.render(); }
  }
  _down(pts, n) {
    if (pts.length <= n) return pts;
    const step = Math.ceil(pts.length / n), out = [];
    for (let i = 0; i < pts.length; i += step) {
      const s = pts.slice(i, i + step);
      out.push([s.reduce((a, p) => a + p[0], 0) / s.length, s.reduce((a, p) => a + p[1], 0) / s.length]);
    }
    return out;
  }

  /* ---------- Helpers ---------- */
  esc(v) { return String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  raw(id) { return this._hass?.states[id]?.state; }
  st(id) { const v = this.raw(id); return this.esc(v === undefined ? "—" : v); }
  num(id) {
    const v = this.raw(id);
    if (v === undefined || v === "" || v === "unknown" || v === "unavailable") return null;
    const n = Number(v); return Number.isFinite(n) ? n : null;
  }
  unit(id) { return this.esc(this._hass?.states[id]?.attributes?.unit_of_measurement || ""); }
  f(n, d = 0) { return n === null || n === undefined || !Number.isFinite(n) ? "—" : Number(n).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  fs(n, d = 0) { return n === null ? "—" : (n > 0 ? "+" : n < 0 ? "−" : "") + this.f(Math.abs(n), d); }
  val(id, d = 0, u) {
    const n = this.num(id), unit = u !== undefined ? u : this.unit(id);
    if (n === null) { const r = this.raw(id); return r === undefined || r === "unknown" || r === "unavailable" ? "—" : this.esc(r); }
    return this.f(n, d) + (unit ? " " + unit : "");
  }
  lab(id, over) {
    const r = this.raw(id);
    if (r === undefined) return "—";
    if (over && over[r] !== undefined) return over[r];
    if (T[r] !== undefined) return T[r];
    if (String(r).startsWith("sensor_invalid:")) return "Sensor ungültig: " + String(r).slice(15).split(",").map((k) => SENSOR_NAMES[k] || k).join(", ");
    // Nur einfache Schlüsselwörter verschönern; Freitexte (z. B. Planer-Bewertung) bleiben unverändert.
    return /^[a-z0-9_]+$/.test(String(r)) ? pretty(r) : String(r);
  }
  tone(p) { return p >= 70 ? "ok" : p >= 40 ? "acc" : "warn"; }
  clamp(p) { return Math.max(0, Math.min(100, p)); }
  info(id) { this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: id }, bubbles: true, composed: true })); }
  async mode(m) { await this._hass.callService("select", "select_option", { entity_id: this.cfg.mode, option: m }); }
  async chem(m) { await this._hass.callService("select", "select_option", { entity_id: this.cfg.chem, option: m }); }
  async toggle(id) { await this._hass.callService("switch", this.raw(id) === "on" ? "turn_off" : "turn_on", { entity_id: id }); }

  /* ---------- Building blocks ---------- */
  row(l, id, d = 0, u) { return `<div class="row click" data-e="${id}"><span>${l}</span><b>${this.val(id, d, u)}</b></div>`; }
  rowT(l, id, over) { return `<div class="row click" data-e="${id}"><span>${l}</span><b title="${this.st(id)}">${this.esc(this.lab(id, over))}</b></div>`; }
  bar(l, text, p, tone, { mark = null, e = "", sub = "" } = {}) {
    const m = mark === null ? "" : `<i class="mark" style="left:${this.clamp(mark)}%"></i>`;
    return `<div class="meter ${e ? "click" : ""}" ${e ? `data-e="${e}"` : ""}><div class="mh"><span>${l}</span><b>${text}</b></div><div class="track"><div class="fill ${tone}" style="width:${this.clamp(p)}%"></div>${m}</div>${sub ? `<div class="msub">${sub}</div>` : ""}</div>`;
  }
  meter(l, id, { max = 100, d = 0, u = "%", mark = null, sub = "" } = {}) {
    const n = this.num(id), p = n === null ? 0 : n / max * 100;
    return this.bar(l, this.val(id, d, u), p, n === null ? "mute" : this.tone(p), { mark, e: id, sub });
  }
  ring(l, p, center, sub, tone, e = "") {
    return `<div class="ring ${e ? "click" : ""}" ${e ? `data-e="${e}"` : ""}><div class="rwrap"><svg viewBox="0 0 36 36"><circle class="rb" cx="18" cy="18" r="15.9155"/><circle class="rf ${tone}" cx="18" cy="18" r="15.9155" pathLength="100" stroke-dasharray="${this.clamp(p)} 100"/></svg><div class="rc"><b>${center}</b><small>${sub}</small></div></div><span>${l}</span></div>`;
  }
  card(title, body, { cls = "", sub = "", icon = "" } = {}) {
    return `<section class="card ${cls}"><h2>${icon ? `<span class="ic">${icon}</span>` : ""}${title}</h2>${sub ? `<p class="hint top">${sub}</p>` : ""}${body}</section>`;
  }
  tog(label, desc, id, on, warn = false) {
    return `<button class="tog ${on ? "on" : ""} ${warn && on ? "warnon" : ""}" data-t="${id}" role="switch" aria-checked="${on}"><span>${label}<small>${desc}</small></span><i class="sw"></i></button>`;
  }
  seg(items, current, attr) {
    return `<div class="seg">${items.map(([v, l]) => `<button ${attr}="${v}" class="${current === v ? "active" : ""}">${l}</button>`).join("")}</div>`;
  }

  chart(title, series, { d = 1, unit = "", zero = false } = {}) {
    const W = 320, H = 88, P = 4, t1 = Date.now() / 1000, t0 = t1 - 86400;
    const data = series.map((s) => ({ ...s, pts: (this._hist?.[s.id] || []).filter((p) => p[0] >= t0 - 600) }));
    const all = data.flatMap((s) => s.pts.map((p) => p[1]));
    if (all.length < 2) return `<section class="card chart"><div class="ch"><h3>${title}</h3></div><div class="empty">${this._histAt ? "Keine Verlaufsdaten (Recorder?)" : "Verlauf wird geladen …"}</div></section>`;
    let lo = Math.min(...all), hi = Math.max(...all);
    const rawLo = lo, rawHi = hi;
    if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const X = (t) => Math.max(0, ((t - t0) / (t1 - t0)) * W), Y = (v) => H - P - ((v - lo) / (hi - lo)) * (H - 2 * P);
    const paths = data.map((s) => {
      const pts = this._down(s.pts, 160); if (pts.length < 2) return "";
      const dd = pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join("");
      const area = data.length === 1 ? `<path class="ar" style="fill:${s.color}" d="${dd}L${X(pts[pts.length - 1][0]).toFixed(1)} ${H}L${X(pts[0][0]).toFixed(1)} ${H}Z"/>` : "";
      return area + `<path class="ln" style="stroke:${s.color}" d="${dd}"/>`;
    }).join("");
    const zl = lo < 0 && hi > 0 ? `<line class="zl" x1="0" x2="${W}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}"/>` : "";
    const legend = data.map((s) => { const last = s.pts.length ? s.pts[s.pts.length - 1][1] : null; return `<span class="lg"><i style="background:${s.color}"></i>${s.label} <b>${this.f(last, d)}${unit ? " " + unit : ""}</b></span>`; }).join("");
    return `<section class="card chart"><div class="ch"><h3>${title}</h3><small>${this.f(rawLo, d)} … ${this.f(rawHi, d)} ${unit}</small></div><div class="legend">${legend}</div><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${title}, letzte 24 Stunden">${zl}${paths}</svg><div class="axis"><span>vor 24 h</span><span>jetzt</span></div></section>`;
  }

  /* ---------- Derived content ---------- */
  alerts() {
    const c = this.cfg, cs = String(this.raw(c.cutoffStatus) ?? ""), br = String(this.raw(c.reason) ?? ""), out = [];
    if (cs.startsWith("cutoff_") || cs.startsWith("trip")) out.push(["bad", "Batterieschutz hat ausgelöst", this.lab(c.cutoffStatus)]);
    else if (cs === "undervoltage_pending" || cs === "sensor_invalid_pending") out.push(["warn", "Batterieschutz prüft", this.lab(c.cutoffStatus)]);
    else if (cs.startsWith("recovered")) out.push(["info", "Batterie erholt", this.lab(c.cutoffStatus)]);
    if (br.startsWith("sensor_invalid")) out.push(["warn", "Regelung pausiert", this.lab(c.reason)]);
    if (this.raw(c.enabled) === "off") out.push(["info", "Regler ist ausgeschaltet", "ASC greift nicht ein, bis der Schalter „Controller enabled“ wieder an ist."]);
    if (this.raw(c.state) === "unavailable") out.push(["warn", "ASC-Entitäten nicht verfügbar", "Integration geladen? Panel zeigt bis dahin keine Werte."]);
    return out.map(([t, h, s]) => `<div class="alert ${t}" role="alert"><b>${this.esc(h)}</b><span>${this.esc(s)}</span></div>`).join("");
  }
  narrative() {
    const c = this.cfg, A = this.num(c.current), V = this.num(c.battery), pv = this.num(c.pv), g = this.num(c.grid), ap = this.num(c.applied);
    const bat = A !== null && V !== null ? A * V : null, parts = [];
    if (bat === null) parts.push("Batteriedaten nicht verfügbar");
    else if (A > 2) parts.push(`Akku lädt mit <b>${this.f(bat)} W</b>`);
    else if (A < -1) parts.push(`Akku entlädt mit <b>${this.f(-bat)} W</b>`);
    else parts.push("Akku nahezu ausgeglichen");
    if (pv !== null) parts.push(`PV liefert <b>${this.f(pv)} W</b>`);
    if (ap !== null) parts.push(`ASC stellt <b>${this.f(ap)} W</b> am Wechselrichter ein`);
    if (g !== null) parts.push(`Netz <b>${this.f(g)} W</b>`);
    return parts.join(" · ");
  }
  flow() {
    const c = this.cfg, A = this.num(c.current), V = this.num(c.battery), pv = this.num(c.pv), ap = this.num(c.applied), ld = this.num(c.load), g = this.num(c.grid);
    const bat = A !== null && V !== null ? A * V : null;
    const node = (ic, l, main, sub, tone, e) => `<div class="node click ${tone}" data-e="${e}"><div class="ni">${ic}</div><div class="nl">${l}</div><b>${main}</b><small>${sub}</small></div>`;
    const arrow = (on) => `<div class="arrow ${on ? "on" : ""}" aria-hidden="true"><i></i></div>`;
    const batTone = bat === null ? "mute" : A > 2 ? "ok" : A < -1 ? "warn" : "acc";
    return `<div class="flow">
      ${node("☀️", "PV", pv === null ? "—" : this.f(pv) + " W", pv > 20 ? "erzeugt" : "keine Erzeugung", pv > 20 ? "ok" : "mute", c.pv)}${arrow(pv > 20)}
      ${node("🔋", "Akku", bat === null ? "—" : this.fs(bat) + " W", `${this.f(V, 2)} V · ${this.fs(A, 1)} A`, batTone, c.current)}${arrow(ap > 20)}
      ${node("⚡", "Wechselrichter", ap === null ? "—" : this.f(ap) + " W", `Limit ${this.val(c.limit, 0, "W")}`, ap > 20 ? "acc" : "mute", c.applied)}${arrow(ld > 20)}
      ${node("🏠", "Haus", ld === null ? "—" : this.f(ld) + " W", `Netz ${g === null ? "—" : this.f(g) + " W"}`, "acc", c.load)}
    </div>`;
  }

  /* ---------- Tabs ---------- */
  tabOverview() {
    const c = this.cfg, res = this.num(c.reserve), tr = this.num(c.targetReserve), st = this.num(c.stored), cap = this.num(c.capacity);
    const a = this.num(c.actualToday), fc = this.num(c.correctedToday), dev = a !== null && fc !== null ? a - fc : null, devp = dev !== null && fc ? dev / fc * 100 : null;
    const bud = this.num(c.budget), pc = this.num(c.planningConf);
    const kpis = `<div class="kpis">
      <section class="card kpi">${this.ring("Batterie-Reserve", res ?? 0, res === null ? "—" : this.f(res), "%", res === null ? "mute" : res >= (tr ?? 0) ? "ok" : "warn", c.reserve)}<p class="ksub">Ziel ${this.val(c.targetReserve, 0, "%")}<br>${this.f(st, 1)} / ${this.f(cap, 1)} kWh</p></section>
      <section class="card kpi">${this.ring("PV heute", fc ? a / fc * 100 : 0, a === null ? "—" : this.f(a, 1), "kWh", "acc", c.actualToday)}<p class="ksub">Forecast ${this.f(fc, 1)} kWh<br>${dev === null ? "—" : `<span class="${dev < 0 ? "neg" : "pos"}">${this.fs(dev, 1)} kWh${devp === null ? "" : " (" + this.fs(devp, 0) + " %)"}</span>`}</p></section>
      <section class="card kpi"><div class="big ${bud === null ? "" : bud >= 0 ? "pos" : "neg"} click" data-e="${c.budget}">${bud === null ? "—" : this.fs(bud, 2)}<small>kWh</small></div><span class="kl">Energie-Budget</span><p class="ksub">${this.esc(this.lab(c.budgetState))}</p></section>
      <section class="card kpi">${this.ring("Planungs-Vertrauen", pc ?? 0, pc === null ? "—" : this.f(pc), "%", pc === null ? "mute" : this.tone(pc), c.planningConf)}<p class="ksub">Grund: ${this.esc(this.lab(c.plannerReason))}</p></section>
    </div>`;
    const charts = `<div class="charts">
      ${this.chart("Batteriespannung", [{ id: c.battery, color: "var(--acc)", label: "Spannung" }], { d: 2, unit: "V" })}
      ${this.chart("Batteriestrom", [{ id: c.current, color: "var(--ok)", label: "Strom" }], { d: 1, unit: "A", zero: true })}
      ${this.chart("PV-Leistung", [{ id: c.pv, color: "var(--warn)", label: "PV" }], { d: 0, unit: "W" })}
      ${this.chart("Netz & ASC-Zielwert", [{ id: c.grid, color: "var(--bad)", label: "Netz" }, { id: c.applied, color: "var(--acc)", label: "Ziel" }], { d: 0, unit: "W", zero: true })}
    </div>`;
    return this.flow() + kpis + charts;
  }

  tabPlanner() {
    const c = this.cfg, res = this.num(c.reserve), tr = this.num(c.targetReserve);
    const a = this.num(c.actualToday), fc = this.num(c.correctedToday), se = this.num(c.seasonalToday), st = this.num(c.seasonalTomorrow);
    const mx = Math.max(1, a ?? 0, fc ?? 0, se ?? 0), dev = a !== null && fc !== null ? a - fc : null;
    const hz = (l, id) => { const n = this.num(id); return `<div class="hbox ${n === null ? "" : n >= 0 ? "pos" : "neg"} click" data-e="${id}"><small>${l}</small><b>${n === null ? "—" : this.fs(n, 1)}</b><em>kWh</em></div>`; };
    const need = Math.max(0.1, this.num(c.totalNeed) ?? 0, this.num(c.typical) ?? 0, this.num(c.recent) ?? 0);
    const planner = this.card("Energie-Planer", `
      <div class="hero2"><div class="big click ${this.num(c.budget) >= 0 ? "pos" : "neg"}" data-e="${c.budget}">${this.num(c.budget) === null ? "—" : this.fs(this.num(c.budget), 2)}<small>kWh Budget</small></div>
      <div class="hero2t"><b>${this.esc(this.lab(c.budgetState))}</b><span>${this.esc(this.lab(c.plannerReason))}</span></div></div>
      ${this.bar("Reserve (Marke = Ziel)", this.val(c.reserve, 0, "%"), res ?? 0, res === null ? "mute" : res >= (tr ?? 0) ? "ok" : "warn", { mark: tr, e: c.reserve, sub: `Zielreserve bei nächster PV-Ladung: ${this.val(c.targetReserve, 0, "%")}` })}
      ${this.rowT("Letzte Bewertung", c.evaluation)}${this.row("Gelernte Reservekorrektur", c.planAdj, 1, "%")}`, { icon: "🧭" });
    const horizon = this.card("Energie-Horizont", `<div class="horizon">${hz("24 h", c.h24)}${hz("48 h", c.h48)}${hz("72 h", c.h72)}</div><p class="hint">Positiv = erwarteter Überschuss, negativ = erwartetes Defizit. 48/72 h nutzen bis zu eigenen Forecast-Sensoren den gelernten saisonalen PV-Wert als Proxy.</p>`, { icon: "🔭" });
    const pv = this.card("PV-Erzeugung heute", `
      ${this.bar("Echte Erzeugung", this.val(c.actualToday, 1, "kWh"), (a ?? 0) / mx * 100, "acc", { e: c.actualToday })}
      ${this.bar("Korrigierter Forecast", this.val(c.correctedToday, 1, "kWh"), (fc ?? 0) / mx * 100, "ok", { e: c.correctedToday })}
      ${this.bar("Saison-Erwartung", this.val(c.seasonalToday, 1, "kWh"), (se ?? 0) / mx * 100, "mute", { e: c.seasonalToday })}
      <div class="row"><span>Abweichung echt − Forecast</span><b class="${dev === null ? "" : dev < 0 ? "neg" : "pos"}">${dev === null ? "—" : this.fs(dev, 2) + " kWh"}</b></div>
      ${this.meter("Forecast-Vertrauen", c.forecast)}${this.rowT("Forecast-Reputation", c.forecastrep)}
      ${this.row("Saison-Erwartung morgen", c.seasonalTomorrow, 1, "kWh")}`, { icon: "☀️" });
    const demand = this.card("Bedarf & Überschuss", `
      ${this.bar("Gesamtbedarf gelernt", this.val(c.totalNeed, 2, "kWh"), (this.num(c.totalNeed) ?? 0) / need * 100, "acc", { e: c.totalNeed })}
      ${this.bar("Typischer Bedarf", this.val(c.typical, 2, "kWh"), (this.num(c.typical) ?? 0) / need * 100, "mute", { e: c.typical })}
      ${this.bar("Jüngster Bedarf", this.val(c.recent, 2, "kWh"), (this.num(c.recent) ?? 0) / need * 100, "mute", { e: c.recent })}
      <div class="sep"></div>
      ${this.row("Hauslast aktuell / erwartet", c.load, 0, "W").replace("</b>", ` / ${this.val(c.predLoad, 0, "W")}</b>`)}
      ${this.row("Überschuss-Leistung", c.surplusPower, 0, "W")}${this.row("Überschuss-Energie", c.surplusEnergy, 2, "kWh")}${this.meter("Überschuss-Vertrauen", c.surplusConf)}`, { icon: "🏠" });
    const chem = this.card("Chemie-Strategie", `
      ${this.rowT("Strategie", c.chemStrategy)}${this.rowT("Batterietyp", c.chem)}
      ${this.meter("Vollladungs-Priorität", c.fullPriority)}${this.rowT("Vollladungs-Gelegenheit", c.fullOpportunity)}${this.row("Tage seit letzter Vollladung", c.daysFull, 1, "Tage")}
      <p class="hint">LiFePO₄ behält die 4.3-Energiestrategie. Lead/PzS kann Energie über mehrere Tage für eine echte Vollladung zurückhalten.</p>`, { icon: "🧪" });
    return `<div class="cols">${planner}${horizon}${pv}${demand}${chem}</div>`;
  }

  tabBattery() {
    const c = this.cfg, st = this.num(c.stored), cap = this.num(c.capacity), A = this.num(c.current), V = this.num(c.battery);
    const el = this.num(c.absorptionElapsed), req = this.num(c.absorptionRequired);
    const bat = A !== null && V !== null ? A * V : null;
    const store = this.card("Speicher", `
      ${this.bar("Gespeicherte Energie", `${this.f(st, 2)} / ${this.f(cap, 2)} kWh`, cap ? (st ?? 0) / cap * 100 : 0, cap ? this.tone((st ?? 0) / cap * 100) : "mute", { e: c.stored, sub: `Nutzbare Kapazität (gelernt): ${this.val(c.capacity, 2, "kWh")}` })}
      ${this.row("Spannung", c.battery, 2, "V")}${this.row("Strom", c.current, 1, "A")}
      <div class="row"><span>Leistung (U × I)</span><b>${bat === null ? "—" : this.fs(bat, 0) + " W"}</b></div>
      ${this.rowT("Messqualität", c.measureQuality)}`, { icon: "🔋" });
    const learn = this.card("Lernstand", `
      <p class="hint top">Wie sicher ASC seine Schätzungen ist. Niedrige Werte bedeuten „lernt noch“, nicht „defekt“.</p>
      ${this.meter("Kapazität", c.capacityConf)}${this.meter("Energiezustand", c.energyConf)}${this.meter("Planung", c.planningConf)}
      ${this.meter("Leistungs-Envelope", c.envelopeConf)}${this.meter("Überschuss", c.surplusConf)}${this.meter("Saison-Modell", c.seasonalConf)}${this.meter("Forecast", c.forecast)}`, { icon: "🧠" });
    const env = this.card("Leistungs-Envelope", `
      ${this.row("Akku erlaubt momentan", c.envelope, 0, "W")}${this.row("Effektives Inverter-Limit", c.limit, 0, "W")}${this.row("Max. Wechselrichterleistung", c.inverterMax, 0, "W")}
      ${this.meter("Progressive Freigabe", c.release)}${this.row("Progressive γ", c.gamma, 2, "")}`, { icon: "⚙️" });
    const full = this.card("FULL · Absorption", `
      ${this.bar("Gesammelte Absorptionszeit", `${this.f(el, 0)} / ${this.f(req, 0)} min`, req ? (el ?? 0) / req * 100 : 0, req && (el ?? 0) >= req ? "ok" : "acc", { e: c.absorptionElapsed })}
      ${this.row("Verbleibend", c.absorptionRemaining, 0, "min")}${this.rowT("Status", c.absorptionStatus)}${this.rowT("Letzter FULL-Anker", c.anchorSource)}`, { icon: "🔌" });
    const low = this.card("LOW-Kalibrierung & Rückfederung", `
      ${this.rowT("Modus", c.lowMode)}${this.rowT("Status", c.lowStatus)}${this.rowT("Phase", c.lowPhase)}${this.row("Messstufe", c.lowStep, 0, "")}${this.row("Restzeit der Phase", c.lowRemaining, 0, "s")}${this.row("Erfolgreiche Durchläufe", c.lowRuns, 0, "")}
      <div class="sep"></div>
      ${this.row("Gültige Leistungsbereiche", c.reboundBins, 0, "")}${this.row("Prognostizierter Spannungseinbruch", c.reboundSag, 2, "V")}
      <p class="hint">Gezielte LOW-Kalibrierung nur mit bestätigtem FULL-Anker aus demselben Zyklus. Das Rückfederungsmodell ist vorläufig; importierte Messpunkte sind keine erfolgreiche Kapazitätskalibrierung.</p>`, { icon: "🔬" });
    const season = this.card("Saisonlernen", `
      ${this.row("Importierte historische Tage", c.historyDays, 0, "")}${this.row("Erwartung heute", c.seasonalToday, 2, "kWh")}${this.row("Erwartung morgen", c.seasonalTomorrow, 2, "kWh")}${this.meter("Saison-Konfidenz", c.seasonalConf)}
      <p class="hint">Historische Tage sind importierte Datenpunkte, kein Beweis für eine abgeschlossene Lernphase.</p>`, { icon: "📅" });
    return `<div class="cols">${store}${learn}${env}${full}${low}${season}</div>`;
  }

  tabSafety() {
    const c = this.cfg, V = this.num(c.battery), em = this.num(c.emergencySetting), co = this.num(c.cutoffSetting);
    const LO = 20, HI = 29.5, pp = (v) => this.clamp((v - LO) / (HI - LO) * 100);
    const cs = String(this.raw(c.cutoffStatus) ?? ""), okish = cs === "ok" || cs === "paused" || cs === "";
    const ladder = em !== null && co !== null ? `<div class="ladder">
        <div class="lz bad" style="left:0;width:${pp(em)}%"></div><div class="lz warn" style="left:${pp(em)}%;width:${pp(co) - pp(em)}%"></div><div class="lz ok" style="left:${pp(co)}%;width:${100 - pp(co)}%"></div>
        ${V === null ? "" : `<div class="lm" style="left:${pp(V)}%"><b>${this.f(V, 2)} V</b></div>`}
        <div class="lt l" style="left:${pp(em)}%">Notabschaltung<br>${this.f(em, 1)} V</div><div class="lt r" style="left:${pp(co)}%">LOW-Grenze (erholt)<br>${this.f(co, 1)} V</div>
      </div>` : `<p class="hint">Grenzwerte nicht verfügbar.</p>`;
    const status = this.card("Batterieschutz", `
      <div class="state ${okish ? "ok" : cs.startsWith("cutoff") ? "bad" : "warn"}"><b>${okish ? "Alles in Ordnung" : this.esc(this.lab(c.cutoffStatus))}</b><span>${okish ? "Keine Unterspannung, keine Verriegelung." : "Siehe Details unten."}</span></div>
      ${ladder}
      ${this.rowT("Abschaltstatus / Verriegelung", c.cutoffStatus)}${this.row("Gemessene Batteriespannung", c.battery, 2, "V")}${this.rowT("Messqualität", c.measureQuality)}`, { icon: "🛡️", cls: "wide" });
    const limits = this.card("Grenzwerte", `
      ${this.row("LOW-Abschaltgrenze (erholt) – Einstellung", c.cutoffSetting, 1, "V")}${this.row("Tatsächlich konfigurierte LOW-Grenze", c.cutoffActual, 1, "V")}${this.row("Notabschaltung (Klemmenspannung)", c.emergencySetting, 1, "V")}
      <p class="hint">Einstellwerte anklicken, um sie zu ändern.</p>`, { icon: "📏" });
    const how = this.card("So arbeitet der Schutz", `<ul class="how">
      <li><b>Entprellt:</b> Unterspannung löst erst nach mindestens 2 Messungen und 10 s aus. Klemmenspannung weit unter der Notgrenze (−1,0 V) löst sofort aus.</li>
      <li><b>Ungültiger Sensor ≠ 0 V:</b> Fällt die Spannungsmessung aus, pausiert die Regelung; verriegelt wird erst nach 120 s.</li>
      <li><b>Immer aktiv:</b> Die Prüfung läuft in jedem Zyklus zuerst – auch bei pausierter Regelung und veraltetem Netzsensor.</li>
      <li><b>Echte Abschaltung</b> ist nur mit angeschlossenem, korrekt konfiguriertem Inverter-Power-Schalter möglich. Ohne Schalter erscheint eine Benachrichtigung in Home Assistant.</li></ul>`, { icon: "ℹ️" });
    return `<div class="grid">${status}${limits}${how}</div>`;
  }

  tabControl() {
    const c = this.cfg, mode = String(this.raw(c.mode)), chem = String(this.raw(c.chem)), rec = this.raw(c.recorder) === "on", cal = this.raw(c.calibration) === "on";
    const ctrl = this.card("Regelung", `
      <div class="lbl">Modus</div>${this.seg([["off", "Aus"], ["monitor", "Monitor"], ["adaptive", "Adaptiv"], ["predictive", "Prädiktiv"]], mode, "data-m")}
      <div class="lbl">Batteriechemie</div>${this.seg([["lead_acid", "Blei-Säure"], ["lifepo4", "LiFePO₄"]], chem, "data-c")}
      <div class="sep"></div>
      ${this.tog("Flight Recorder", "Protokolliert jeden Zyklus als CSV", c.recorder, rec)}
      ${this.tog("Batterie-Kalibrierung", cal ? "Läuft – Regelung ist eingeschränkt" : "Aus", c.calibration, cal, true)}`, { icon: "🎛️", cls: cal ? "warncard" : "" });
    const fast = this.card("Fast Grid Controller", `
      ${this.row("Netz", c.grid, 0, "W")}${this.row("Zielwert (Helper)", c.target, 0, "W")}${this.row("Empfehlung", c.recommended, 0, "W")}${this.row("Angewendet", c.applied, 0, "W")}${this.row("PV aktuell", c.pv, 0, "W")}
      <div class="sep"></div>${this.rowT("Status", c.state, { ok: "Regelung läuft" })}${this.rowT("Blockiergrund", c.reason)}`, { icon: "⚡" });
    const diag = this.card("Diagnose", `${this.rowT("Letztes Ereignis", c.events)}<div class="row"><span>Recorder-Datei</span><b class="path" title="${this.st(c.flight)}">${this.st(c.flight)}</b></div>`, { icon: "🩺" });
    const csv = this.card("PV-CSV · passives Saisonmodell", `
      <p class="hint top">Home-Assistant-History-CSV des Tageserzeugungs-Sensors. Erst Vorschau, dann bestätigen. Wirkt nicht auf die aktive Regelung.</p>
      <label class="drop"><span id="pv-csv-selected">${this._selectedCsvFile ? "Ausgewählt: " + this.esc(this._selectedCsvFile.name) : "CSV-Datei wählen …"}</span><span id="pv-csv-slot"></span></label>
      <label class="chk"><input type="checkbox" id="pv-csv-replace" ${this._csvReplace ? "checked" : ""}> Vorhandene Tage ersetzen (sonst bleiben sie unverändert)</label>
      <div class="btns"><button id="pv-csv-preview">CSV prüfen</button><button id="pv-csv-commit" class="primary">Import bestätigen</button></div>
      <p id="pv-csv-status" class="hint">${this.esc(this._csvStatus || "Bis zu 3 MB / 1100 Tage. Panel-Konfiguration benötigt entry_id.")}</p>`, { icon: "📁", cls: "wide" });
    return `<div class="cols">${ctrl}${fast}${diag}${csv}</div>`;
  }

  /* ---------- Render ---------- */
  render() {
    if (!this._root || !this._hass) return;
    const c = this.cfg, tabs = [["overview", "Übersicht"], ["planner", "Planer & Prognose"], ["battery", "Batterie & Lernen"], ["safety", "Sicherheit"], ["control", "Steuerung"]];
    if (!tabs.some(([k]) => k === this._tab)) this._tab = "overview";
    const body = { overview: () => this.tabOverview(), planner: () => this.tabPlanner(), battery: () => this.tabBattery(), safety: () => this.tabSafety(), control: () => this.tabControl() }[this._tab]();
    const cs = String(this.raw(c.cutoffStatus) ?? ""), alarm = cs.startsWith("cutoff_") || cs.startsWith("trip"), pend = cs.endsWith("_pending");
    const html = `<style>${this.css()}</style><div class="w">
      <header class="hero">
        <img class="logo" src="/asc_static/asc-icon.png" alt="">
        <div class="ht"><h1>Adaptive Solar Controller</h1><div class="sub">v0.4.6 RC4 · Estimator → Strategy Learner → Energy Planner → Fast Controller</div></div>
        <button class="back" type="button">← Solar</button>
      </header>
      <div class="pills">
        <span class="pill ${this.raw(c.state) === "ok" ? "ok" : "mute"}" title="${this.st(c.state)}"><i></i>${this.esc(this.lab(c.state, { ok: "Regelung läuft" }))}</span>
        <span class="pill acc">Modus <b>${this.esc(this.lab(c.mode))}</b></span>
        <span class="pill acc">${this.esc(this.lab(c.chem))}</span>
        <span class="pill ${alarm ? "bad" : pend ? "warn" : "ok"}">🛡️ ${alarm || pend ? this.esc(this.lab(c.cutoffStatus)) : "Schutz bereit"}</span>
        <span class="pill mute">Letzte Vollladung vor <b>${this.val(c.daysFull, 1, "")}</b> Tagen</span>
      </div>
      <p class="now">${this.narrative()}</p>
      ${this.alerts()}
      <nav class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" aria-selected="${this._tab === k}" class="${this._tab === k ? "active" : ""}" data-tab="${k}">${l}</button>`).join("")}</nav>
      <main role="tabpanel">${body}</main>
      <footer class="foot">ASC v0.4.6 RC4 · Adaptive Energy Strategy · Darkwulf183 &amp; ChatGPT</footer></div>`;
    this._apply(html);
    // Persistente Dateiauswahl: dasselbe <input> wird bei jedem Neuzeichnen wieder eingesetzt.
    if (!this._fileInput) {
      const fi = document.createElement("input"); fi.type = "file"; fi.id = "pv-csv-file"; fi.accept = ".csv,text/csv"; fi.style.display = "none";
      fi.onchange = (e) => {
        this._selectedCsvFile = e.target.files?.[0] || null;
        const sel = this._root.querySelector("#pv-csv-selected");
        if (sel) sel.textContent = this._selectedCsvFile ? "Ausgewählt: " + this._selectedCsvFile.name : "CSV-Datei wählen …";
      };
      this._fileInput = fi;
    }
    const slot = this._root.querySelector("#pv-csv-slot"); if (slot) slot.replaceWith(this._fileInput);
  }

  /* ---------- In-Place-Update ----------
   * Statt das ganze Panel per innerHTML neu aufzubauen (Scroll-Sprung am Handy, Flackern, neu startende
   * Animationen, verlorener Fokus), wird das neue Markup mit dem vorhandenen DOM abgeglichen und nur
   * Geändertes angefasst. Gleiche Knoten bleiben bestehen.
   */
  _scrollState() {
    const out = [];
    let n = this;
    while (n) {
      if (n.scrollTop > 0) out.push([n, n.scrollTop]);
      n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
    }
    const se = document.scrollingElement;
    if (se && se.scrollTop > 0 && !out.some(([e]) => e === se)) out.push([se, se.scrollTop]);
    return out;
  }
  _apply(html) {
    if (!this._root.firstChild) { this._root.innerHTML = html; return; }
    const saved = this._tabChanged ? [] : this._scrollState();
    this._tabChanged = false;
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    this._patch(this._root, tpl.content);
    // Sicherheitsnetz: falls ein Browser trotzdem scrollt, alte Position wiederherstellen.
    for (const [el, top] of saved) if (Math.abs(el.scrollTop - top) > 1) el.scrollTop = top;
  }
  _syncAttrs(live, next) {
    for (const a of Array.from(live.attributes)) if (!next.hasAttribute(a.name)) live.removeAttribute(a.name);
    for (const a of Array.from(next.attributes)) if (live.getAttribute(a.name) !== a.value) live.setAttribute(a.name, a.value);
    if (live.nodeName === "INPUT" && live.type === "checkbox") live.checked = next.checked;
  }
  _patch(live, next) {
    const L = Array.from(live.childNodes), N = Array.from(next.childNodes), len = Math.max(L.length, N.length);
    for (let i = 0; i < len; i++) {
      const l = L[i], x = N[i];
      if (!x) { live.removeChild(l); continue; }
      if (!l) { live.appendChild(x); continue; }
      // Die Dateiauswahl-<input> bleibt dauerhaft an der Stelle des Platzhalters.
      if (l === this._fileInput && x.id === "pv-csv-slot") continue;
      if (l.nodeType !== x.nodeType || l.nodeName !== x.nodeName) { live.replaceChild(x, l); continue; }
      if (l.nodeType === 3 || l.nodeType === 8) { if (l.nodeValue !== x.nodeValue) l.nodeValue = x.nodeValue; continue; }
      this._syncAttrs(l, x);
      if (l.nodeName === "STYLE") { if (l.textContent !== x.textContent) l.textContent = x.textContent; continue; }
      this._patch(l, x);
    }
  }

  _onClick(e) {
    const t = e.target.closest("[data-e],[data-m],[data-c],[data-t],[data-tab],.back,#pv-csv-preview,#pv-csv-commit");
    if (!t) return;
    if (t.dataset.tab) { this._tab = t.dataset.tab; this._tabChanged = true; this._sig = null; this.render(); }
    else if (t.dataset.m) this.mode(t.dataset.m);
    else if (t.dataset.c) this.chem(t.dataset.c);
    else if (t.dataset.t) this.toggle(t.dataset.t);
    else if (t.classList.contains("back")) window.location.href = "/dashboard-solar/solar";
    else if (t.id === "pv-csv-preview") this.csvImport(false);
    else if (t.id === "pv-csv-commit") this.csvImport(true);
    else if (t.dataset.e) this.info(t.dataset.e);
  }
  _onChange(e) { if (e.target?.id === "pv-csv-replace") this._csvReplace = e.target.checked; }

  async csvImport(commit = false) {
    const replace = !!this._csvReplace;
    const setS = (t) => { this._csvStatus = t; const n = this._root.querySelector("#pv-csv-status"); if (n) n.textContent = t; };
    const file = this._selectedCsvFile || this._fileInput?.files?.[0];
    if (!file) { setS("Bitte CSV wählen"); return; }
    if (file.size > 3000000) { setS("Maximal 3 MB"); return; }
    try {
      setS("CSV wird geprüft …");
      const csv = await file.text();
      const entry_id = this._panel?.config?.entry_id || this._panel?.config?.entryId || "";
      if (!entry_id) { setS("ASC entry_id fehlt in der Panel-Konfiguration. Bitte in panel_custom setzen."); return; }
      const result = await this._hass.callWS({ type: "adaptive_solar_controller/pv_csv", entry_id, csv, commit, replace });
      this._csvResult = result;
      setS(`${commit ? "Import gespeichert" : "Vorschau"}: ${result.parsed_days} CSV-Tage, ${result.added_days} neu, ${result.replaced_days || 0} ersetzt, ${result.duplicates} unverändert, ${result.days} insgesamt; Kalenderjahre komplett: ${(result.full_calendar_years || []).join(", ") || "keines"}; theoretischer Einfluss ${(result.theoretical_weight * 100).toFixed(1)} %, aktiv 0 %.`);
    } catch (e) { setS("CSV-Fehler: " + (e.message || String(e))); }
  }

  css() { return `
:host{display:block;min-height:100vh;box-sizing:border-box;padding:20px 20px 28px;color:var(--primary-text-color);background:var(--primary-background-color);
  --ok:var(--success-color,#2fa866);--warn:var(--warning-color,#f0a30a);--bad:var(--error-color,#e5484d);--acc:var(--primary-color,#03a9f4);--mute:var(--secondary-text-color,#8a94a6);
  --line:var(--divider-color,rgba(127,127,127,.25));--soft:var(--secondary-background-color,rgba(127,127,127,.12));--card:var(--card-background-color,#fff);font-family:var(--paper-font-body1_-_font-family,Roboto,system-ui,sans-serif)}
*{box-sizing:border-box}.w{max-width:1320px;margin:0 auto}
h1{font-size:26px;line-height:1.15;margin:0;font-weight:600}h2{font-size:15px;margin:0 0 12px;font-weight:600;display:flex;align-items:center;gap:8px}h3{font-size:14px;margin:0;font-weight:600}
.ic{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:8px;background:var(--soft);font-size:14px}
.hero{display:flex;align-items:center;gap:16px;padding:16px 18px;border-radius:20px;border:1px solid var(--line);background:linear-gradient(135deg,color-mix(in srgb,var(--acc) 16%,var(--card)),var(--card) 70%);box-shadow:var(--ha-card-box-shadow,none)}
.logo{width:60px;height:60px;border-radius:16px;flex:none;object-fit:contain;background:#fff;padding:3px;box-shadow:0 2px 8px rgba(0,0,0,.25)}.ht{flex:1;min-width:0}.sub{color:var(--mute);font-size:13px;margin-top:4px}
.back{border:1px solid var(--line);background:var(--card);color:var(--primary-text-color);border-radius:999px;padding:8px 14px;cursor:pointer;font:inherit;font-size:13px}.back:hover{border-color:var(--acc)}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;font-size:13px;border:1px solid var(--line);background:var(--card)}
.pill i{width:8px;height:8px;border-radius:50%;background:currentColor}.pill.ok{color:var(--ok)}.pill.bad{color:var(--bad);border-color:var(--bad)}.pill.warn{color:var(--warn);border-color:var(--warn)}.pill.acc{color:var(--primary-text-color)}.pill.mute{color:var(--mute)}
.pill b{color:var(--primary-text-color);font-weight:600}.pill.ok,.pill.bad{font-weight:500}
.now{margin:10px 2px 14px;font-size:15px;line-height:1.5;color:var(--primary-text-color)}.now b{font-weight:600}
.alert{display:flex;flex-direction:column;gap:2px;padding:12px 16px;border-radius:14px;margin:0 0 10px;border:1px solid;font-size:14px}
.alert.bad{background:color-mix(in srgb,var(--bad) 14%,var(--card));border-color:var(--bad)}.alert.warn{background:color-mix(in srgb,var(--warn) 14%,var(--card));border-color:var(--warn)}.alert.info{background:color-mix(in srgb,var(--acc) 10%,var(--card));border-color:var(--acc)}
.tabs{display:flex;gap:6px;overflow-x:auto;margin:6px 0 16px;padding:4px;border-radius:14px;background:var(--soft);scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:1 0 auto;border:0;background:transparent;color:var(--mute);padding:10px 16px;border-radius:10px;cursor:pointer;font:inherit;font-size:14px;white-space:nowrap}
.tabs button.active{background:var(--card);color:var(--primary-text-color);font-weight:600;box-shadow:0 1px 4px rgba(0,0,0,.18)}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px;box-shadow:var(--ha-card-box-shadow,none);min-width:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;align-items:start}.wide{grid-column:span 2}
.cols{column-width:320px;column-gap:14px}.cols>.card{break-inside:avoid;-webkit-column-break-inside:avoid;margin:0 0 14px}
.click{cursor:pointer}.click:hover{opacity:.82}
.row{display:flex;justify-content:space-between;gap:14px;padding:8px 2px;border-bottom:1px solid var(--line);font-size:14px}.row:last-child{border-bottom:0}
.row span{color:var(--mute)}.row b{font-weight:600;text-align:right;min-width:0;overflow-wrap:anywhere}.path{font-size:12px;font-weight:500}
.sep{height:10px}.hint{color:var(--mute);font-size:12.5px;line-height:1.5;margin:10px 0 0}.hint.top{margin:-4px 0 12px}.lbl{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin:12px 0 6px}
.pos{color:var(--ok)}.neg{color:var(--bad)}
.flow{display:grid;grid-template-columns:1fr 36px 1fr 36px 1fr 36px 1fr;align-items:stretch;gap:0;margin:0 0 14px}
.node{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px 10px;text-align:center;display:flex;flex-direction:column;gap:2px;align-items:center;box-shadow:var(--ha-card-box-shadow,none)}
.node .ni{font-size:26px;line-height:1}.node .nl{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-top:4px}.node b{font-size:22px;font-weight:600}.node small{color:var(--mute);font-size:12px}
.node.ok{border-color:color-mix(in srgb,var(--ok) 60%,var(--line))}.node.warn{border-color:color-mix(in srgb,var(--warn) 70%,var(--line))}.node.acc{border-color:color-mix(in srgb,var(--acc) 45%,var(--line))}
.arrow{position:relative;align-self:center;height:4px;margin:0 4px;border-radius:2px;background:var(--line);overflow:hidden}
.arrow.on{background:color-mix(in srgb,var(--acc) 30%,transparent)}.arrow.on i{position:absolute;inset:0;background:linear-gradient(90deg,transparent,var(--acc),transparent);width:60%;animation:fl 1.6s linear infinite}
@keyframes fl{from{transform:translateX(-100%)}to{transform:translateX(180%)}}@media(prefers-reduced-motion:reduce){.arrow.on i{animation:none;width:100%;opacity:.6}}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}.kpi{display:flex;flex-direction:column;align-items:center;text-align:center;padding:16px 12px}
.ksub{margin:10px 0 0;color:var(--mute);font-size:12.5px;line-height:1.5}.kl{color:var(--mute);font-size:13px;margin-top:6px}
.ring{display:flex;flex-direction:column;align-items:center;gap:6px}.ring>span{color:var(--mute);font-size:13px}.rwrap{position:relative;width:112px;height:112px}
.rwrap svg{width:100%;height:100%;transform:rotate(-90deg)}.rb,.rf{fill:none;stroke-width:3.4}.rb{stroke:var(--soft)}.rf{stroke-linecap:round;transition:stroke-dasharray .6s}
.rf.ok{stroke:var(--ok)}.rf.acc{stroke:var(--acc)}.rf.warn{stroke:var(--warn)}.rf.mute{stroke:var(--mute)}
.rc{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}.rc b{font-size:26px;font-weight:600;line-height:1}.rc small{color:var(--mute);font-size:12px;margin-top:2px}
.big{font-size:40px;font-weight:600;line-height:1.1;display:flex;align-items:baseline;gap:6px;justify-content:center;margin:22px 0 4px}.big small{font-size:14px;color:var(--mute);font-weight:400}
.hero2{display:flex;align-items:center;gap:16px;margin-bottom:12px}.hero2 .big{margin:0;justify-content:flex-start;flex-direction:column;align-items:flex-start;gap:0;font-size:34px}
.hero2t{display:flex;flex-direction:column;gap:3px}.hero2t span{color:var(--mute);font-size:13px}
.meter{padding:7px 0}.mh{display:flex;justify-content:space-between;font-size:14px;margin-bottom:6px;gap:10px}.mh span{color:var(--mute)}.mh b{font-weight:600}
.track{position:relative;height:9px;border-radius:99px;background:var(--soft);overflow:visible}.fill{height:100%;border-radius:99px;transition:width .6s;min-width:2px}
.fill.ok{background:var(--ok)}.fill.acc{background:var(--acc)}.fill.warn{background:var(--warn)}.fill.mute{background:var(--mute);opacity:.55}
.mark{position:absolute;top:-4px;width:3px;height:17px;border-radius:2px;background:var(--primary-text-color);transform:translateX(-50%)}.msub{color:var(--mute);font-size:12px;margin-top:5px}
.horizon{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.hbox{display:flex;flex-direction:column;align-items:center;gap:2px;padding:14px 6px;border-radius:14px;background:var(--soft)}
.hbox small{color:var(--mute)}.hbox b{font-size:22px;font-weight:600}.hbox em{font-style:normal;color:var(--mute);font-size:12px}.hbox.pos b{color:var(--ok)}.hbox.neg b{color:var(--bad)}
.charts{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.chart{padding:14px 16px}.ch{display:flex;justify-content:space-between;align-items:baseline;gap:10px}.ch small{color:var(--mute);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0 8px;font-size:13px;color:var(--mute)}.lg{display:inline-flex;align-items:center;gap:6px}.lg i{width:10px;height:10px;border-radius:3px}.lg b{color:var(--primary-text-color);font-weight:600}
.chart svg{width:100%;height:110px;display:block}.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}.ar{opacity:.14}.zl{stroke:var(--mute);stroke-dasharray:3 3;opacity:.6;vector-effect:non-scaling-stroke}
.axis{display:flex;justify-content:space-between;color:var(--mute);font-size:11px;margin-top:4px}.empty{color:var(--mute);font-size:13px;padding:34px 0;text-align:center}
.state{display:flex;flex-direction:column;gap:2px;padding:12px 14px;border-radius:14px;margin-bottom:6px;border:1px solid}
.state.ok{background:color-mix(in srgb,var(--ok) 12%,var(--card));border-color:color-mix(in srgb,var(--ok) 55%,var(--line))}.state.warn{background:color-mix(in srgb,var(--warn) 14%,var(--card));border-color:var(--warn)}.state.bad{background:color-mix(in srgb,var(--bad) 14%,var(--card));border-color:var(--bad)}
.state span{color:var(--mute);font-size:13px}
.ladder{position:relative;height:10px;margin:44px 8px 58px;border-radius:99px}.lz{position:absolute;top:0;height:100%}.lz.bad{background:var(--bad);border-radius:99px 0 0 99px}.lz.warn{background:var(--warn)}.lz.ok{background:var(--ok);border-radius:0 99px 99px 0}
.lm{position:absolute;top:-8px;width:0;height:26px;border-left:3px solid var(--primary-text-color)}.lm b{position:absolute;top:-24px;left:0;transform:translateX(-50%);font-size:14px;white-space:nowrap;background:var(--card);padding:0 6px;border-radius:6px}
.lt{position:absolute;top:20px;font-size:11.5px;line-height:1.35;color:var(--mute);white-space:nowrap;padding:0 4px;border-top:2px solid var(--line)}.lt.l{transform:translateX(-100%);text-align:right}.lt.r{text-align:left}
.how{margin:0;padding-left:18px;font-size:13.5px;line-height:1.55;color:var(--mute)}.how li{margin-bottom:8px}.how b{color:var(--primary-text-color)}
.seg{display:flex;gap:4px;padding:4px;border-radius:12px;background:var(--soft);flex-wrap:wrap}.seg button{flex:1;border:0;background:transparent;color:var(--primary-text-color);padding:9px 10px;border-radius:9px;cursor:pointer;font:inherit;font-size:14px}.seg button.active{background:var(--acc);color:#fff;font-weight:600}
.tog{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;margin-top:8px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:transparent;color:var(--primary-text-color);cursor:pointer;font:inherit;text-align:left}
.tog span{display:flex;flex-direction:column;gap:2px;font-size:14px;font-weight:500}.tog small{color:var(--mute);font-size:12px;font-weight:400}
.sw{flex:none;width:42px;height:24px;border-radius:99px;background:var(--soft);border:1px solid var(--line);position:relative;transition:.2s}.sw:after{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:var(--mute);transition:.2s}
.tog.on .sw{background:var(--ok);border-color:var(--ok)}.tog.on .sw:after{left:20px;background:#fff}.tog.warnon .sw{background:var(--warn);border-color:var(--warn)}.warncard{border-color:var(--warn)}
.drop{display:flex;align-items:center;justify-content:center;gap:8px;padding:18px;border:1.5px dashed var(--line);border-radius:14px;color:var(--mute);cursor:pointer;font-size:14px;text-align:center;overflow-wrap:anywhere}.drop:hover{border-color:var(--acc);color:var(--primary-text-color)}
.chk{display:flex;gap:8px;align-items:center;margin:12px 0;font-size:13px;color:var(--mute)}.btns{display:flex;gap:8px;flex-wrap:wrap}
.btns button{border:1px solid var(--line);background:var(--soft);color:var(--primary-text-color);border-radius:10px;padding:10px 16px;cursor:pointer;font:inherit;font-size:14px}.btns button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
.foot{text-align:center;margin:22px 0 0;color:var(--mute);font-size:12px}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(2,1fr)}.charts{grid-template-columns:1fr}.wide{grid-column:auto}}
@media(max-width:700px){:host{padding:10px 10px 22px}h1{font-size:20px}.sub{display:none}.logo{width:46px;height:46px}.hero{padding:12px}.grid{grid-template-columns:1fr}
  .flow{grid-template-columns:1fr 1fr;gap:10px}.arrow{display:none}.node b{font-size:19px}.rwrap{width:96px;height:96px}.big{font-size:32px}}
`; }
}
customElements.define("adaptive-solar-controller-panel", AdaptiveSolarControllerPanel);
