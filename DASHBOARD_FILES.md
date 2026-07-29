# SatSure Climate Anomaly Atlas — Required Files

Inventory of everything the dashboard needs to build and run. Live site:
https://santa1309.github.io/climate_change_at_glance/satsure_dashboard/

There are **two git repos** on disk (siblings under `D:\Satsure\satsure_codes1\dashboard\`):

| Repo folder | GitHub remote | Role |
|---|---|---|
| `weather_dashboard\` | `santa1309/india-climate-anomaly-atlas` | **Source**: pipeline + dashboard code + a working copy of `data/` |
| `climate_change_at_glance\` | `santa1309/climate_change_at_glance` | **Deploy / GitHub Pages**: `data/` mirror + served dashboard |

`climate_change_at_glance` is produced from `weather_dashboard` by `publish_satsure.py` (robocopy mirror + file copy), so **edit the `weather_dashboard` copies, never the deploy mirror**.

---

## 1. Pipeline (code) — `weather_dashboard\`

| Path | Required | Purpose |
|---|---|---|
| `weather_anomaly_dashboard_generation.py` | ✅ core | Reads NetCDF → computes district/state/india anomalies → writes `data/` JSON |
| `satsure_dashboard\publish_satsure.py` | ✅ | Generate → mirror to deploy → commit+push **both** repos → verify live |
| `satsure_dashboard\update_satsure.bat` | ✅ | One-click updater (calls `publish_satsure.py`) |
| `satsure_dashboard\build_standalone.py` | ⬜ optional | Builds offline single-file HTML (`--build`) |
| `README.md`, `PROCESS.md` | ⬜ docs | |
| `dash_format\*.md` (01–05) | ⬜ docs | Design-system reference |

## 2. Front-end (served dashboard) — `weather_dashboard\satsure_dashboard\`

| Path | Required | Purpose |
|---|---|---|
| `index.html` | ✅ | Page shell (loads `app.js?v=…`) |
| `app.js` | ✅ | All dashboard logic (map, filters, distribution, trends) |
| `style.css` | ✅ | Styling |
| `Satsure_Transparent_Bg_logo.png` | ✅ | Logo |

These 4 = `DASH_FILES` in `publish_satsure.py`, copied into the deploy repo on publish.

## 3. Generated data — `weather_dashboard\data\` (mirrored to deploy)

| Path | Purpose |
|---|---|
| `districts.geojson`, `states.geojson` | Base map geometry |
| `rainfall\manifest.json`, `temperature\manifest.json` | Lists all weeks/months/seasons |
| `rainfall\trends.json`, `temperature\trends.json` | Per-level time series ⚠️ temp is ~52 MB, nearing GitHub's 50 MB warn |
| `rainfall\{weeks,months,seasons}\*.json` | Per-period anomaly records (districts/states/india) |
| `temperature\{weeks,months,seasons}\*.json` | Same for tmax/tmin |
| `*\timeseries.json` | Legacy; **excluded** from the deploy repo (`.gitignore` + robocopy `/XF`) |

## 4. External inputs (NOT in either repo; local only)

| Path | Used for |
|---|---|
| `weather_dashboard\rainfall_historic\india_rainfall_1901_2025.nc` | Rainfall **actuals** (2021+) **and** the 1971-2020 normal (~6.4 GB) |
| `weather_dashboard\temp_historic\imd_tmax_1996_2025.nc` | tmax daily **actuals** (0.5° grid) |
| `weather_dashboard\temp_historic\imd_tmin_1996_2025.nc` | tmin daily **actuals** |
| `D:\Satsure\IMD\...\tmax_2016_2024.nc`, `tmin_2016_2024.nc` | Temperature **normal** baseline (2016-2024) |
| `D:\Satsure\IMD\India_Boundary\simplified\India_District_Simplified_RID.shp` | District zones (`dtname`/`stname`) |
| `D:\Satsure\IMD\weekly_weather_report\{Rainfall,Temperature}\...` (raw `.grd`) | IMD real-time fallback for dates **past 2025** (2026+) |

All `.nc` and `rainfall_historic/` are **gitignored** (exceed GitHub's 100 MB limit).

## 5. Runtime

- **Python**: `C:\ProgramData\anaconda3\envs\spi\python.exe` (the `spi` conda env — only one with `imdlib`, `xarray`, `geopandas`, `exactextract`, `rioxarray`, `netCDF4`). Override via `SPI_PYTHON` env var.
- **Update everything**: double-click `weather_dashboard\satsure_dashboard\update_satsure.bat` (or `python publish_satsure.py`). Flags: `--no-push`, `--no-verify`, `--build`.

## Not required (safe to delete / regenerable)
`dashboard_standalone.html` (offline build), `__pycache__/`, promo media (`*.mp4`, `*.gif`) — all gitignored. The old root `india-climate-anomaly-atlas` dashboard files were removed (SatSure dashboard is the active one).
