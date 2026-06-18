/* ============================================================
   India Climate Anomaly Atlas — Frontend Logic
   Variable-aware: rainfall · tmax · tmin
   ============================================================ */

(() => {
  "use strict";

  // ===========================================================
  // VARIABLE CONFIG — single source of truth for per-variable
  // labels, data paths, category palettes, and field mappings.
  // ===========================================================

  const RAINFALL_CATS = [
    { key: "Excess",    color: "#60b1f4", range: ">+20%"        },
    { key: "Normal",    color: "#6ae944", range: "-19% to +20%" },
    { key: "Deficient", color: "#dd7534", range: "-20% to -59%" },
    { key: "Scanty",    color: "#ffe23a", range: "-60% to -99%" },
    { key: "No Rain",   color: "#969696", range: "≤ -99%"       },
    { key: "No Data",   color: "#2a3441", range: "—"            },
  ];

  // 12-bin temperature palette mirrors the notebook's PALETTE (cold → warm).
  const TEMP_CATS = [
    { key: "< -5",     color: "#004da8", range: "< -5 °C"       },
    { key: "-5 to -4", color: "#0536fe", range: "-5 to -4 °C"   },
    { key: "-4 to -3", color: "#618cd3", range: "-4 to -3 °C"   },
    { key: "-3 to -2", color: "#0a8500", range: "-3 to -2 °C"   },
    { key: "-2 to -1", color: "#17dd05", range: "-2 to -1 °C"   },
    { key: "-1 to 0",  color: "#b8edae", range: "-1 to 0 °C"    },
    { key: "0 to 1",   color: "#f6f69c", range: "0 to +1 °C"    },
    { key: "1 to 2",   color: "#f9f904", range: "+1 to +2 °C"   },
    { key: "2 to 3",   color: "#f7ad00", range: "+2 to +3 °C"   },
    { key: "3 to 4",   color: "#ff9b9b", range: "+3 to +4 °C"   },
    { key: "4 to 5",   color: "#ff0000", range: "+4 to +5 °C"   },
    { key: "> 5",      color: "#600700", range: "> +5 °C"       },
    { key: "No Data",  color: "#2a3441", range: "—"             },
  ];

  const TEMP_SURPLUS = new Set(["0 to 1", "1 to 2", "2 to 3", "3 to 4", "4 to 5", "> 5"]);
  const TEMP_DEFICIT = new Set(["< -5", "-5 to -4", "-4 to -3", "-3 to -2", "-2 to -1", "-1 to 0"]);

  const VARIABLES = {
    rainfall: {
      id: "rainfall",
      dataBase: "./data/rainfall",
      categories: RAINFALL_CATS,
      fields: {
        actual:   "actual",
        normal:   "normal",
        measure:  "deviation",
        category: "category",
      },
      units:        { actual: "mm", normal: "mm", measure: "%" },
      measureLabel: "Deviation",
      formatMeasure: v => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(1) + "%"),
      formatActualMm: v => v == null ? "—" : Number(v).toFixed(1) + " mm",
      formatNormalMm: v => v == null ? "—" : Number(v).toFixed(1) + " mm",
      surplusKeys:  new Set(["Excess"]),
      deficitKeys:  new Set(["Deficient", "Scanty", "No Rain"]),
      hero: {
        surplusLabel: "Surplus",
        surplusUnit:  "excess districts",
        deficitLabel: "Deficit",
        deficitUnit:  "deficient + scanty + no-rain",
      },
      surplusColor: "#60b1f4",
      deficitColor: "#dd7534",
      legendTitle:  "Rainfall Departure Classes",
      normalNote:   "Normal Rainfall Considered from 1961-2010",
      yAxisUnit:    "mm",
    },

    tmax: {
      id: "tmax",
      dataBase: "./data/temperature",
      categories: TEMP_CATS,
      fields: {
        actual:   "tmax_actual",
        normal:   "tmax_normal",
        measure:  "tmax_anomaly",
        category: "tmax_category",
      },
      units:        { actual: "°C", normal: "°C", measure: "°C" },
      measureLabel: "Anomaly",
      formatMeasure:  v => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "°C"),
      formatActualMm: v => v == null ? "—" : Number(v).toFixed(1) + " °C",
      formatNormalMm: v => v == null ? "—" : Number(v).toFixed(1) + " °C",
      surplusKeys: TEMP_SURPLUS,
      deficitKeys: TEMP_DEFICIT,
      hero: {
        surplusLabel: "Warmer",
        surplusUnit:  "districts above normal",
        deficitLabel: "Cooler",
        deficitUnit:  "districts below normal",
      },
      surplusColor: "#ff0000",
      deficitColor: "#0536fe",
      legendTitle:  "Max-Temp Anomaly Classes",
      normalNote:   "Anomaly w.r.t Average of 2016-2024",
      yAxisUnit:    "°C",
    },

    tmin: {
      id: "tmin",
      dataBase: "./data/temperature",
      categories: TEMP_CATS,
      fields: {
        actual:   "tmin_actual",
        normal:   "tmin_normal",
        measure:  "tmin_anomaly",
        category: "tmin_category",
      },
      units:        { actual: "°C", normal: "°C", measure: "°C" },
      measureLabel: "Anomaly",
      formatMeasure:  v => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(2) + "°C"),
      formatActualMm: v => v == null ? "—" : Number(v).toFixed(1) + " °C",
      formatNormalMm: v => v == null ? "—" : Number(v).toFixed(1) + " °C",
      surplusKeys: TEMP_SURPLUS,
      deficitKeys: TEMP_DEFICIT,
      hero: {
        surplusLabel: "Warmer",
        surplusUnit:  "districts above normal",
        deficitLabel: "Cooler",
        deficitUnit:  "districts below normal",
      },
      surplusColor: "#ff0000",
      deficitColor: "#0536fe",
      legendTitle:  "Min-Temp Anomaly Classes",
      normalNote:   "Anomaly w.r.t Average of 2016-2024",
      yAxisUnit:    "°C",
    },
  }

  const DISTRICT_KEY = "dtname";
  const STATE_KEY    = "stname";

  const MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
  ];

  // Curated state-capital / major-metro districts (mid-zoom label tier).
  const IMPORTANT_DISTRICTS_LC = new Set([
    "bangalore urban", "bengaluru urban", "bengaluru",
    "mumbai city", "mumbai suburban", "mumbai",
    "chennai", "kolkata", "hyderabad",
    "lucknow", "jaipur", "bhopal", "patna",
    "thiruvananthapuram", "tiruvananthapuram",
    "ahmedabad", "pune", "surat",
    "kanpur nagar", "kanpur",
    "nagpur", "indore", "vadodara",
    "visakhapatnam", "coimbatore",
    "agra", "varanasi", "meerut", "ludhiana", "amritsar",
    "faridabad", "gurgaon", "gurugram",
    "ranchi", "raipur",
    "bhubaneswar", "khordha", "khurda", "cuttack",
    "dehradun", "srinagar", "shimla", "gandhinagar",
    "imphal", "imphal west", "aizawl", "kohima",
    "itanagar", "papum pare", "gangtok", "east sikkim",
    "shillong", "east khasi hills", "agartala", "west tripura",
    "panaji", "north goa",
    "kamrup metropolitan",
    "jammu", "chandigarh",
    "new delhi", "central delhi", "south delhi", "north delhi",
    "east delhi", "west delhi", "north east delhi", "south west delhi",
    "rajkot", "nashik", "aurangabad",
    "madurai", "mysuru", "mysore",
    "tiruchirappalli", "salem", "vellore",
    "mangaluru", "mangalore", "thane", "kolhapur",
    "puducherry", "pondicherry",
  ]);

  // ===========================================================
  // STATE
  // ===========================================================

  const state = {
    currentVar: "rainfall",
    // Per-data-source caches (rainfall and temperature share data/temperature/ for tmax/tmin)
    sources: {},      // dataBase URL -> { manifest, weeksByKey, weekCache, timeseries, timeseriesPromise }

    currentWeekKey: null,
    currentWeekData: null,

    selectedDistrict: null,
    selectedLayer: null,

    districtToState: {},
    stateToDistricts: {},
    districtLayer: new Map(),

    geojsonLayer: null,
    map: null,
    trendChart: null,

    stateLabels: [], // deprecated — state name overlays removed for map clarity
    districtLabels: new Map(),
    selectedLabel: null,
    labelFrame: null,
  };

  function v() { return VARIABLES[state.currentVar]; }
  function src() { return state.sources[v().dataBase]; }

  // ===========================================================
  // Utility helpers
  // ===========================================================

  const $  = sel => document.querySelector(sel);

  const fmtDate = iso => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };

  async function fetchJSON(path) {
    if (typeof EMBEDDED_DATA !== "undefined") {
      if (path.includes("districts.geojson")) {
        return EMBEDDED_DATA.districtsGeojson;
      }
      if (path.includes("rainfall/manifest.json")) {
        return EMBEDDED_DATA.rainfall.manifest;
      }
      if (path.includes("temperature/manifest.json")) {
        return EMBEDDED_DATA.temperature.manifest;
      }
      if (path.includes("rainfall/timeseries.json")) {
        return EMBEDDED_DATA.rainfall.timeseries;
      }
      if (path.includes("temperature/timeseries.json")) {
        return EMBEDDED_DATA.temperature.timeseries;
      }
      const rainWeekMatch = path.match(/rainfall\/weeks\/(.+)\.json/);
      if (rainWeekMatch) {
        return EMBEDDED_DATA.rainfall.weeks[rainWeekMatch[1]];
      }
      const tempWeekMatch = path.match(/temperature\/weeks\/(.+)\.json/);
      if (tempWeekMatch) {
        return EMBEDDED_DATA.temperature.weeks[tempWeekMatch[1]];
      }
    }
    const res = await fetch(path);
    if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
    return res.json();
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  // ===========================================================
  // BOOT
  // ===========================================================

  async function init() {
    try {
      // Boot the rainfall data source by default; temperature is loaded on tab switch.
      await loadSource(v().dataBase);
      const m = src().manifest;
      if (!m.weeks?.length) {
        throw new Error("Manifest has no weeks. Run the pipeline first.");
      }

      buildLegend();
      populateTimeSelectors();

      const latest = m.weeks[m.weeks.length - 1];
      setTimeSelectorValues(latest);
      $("#metaCurrentWeek").textContent =
        `${MONTH_NAMES[latest.month-1].slice(0,3)} ${latest.year} · W${latest.week}`;

      initMap();
      wireTabs();
      applyVariableLabels();

      const districts = await fetchJSON(`./data/districts.geojson`);
      buildLocationIndex(districts);
      populateLocationSelectors();
      renderDistricts(districts);

      await loadWeek(latest.key);
      applyWeekToMap();
      updateSummary();
      updateHeroStats();
      updateDateRange();

      hideLoading();
    } catch (err) {
      console.error(err);
      $(".loader-text").textContent = "Failed to load: " + err.message;
    }
  }

  // ===========================================================
  // Sources (manifest + week cache + timeseries) per dataBase URL
  // ===========================================================

  async function loadSource(base) {
    if (state.sources[base]?.manifest) return state.sources[base];

    const manifest = await fetchJSON(`${base}/manifest.json`);
    const weeksByKey = new Map(manifest.weeks.map(w => [w.key, w]));
    state.sources[base] = {
      manifest,
      weeksByKey,
      weekCache: new Map(),
      timeseries: null,
      timeseriesPromise: null,
    };
    return state.sources[base];
  }

  async function loadWeek(key) {
    const s = src();
    if (s.weekCache.has(key)) {
      state.currentWeekKey = key;
      state.currentWeekData = s.weekCache.get(key);
      return state.currentWeekData;
    }
    const data = await fetchJSON(`${v().dataBase}/weeks/${key}.json`);
    s.weekCache.set(key, data);
    state.currentWeekKey = key;
    state.currentWeekData = data;
    return data;
  }

  function getTimeseries() {
    const s = src();
    if (s.timeseries) return Promise.resolve(s.timeseries);
    if (s.timeseriesPromise) return s.timeseriesPromise;
    s.timeseriesPromise = fetchJSON(`${v().dataBase}/timeseries.json`)
      .then(ts => { s.timeseries = ts; return ts; });
    return s.timeseriesPromise;
  }

  // ===========================================================
  // Tab switching
  // ===========================================================

  function wireTabs() {
    document.querySelectorAll(".mtab").forEach(btn => {
      btn.addEventListener("click", () => switchVariable(btn.dataset.var));
    });
  }

  async function switchVariable(newVarId) {
    if (!VARIABLES[newVarId] || newVarId === state.currentVar) return;
    const previousKey = state.currentWeekKey;
    state.currentVar = newVarId;

    // Update tab visuals
    document.querySelectorAll(".mtab").forEach(btn => {
      btn.classList.toggle("is-active", btn.dataset.var === newVarId);
      btn.setAttribute("aria-selected", btn.dataset.var === newVarId ? "true" : "false");
    });

    try {
      await loadSource(v().dataBase);
      applyVariableLabels();
      populateTimeSelectors();          // rebuild from new manifest
      buildLegend();

      // Try to keep the same week if it exists; otherwise snap to latest.
      const m = src().manifest;
      const target = src().weeksByKey?.has?.(previousKey)
        ? src().weeksByKey.get(previousKey)
        : (m.weeks.find(w => w.key === previousKey)
           || m.weeks[m.weeks.length - 1]);
      setTimeSelectorValues(target);

      await loadWeek(target.key);
      applyWeekToMap();
      updateSummary();
      updateHeroStats();
      updateDateRange();

      if (state.selectedDistrict) {
        updateDetail(state.selectedDistrict);
        // Always redraw the chart on tab switch — even if the timeseries
        // fetch fails, draw an empty chart with the NEW variable's axes
        // so the Y-axis unit and color set match the active tab.
        let series = [];
        try {
          const ts = await getTimeseries();
          series = ts[state.selectedDistrict] || [];
        } catch (tsErr) {
          console.error("timeseries fetch failed for", v().id, tsErr);
        }
        drawTrendChart(state.selectedDistrict, series);
      }
    } catch (err) {
      console.error("Variable switch failed:", err);
    }
  }

  // ===========================================================
  // Variable-driven labels (applied on init + tab switch)
  // ===========================================================

  function applyVariableLabels() {
    const V = v();
    const cat = V.categories;
    // Hero
    $("#heroSurplusLabel").textContent = V.hero.surplusLabel;
    $("#heroSurplusUnit").textContent  = V.hero.surplusUnit;
    $("#heroDeficitLabel").textContent = V.hero.deficitLabel;
    $("#heroDeficitUnit").textContent  = V.hero.deficitUnit;

    // Map hint dots
    $("#hintSurplusDot").style.background = V.surplusColor;
    $("#hintDeficitDot").style.background = V.deficitColor;
    $("#hintSurplusLbl").textContent = V.hero.surplusLabel;
    $("#hintDeficitLbl").textContent = V.hero.deficitLabel;

    // Metric tile labels & units
    $("#metActualUnit").textContent  = V.units.actual;
    $("#metNormalUnit").textContent  = V.units.normal;
    $("#metMeasureLabel").textContent = V.measureLabel;
    $("#metMeasureUnit").textContent = V.units.measure;

    // Legend title + normal-period note
    $("#legendTitle").textContent = V.legendTitle;
    const noteEl = $("#normalNote");
    if (noteEl) noteEl.textContent = V.normalNote || "";
  }

  // ===========================================================
  // Geometry / selectors / map
  // (same logic as before, now reads through v() and fields)
  // ===========================================================

  function buildLocationIndex(geojson) {
    state.districtToState = {};
    state.stateToDistricts = {};
    geojson.features.forEach(f => {
      const dt = f.properties[DISTRICT_KEY];
      const st = f.properties[STATE_KEY] || "—";
      state.districtToState[dt] = st;
      if (!state.stateToDistricts[st]) state.stateToDistricts[st] = [];
      state.stateToDistricts[st].push(dt);
    });
    Object.keys(state.stateToDistricts).forEach(st => {
      state.stateToDistricts[st].sort((a, b) => a.localeCompare(b));
    });
  }

  // -- Time selectors --
  function populateTimeSelectors() {
    const m = src().manifest;
    const years = [...new Set(m.weeks.map(w => w.year))].sort((a,b)=>a-b);
    const yearSel = $("#yearSelect");
    const prev = Number(yearSel.value);
    yearSel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join("");
    if (years.includes(prev)) yearSel.value = String(prev);

    // Avoid re-binding listeners on rebuild — add once.
    if (!yearSel._wired) {
      yearSel.addEventListener("change", () => onTimeChange("year"));
      $("#monthSelect").addEventListener("change", () => onTimeChange("month"));
      $("#weekSelect").addEventListener("change", () => onTimeChange("week"));
      yearSel._wired = true;
    }

    refreshMonthOptions();
    refreshWeekOptions();
  }

  function refreshMonthOptions() {
    const year = Number($("#yearSelect").value);
    const months = [...new Set(src().manifest.weeks
      .filter(w => w.year === year).map(w => w.month))].sort((a,b)=>a-b);
    const sel = $("#monthSelect");
    const prev = Number(sel.value);
    sel.innerHTML = months
      .map(m => `<option value="${m}">${MONTH_NAMES[m-1]}</option>`).join("");
    if (months.includes(prev)) sel.value = String(prev);
  }

  function refreshWeekOptions() {
    const year  = Number($("#yearSelect").value);
    const month = Number($("#monthSelect").value);
    const weeks = src().manifest.weeks
      .filter(w => w.year === year && w.month === month)
      .map(w => w.week).sort((a,b)=>a-b);
    const sel = $("#weekSelect");
    const prev = Number(sel.value);
    sel.innerHTML = weeks.map(w => `<option value="${w}">Week ${w}</option>`).join("");
    if (weeks.includes(prev)) sel.value = String(prev);
  }

  function setTimeSelectorValues({ year, month, week }) {
    $("#yearSelect").value = String(year);
    refreshMonthOptions();
    $("#monthSelect").value = String(month);
    refreshWeekOptions();
    $("#weekSelect").value = String(week);
  }

  function currentSelectionKey() {
    return `${String($("#yearSelect").value).padStart(4,"0")}-`
         + `${String($("#monthSelect").value).padStart(2,"0")}-`
         + `W${$("#weekSelect").value}`;
  }

  async function onTimeChange(which) {
    if (which === "year")  refreshMonthOptions();
    if (which !== "week")  refreshWeekOptions();

    let key = currentSelectionKey();
    if (!src().weeksByKey.has(key)) {
      const m = src().manifest;
      const year  = Number($("#yearSelect").value);
      const month = Number($("#monthSelect").value);
      const fallback = m.weeks
        .filter(w => w.year === year && w.month === month)[0]
        || m.weeks.filter(w => w.year === year)[0]
        || m.weeks[m.weeks.length - 1];
      setTimeSelectorValues(fallback);
      key = currentSelectionKey();
    }

    try {
      await loadWeek(key);
      applyWeekToMap();
      updateSummary();
      updateHeroStats();
      updateDateRange();
      if (state.selectedDistrict) {
        updateDetail(state.selectedDistrict);
        getTimeseries().then(ts =>
          drawTrendChart(state.selectedDistrict, ts[state.selectedDistrict] || []));
      }
    } catch (err) {
      console.error("Failed to switch week:", err);
    }
  }

  function updateDateRange() {
    const entry = src().weeksByKey.get(state.currentWeekKey);
    if (!entry) return;
    $("#dateRangeValue").textContent =
      `${fmtDate(entry.start)}  →  ${fmtDate(entry.end)}`;
  }

  // -- Location selectors --
  function populateLocationSelectors() {
    const states = Object.keys(state.stateToDistricts).sort((a,b)=>a.localeCompare(b));
    $("#stateSelect").innerHTML =
      `<option value="">— All states —</option>` +
      states.map(s => `<option value="${escapeHTML(s)}">${escapeHTML(s)}</option>`).join("");
    $("#stateSelect").addEventListener("change", () => refreshDistrictOptions());
    $("#districtSelect").addEventListener("change", () => {
      const name = $("#districtSelect").value;
      if (name) selectDistrict(name, { fromSelector: true });
    });
    refreshDistrictOptions();
  }

  function refreshDistrictOptions() {
    const st = $("#stateSelect").value;
    const list = st && state.stateToDistricts[st]
      ? state.stateToDistricts[st]
      : Object.keys(state.districtToState).sort((a,b)=>a.localeCompare(b));
    $("#districtSelect").innerHTML =
      `<option value="">— Select district —</option>` +
      list.map(d => `<option value="${escapeHTML(d)}">${escapeHTML(d)}</option>`).join("");
  }

  function syncLocationSelectorsTo(name) {
    const st = state.districtToState[name];
    if (!st) return;
    if ($("#stateSelect").value !== st) {
      $("#stateSelect").value = st;
      refreshDistrictOptions();
    }
    $("#districtSelect").value = name;
  }

  // ===========================================================
  // Map
  // ===========================================================

  function initMap() {
    state.map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
      minZoom: 4,
      maxZoom: 12,
      preferCanvas: true,
    }).setView([22.0, 80.5], 5);

    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Tiles &copy; Esri", maxZoom: 16 }
    ).addTo(state.map);

    state.map.createPane("labels");
    state.map.getPane("labels").style.zIndex = 450;
    state.map.getPane("labels").style.pointerEvents = "none";

    state.map.on("zoomend moveend", scheduleLabelRefresh);
  }

  function catColor(catKey) {
    const cats = v().categories;
    const found = cats.find(c => c.key === catKey);
    return found ? found.color : cats[cats.length - 1].color; // No Data fallback
  }

  function renderDistricts(geojson) {
    state.geojsonLayer = L.geoJSON(geojson, {
      style: () => ({
        color: "rgba(0,0,0,0.45)",
        weight: 0.3,
        fillColor: catColor("No Data"),
        fillOpacity: 0.88,
      }),
      onEachFeature: (feature, layer) => {
        const name = feature.properties[DISTRICT_KEY];
        state.districtLayer.set(name, layer);
        layer.on({
          mouseover: e => {
            if (layer === state.selectedLayer) return;
            e.target.setStyle({ weight: 1.6, color: "#ffffff" });
            e.target.bringToFront();
            showTooltip(layer, name);
          },
          mouseout: e => {
            if (layer === state.selectedLayer) return;
            e.target.setStyle({ weight: 0.3, color: "rgba(0,0,0,0.45)" });
            layer.closeTooltip();
          },
          click: () => selectDistrict(name, { fromMap: true }),
        });
      },
    }).addTo(state.map);

    state.map.fitBounds(state.geojsonLayer.getBounds(), { padding: [10, 10] });

    buildLabelMarkers();
    refreshLabels();
  }

  function applyWeekToMap() {
    if (!state.geojsonLayer || !state.currentWeekData) return;
    const districts = state.currentWeekData.districts;
    const catField = v().fields.category;
    state.geojsonLayer.eachLayer(layer => {
      if (layer === state.selectedLayer) return;
      const name = layer.feature.properties[DISTRICT_KEY];
      const rec = districts[name];
      const cat = rec ? rec[catField] : "No Data";
      layer.setStyle({ fillColor: catColor(cat || "No Data") });
    });
    if (state.selectedLayer) {
      const name = state.selectedLayer.feature.properties[DISTRICT_KEY];
      const rec = districts[name];
      const cat = rec ? rec[catField] : "No Data";
      state.selectedLayer.setStyle({ fillColor: catColor(cat || "No Data") });
    }
  }

  function showTooltip(layer, name) {
    const V = v();
    const rec = state.currentWeekData?.districts?.[name];
    const cat = rec ? rec[V.fields.category] : "No Data";
    const st  = state.districtToState[name] || "";
    const a   = rec ? rec[V.fields.actual]  : null;
    const n   = rec ? rec[V.fields.normal]  : null;
    const d   = rec ? rec[V.fields.measure] : null;
    const html = `
      <strong>${escapeHTML(name)}</strong>
      ${st ? `<div class="tt-state">${escapeHTML(st)}</div>` : ""}
      <div class="tt-row"><span>Actual</span><span>${V.formatActualMm(a)}</span></div>
      <div class="tt-row"><span>Normal</span><span>${V.formatNormalMm(n)}</span></div>
      <div class="tt-row"><span>${V.measureLabel}</span><span>${V.formatMeasure(d)}</span></div>
      <span class="tt-cat" style="background:${catColor(cat || "No Data")}">${cat || "No Data"}</span>
    `;
    layer.bindTooltip(html, {
      sticky: true, direction: "top",
      className: "district-tip", offset: [0, -6],
    }).openTooltip();
  }

  // ===========================================================
  // District selection
  // ===========================================================

  async function selectDistrict(name, { fromMap = false } = {}) {
    state.selectedDistrict = name;

    if (state.selectedLayer) {
      state.selectedLayer.setStyle({ weight: 0.3, color: "rgba(0,0,0,0.45)" });
    }

    const layer = state.districtLayer.get(name);
    if (layer) {
      state.selectedLayer = layer;
      layer.setStyle({ weight: 2.5, color: "#ffffff" });
      layer.bringToFront();
      showSelectedLabel(name, layer.getBounds().getCenter());
      if (!fromMap) {
        state.map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 8 });
      }
    }
    syncLocationSelectorsTo(name);
    updateDetail(name);

    try {
      const ts = await getTimeseries();
      drawTrendChart(name, ts[name] || []);
    } catch (err) { console.error(err); }
  }

  function updateDetail(name) {
    const V = v();
    $("#detailTitle").textContent = name;
    const st = state.districtToState[name] || "";
    $("#detailSub").textContent =
      `${st ? st + " · " : ""}Week ${state.currentWeekData.week} · `
      + `${MONTH_NAMES[state.currentWeekData.month-1]} ${state.currentWeekData.year}`;
    $("#detailBody").hidden = false;

    const rec = state.currentWeekData.districts[name];
    const a = rec?.[V.fields.actual];
    const n = rec?.[V.fields.normal];
    const d = rec?.[V.fields.measure];
    const cat = rec?.[V.fields.category] || "No Data";

    $("#metActual").textContent    = a == null ? "—" : Number(a).toFixed(1);
    $("#metNormal").textContent    = n == null ? "—" : Number(n).toFixed(1);
    $("#metDeviation").textContent = d == null ? "—" : (d > 0 ? "+" : "") + Number(d).toFixed(V.id === "rainfall" ? 1 : 2);

    const pill = $("#metCategory");
    pill.textContent = cat;
    pill.style.background = catColor(cat);
    pill.style.color = (cat === "No Data" || cat === "< -5" || cat === "-5 to -4" || cat === "> 5") ? "#e8eef5" : "#0d1117";
  }

  // ===========================================================
  // Hero stats / summary (exclude No Data)
  // ===========================================================

  function updateHeroStats() {
    const V = v();
    const catField = V.fields.category;
    const districts = state.currentWeekData?.districts || {};
    let surplus = 0, deficit = 0, total = 0;
    Object.values(districts).forEach(d => {
      total++;
      const c = d?.[catField];
      if (V.surplusKeys.has(c)) surplus++;
      else if (V.deficitKeys.has(c)) deficit++;
    });
    animateNumber($("#heroSurplus"), surplus);
    animateNumber($("#heroDeficit"), deficit);
    $("#heroSurplusPct").textContent = total ? `${((surplus/total)*100).toFixed(0)}%` : "—";
    $("#heroDeficitPct").textContent = total ? `${((deficit/total)*100).toFixed(0)}%` : "—";
  }

  function updateSummary() {
    const V = v();
    const catField = V.fields.category;
    const districts = state.currentWeekData?.districts || {};
    const visibleCats = V.categories.filter(c => c.key !== "No Data");
    const counts = Object.fromEntries(visibleCats.map(c => [c.key, 0]));
    let withData = 0, total = 0;
    Object.values(districts).forEach(d => {
      total++;
      const c = d?.[catField];
      if (!c || c === "No Data") return;
      if (counts[c] !== undefined) counts[c]++;
      withData++;
    });

    $("#summaryCount").textContent = withData === total
      ? `${total} districts`
      : `${withData} of ${total} districts`;

    $("#summaryBar").innerHTML = visibleCats.map(c => {
      const n = counts[c.key];
      const pct = withData ? (n / withData) * 100 : 0;
      if (pct === 0) return "";
      return `<div class="summary-bar-seg"
                   title="${c.key}: ${n} (${pct.toFixed(1)}%)"
                   style="flex:${pct}; background:${c.color}"></div>`;
    }).join("");

    $("#summaryLegend").innerHTML = visibleCats.map(c => {
      const n = counts[c.key];
      const pct = withData ? (n / withData) * 100 : 0;
      return `<li>
        <span class="leg-name">
          <span class="leg-swatch" style="background:${c.color}"></span>${c.key}
        </span>
        <span class="leg-val">${n} · ${pct.toFixed(0)}%</span>
      </li>`;
    }).join("");
  }

  // ===========================================================
  // Trend chart (actual vs normal in variable units, year-filtered)
  // ===========================================================

  function drawTrendChart(name, fullSeries) {
    const V = v();
    const year = Number($("#yearSelect").value);
    $("#chartYear").textContent = year;

    // Defensive: be tolerant of empty/malformed timeseries data — never
    // throw, because that would leave the previous variable's chart on screen.
    const safe = Array.isArray(fullSeries) ? fullSeries : [];
    const series = safe.filter(r =>
      r && typeof r.key === "string" && r.key.startsWith(`${year}-`)
    );
    const labels = series.map(r => trajectoryLabel(r.key));
    const actual = series.map(r => r[V.fields.actual]);
    const normal = series.map(r => r[V.fields.normal]);

    const pointColors = series.map(r => {
      const a = r[V.fields.actual];
      const n = r[V.fields.normal];
      if (a == null || n == null) return "#6c7a8c";
      return a >= n ? V.surplusColor : V.deficitColor;
    });

    const aboveColor = hexToRgba(V.surplusColor, 0.28);
    const belowColor = hexToRgba(V.deficitColor, 0.28);

    const cfg = {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Actual",
            data: actual,
            borderColor: "#e8eef5",
            borderWidth: 1.5,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 4.5,
            pointBackgroundColor: pointColors,
            pointBorderColor: "#0d1117",
            pointBorderWidth: 0.8,
            fill: { target: 1, above: aboveColor, below: belowColor },
            spanGaps: true,
            order: 1,
          },
          {
            label: "Normal",
            data: normal,
            borderColor: "#afbacb",
            borderWidth: 1,
            borderDash: [4, 4],
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            spanGaps: true,
            order: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { left: 0, right: 6, top: 6, bottom: 0 } },
        animation: { duration: 350 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#232b39",
            borderColor: "rgba(255,255,255,0.14)",
            borderWidth: 1,
            titleColor: "#e8eef5",
            bodyColor: "#afbacb",
            titleFont: { family: "IBM Plex Sans", size: 11.5, weight: "600" },
            bodyFont:  { family: "IBM Plex Mono", size: 11 },
            padding: 9,
            displayColors: false,
            callbacks: {
              title: ctx => ctx[0].label,
              label: ctx => {
                const r = series[ctx.dataIndex];
                const a = r[V.fields.actual], n = r[V.fields.normal];
                const above = (a != null && n != null && a >= n);
                return [
                  `Actual:  ${V.formatActualMm(a)}`,
                  `Normal:  ${V.formatNormalMm(n)}`,
                  `${V.measureLabel}: ${V.formatMeasure(r[V.fields.measure])}`,
                  above ? "↑ Above normal" : "↓ Below normal",
                ];
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              font: { family: "IBM Plex Mono", size: 9.5 },
              color: "#6c7a8c",
              maxRotation: 0, autoSkip: true, maxTicksLimit: 9,
            },
            grid: { display: false },
            border: { color: "rgba(255,255,255,0.08)" },
          },
          y: {
            beginAtZero: V.id === "rainfall",
            ticks: {
              font: { family: "IBM Plex Mono", size: 9.5 },
              color: "#6c7a8c",
              callback: val => `${val} ${V.yAxisUnit}`,
            },
            grid: { color: "rgba(255,255,255,0.05)" },
            border: { display: false },
          },
        },
      },
    };

    if (state.trendChart) state.trendChart.destroy();
    state.trendChart = new Chart($("#trendChart"), cfg);
  }

  function trajectoryLabel(key) {
    const m = key.match(/^(\d{4})-(\d{2})-W(\d)$/);
    if (!m) return key;
    return `${MONTH_NAMES[Number(m[2]) - 1].slice(0,3)} W${m[3]}`;
  }

  function hexToRgba(hex, alpha) {
    const m = hex.replace("#", "");
    const r = parseInt(m.slice(0,2), 16);
    const g = parseInt(m.slice(2,4), 16);
    const b = parseInt(m.slice(4,6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ===========================================================
  // Custom labels (important districts → all-visible districts)
  // ===========================================================

  function buildLabelMarkers() {
    state.geojsonLayer.eachLayer(layer => {
      const f = layer.feature;
      const dt = f.properties[DISTRICT_KEY];
      const bounds = layer.getBounds();
      const center = bounds.getCenter();
      const ne = bounds.getNorthEast();
      const sw = bounds.getSouthWest();
      const area = Math.abs((ne.lat - sw.lat) * (ne.lng - sw.lng));
      state.districtLabels.set(dt, {
        latlng: center, area,
        isImportant: IMPORTANT_DISTRICTS_LC.has(String(dt).toLowerCase().trim()),
        marker: null,
      });
    });
  }

  function scheduleLabelRefresh() {
    if (state.labelFrame) cancelAnimationFrame(state.labelFrame);
    state.labelFrame = requestAnimationFrame(refreshLabels);
  }

  function refreshLabels() {
    if (!state.map) return;
    const zoom = state.map.getZoom();
    const bounds = state.map.getBounds();

    state.districtLabels.forEach((info, name) => {
      let shouldShow = false;
      if (zoom >= 9) {
        shouldShow = bounds.contains(info.latlng);
      } else if (zoom >= 7) {
        shouldShow = info.isImportant && bounds.contains(info.latlng);
      }
      if (shouldShow) {
        if (!info.marker) {
          info.marker = L.marker(info.latlng, {
            icon: L.divIcon({
              className: "district-label" + (info.isImportant ? " is-important-label" : ""),
              html: escapeHTML(name),
              iconSize: [150, 14], iconAnchor: [75, 7],
            }),
            interactive: false, pane: "labels", keyboard: false,
          });
        }
        if (!info.marker._map) info.marker.addTo(state.map);
      } else if (info.marker?._map) {
        state.map.removeLayer(info.marker);
      }
    });
  }

  function showSelectedLabel(name, latlng) {
    if (state.selectedLabel) state.map.removeLayer(state.selectedLabel);
    state.selectedLabel = L.marker(latlng, {
      icon: L.divIcon({
        className: "district-label is-selected-label",
        html: escapeHTML(name),
        iconSize: [180, 16], iconAnchor: [90, 8],
      }),
      interactive: false, pane: "labels", keyboard: false,
    }).addTo(state.map);
  }

  // ===========================================================
  // Bottom legend
  // ===========================================================

  function buildLegend() {
    const V = v();
    const items = V.categories
      .filter(c => c.key !== "No Data")
      .map(c => {
        // If the range already starts with the key (temperature case:
        // key "< -5", range "< -5 °C"), drop the duplicate key prefix.
        const dup = c.range.startsWith(c.key);
        return `
          <div class="legend-item">
            <span class="legend-swatch" style="background:${c.color}"></span>
            ${dup ? "" : `<span>${c.key}</span>`}
            <span class="legend-range">${c.range}</span>
          </div>`;
      }).join("");
    $("#legendBar").innerHTML =
      `<div class="legend-title" id="legendTitle">${escapeHTML(V.legendTitle)}</div>` + items;
  }

  // ===========================================================
  // Misc
  // ===========================================================

  function animateNumber(el, end, duration = 500) {
    const start = parseInt(el.textContent, 10);
    const from = Number.isFinite(start) ? start : 0;
    if (!Number.isFinite(end)) { el.textContent = "—"; return; }
    const t0 = performance.now();
    const range = end - from;
    function tick(t) {
      const p = Math.min((t - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + range * eased);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function hideLoading() {
    requestAnimationFrame(() => $("#loadingScreen").classList.add("is-hidden"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
