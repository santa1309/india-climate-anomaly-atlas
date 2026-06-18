# India Climate Anomaly Atlas

An open, interactive atlas of **weekly temperature and rainfall anomalies** for every
district in India, built from IMD daily gridded data.

🌐 **Live (previous deployment):** https://santa1309.github.io/india-climate-anomaly-atlas/

The map shows, for each completed week:

- **Rainfall** — deviation from the 1961–2010 normal (%)
- **Max temperature** — anomaly from the 2016–2024 normal (°C)
- **Min temperature** — anomaly from the 2016–2024 normal (°C)

Pick a year / month / week, switch the variable from the map tabs, and click any
district for its actual vs. normal values and a weekly trajectory chart.

**Data coverage:** 2024-01-W1 → 2026-06-W2 (updated 2026-06-19).

---

## Week convention

Each month is split into four fixed 7-day weeks; days 29–31 are excluded:

| Week | Days   |
|------|--------|
| W1   | 1–7    |
| W2   | 8–14   |
| W3   | 15–21  |
| W4   | 22–28  |

A week is only published once it has fully completed (`week_end < today`).

---

## Repository layout

```
index.html                     Dashboard markup (GitHub Pages entry point)
style.css                      Styles
app.js                         Map + chart logic (fetches data/ over HTTP,
                               or reads an embedded blob in the standalone build)
data/
  districts.geojson            Shared base geometry (already simplified)
  rainfall/
    manifest.json              List of available weeks
    timeseries.json            Per-district series for the trajectory chart
    weeks/YYYY-MM-WN.json       One file per week
  temperature/
    manifest.json
    timeseries.json
    weeks/YYYY-MM-WN.json
dashboard_standalone.html      Self-contained offline build (all data inlined)
weather_anomaly_dashboard_generation.py   Data pipeline (IMD → per-week JSON)
build_standalone_dashboard.py  Bundles the site + data into the standalone HTML
run_dashboard.py               Local gzip dev server (http://127.0.0.1:8000)
```

`districts.geojson` is **already simplified** — do not simplify it further.

---

## Hosting on GitHub Pages

This is a static site. After pushing to a GitHub repository:

1. Repo **Settings → Pages**.
2. **Source:** *Deploy from a branch* → branch `main`, folder `/ (root)`.
3. The `.nojekyll` file ensures GitHub serves every file as-is.

The site loads data with relative paths (`./data/...`), so it works from any
repo or sub-path. GitHub serves the JSON/GeoJSON gzip-compressed automatically.

### Offline / single-file version

`dashboard_standalone.html` embeds all data and runs by double-clicking it
(no server needed). Rebuild it after a data refresh with:

```bash
python build_standalone_dashboard.py
```

---

## Updating the data

The pipeline is idempotent: existing per-week JSON files are kept, only new
completed weeks are computed, and the manifest + timeseries are rebuilt each run.
Daily IMD `.grd` files are auto-downloaded when missing.

```bash
# Uses the conda env that has imdlib + geopandas + exactextract + rioxarray
python weather_anomaly_dashboard_generation.py
python build_standalone_dashboard.py   # refresh the offline build
```

Configure input paths (raw IMD dirs, historical normals, district shapefile) in
the `CONFIG` block at the top of `weather_anomaly_dashboard_generation.py`.

### Local preview

```bash
python run_dashboard.py   # serves the dynamic site at http://127.0.0.1:8000
```

---

## Data sources & methodology

- **Rainfall:** IMD daily gridded rainfall; normal = mean of yearly weekly-sums
  across 1961–2010. Classes: Excess (>+20%), Normal (−19 to +20%),
  Deficient (−20 to −59%), Scanty (−60 to −99%), No Rain (≤ −99%).
- **Temperature:** IMD daily gridded tmax/tmin; normal = mean of yearly
  weekly-means across 2016–2024. Anomalies binned in 1 °C steps from <−5 °C to >+5 °C
  and clipped to ±10 °C.

District-level values are area-weighted zonal means computed with
[`exactextract`](https://github.com/isciences/exactextract).
