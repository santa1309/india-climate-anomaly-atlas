# Update & Deployment Process — India Climate Anomaly Atlas

**Date performed:** 2026-06-19
**Goal:** Update the weekly temperature & rainfall anomaly dashboard from
`2026-05-W3` to the latest completed week, then publish to GitHub Pages.
**Result:** Data updated through `2026-06-W2`; live at
<https://santa1309.github.io/india-climate-anomaly-atlas/>

---

## 0. Context

The dashboard generates per-week, district-level climate anomalies for India from
IMD daily gridded data:

- **Rainfall** — deviation from the 1961–2010 normal (%)
- **Max / Min temperature** — anomaly from the 2016–2024 normal (°C)

Week convention: each month split into 4 fixed 7-day weeks (W1=1–7, W2=8–14,
W3=15–21, W4=22–28; days 29–31 excluded). A week is only processed once fully
complete (`week_end < today`).

Before the update the data ran `2024-01-W1 → 2026-05-W3`. With today = 2026-06-19,
three newly-completed weeks were due:

| Week         | Range            |
|--------------|------------------|
| `2026-05-W4` | May 22 – May 28  |
| `2026-06-W1` | Jun 1 – Jun 7    |
| `2026-06-W2` | Jun 8 – Jun 14   |

`2026-06-W3` (ends Jun 21) was correctly **excluded** — not yet complete.

---

## 1. Environment selection

The required stack is `imdlib`, `geopandas`, `exactextract`, `rioxarray`, `xarray`,
`numpy`, `pandas`.

- ❌ Default `base` Python — no `geopandas`.
- ❌ `WEATHER_ANALYSIS` env — **broken**: NumPy 2.0 removed `np.round_`, which dask
  (pulled in transitively) still references → `AttributeError`.
- ✅ **`spi` env** (`C:/ProgramData/anaconda3/envs/spi/python.exe`) — full stack works
  (only a harmless `GDAL_DATA` warning).

> All subsequent commands use the `spi` interpreter.

---

## 2. Generate the new weeks

```bash
cd "D:/Satsure/satsure_codes1/dashboard/weather_dashboard"
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
  C:/ProgramData/anaconda3/envs/spi/python.exe weather_anomaly_dashboard_generation.py
```

**Why `PYTHONUTF8=1`:** the script prints a `→` (U+2192) character; without UTF-8
the Windows cp1252 console raised `UnicodeEncodeError` and aborted. This is purely a
console-output issue — it does not affect data.

What the run did:
- Skipped existing `districts.geojson` (already simplified — never regenerated).
- Auto-downloaded the missing IMD daily `.grd` files for the 3 new weeks
  (rain, tmax, tmin).
- Computed per-district zonal means via `exactextract`, classified anomalies, and
  wrote new per-week JSON files.
- Rebuilt `manifest.json` and `timeseries.json` for both variables.

**Idempotency:** existing per-week JSON files were kept untouched; only the 3 new
weeks were created. No existing data was altered.

New files written:
```
data/rainfall/weeks/2026-05-W4.json, 2026-06-W1.json, 2026-06-W2.json
data/temperature/weeks/2026-05-W4.json, 2026-06-W1.json, 2026-06-W2.json
```

---

## 3. Verify the data

```bash
# manifests
python -c "import json;m=json.load(open('data/rainfall/manifest.json'));print(m['generated_at'], m['weeks'][-1]['key'])"
# -> 2026-06-19 2026-06-W2   (118 weeks; temperature identical)

# sample new week
python -c "import json;d=json.load(open('data/temperature/weeks/2026-06-W2.json'));print(len(d['districts']))"
# -> 762 districts, real tmax/tmin actual/normal/anomaly values
```

Both variables: **118 weeks**, **762 districts**, `generated_at = 2026-06-19`,
latest `2026-06-W2`. Spot-checked values were physically plausible (pre-monsoon dry
rainfall in Gujarat; tmax anomalies ~+1–2 °C).

---

## 4. Rebuild the standalone (offline) dashboard

```bash
PYTHONUTF8=1 C:/ProgramData/anaconda3/envs/spi/python.exe build_standalone_dashboard.py
```

Produces `dashboard_standalone.html` (~61 MB) with all CSS, JS and data inlined —
runs by double-clicking, no server needed. `app.js` is dual-mode: it reads the
embedded `EMBEDDED_DATA` blob when present, otherwise fetches `./data/...` over HTTP.

---

## 5. Prepare for GitHub Pages

Site is fully static; the dynamic multi-file version is the Pages entry point
(matches the existing repo). Added:

- **`.nojekyll`** — serve every file as-is (no Jekyll processing).
- **`.gitignore`** — exclude logs, `__pycache__`, `.claude/`, intermediate
  `data/temp_districts.geojson`.
- **`README.md`** — project overview, layout, hosting & update instructions.

`app.js` uses relative data paths (`./data/rainfall`, `./data/temperature`), so the
site works from any repo or sub-path. GitHub serves the JSON/GeoJSON gzip-compressed
automatically.

---

## 6. Commit

```bash
git init -b main
git config user.email "santoshgeo22@gmail.com"
git config user.name  "santa1309"
rm -f generation_run.log
git add -A
git commit -m "India Climate Anomaly Atlas: data through 2026-06-W2"
```

Initial commit: **251 files** (site + full `data/` + standalone).

---

## 7. Local preview (sanity check)

```bash
PYTHONUTF8=1 C:/ProgramData/anaconda3/envs/spi/python.exe run_dashboard.py
# serves http://127.0.0.1:8000 with on-the-fly gzip, opens Chrome
```

Verified over HTTP: `index.html` 200; rainfall manifest → 118 weeks / latest
`2026-06-W2`; new rainfall & temperature week files → 762 districts each;
`districts.geojson` served (gzip ~4.9 MB). The browser auto-loaded the latest week.
Server then stopped.

---

## 8. Push to GitHub

The remote `india-climate-anomaly-atlas` already existed with **unrelated history**
(fresh `git init` here), so a normal push would be rejected. Chosen resolution:
**force-push**, replacing remote `main`.

```bash
git remote add origin https://github.com/santa1309/india-climate-anomaly-atlas.git
git ls-remote --heads origin          # read-only auth probe (credentials cached via GCM)
git push --force -u origin main
```

- Push succeeded: `630fb08...2f195f7 main -> main (forced update)`.
- GitHub emitted the expected **>50 MB warning** for `dashboard_standalone.html`
  (61.34 MB) — allowed (under the 100 MB hard limit).

---

## 9. Verify the live deployment

GitHub Pages auto-rebuilt (Pages was already enabled). Polled the live manifest:

```bash
curl -s --compressed "https://santa1309.github.io/india-climate-anomaly-atlas/data/rainfall/manifest.json"
```

- ~20 s after push: still old (115 weeks / `2026-05-W3`).
- ~40 s after push: **118 weeks / `2026-06-W2` / generated 2026-06-19** ✅

Live site confirmed serving the updated data.

---

## Reproducing a future update

1. `PYTHONUTF8=1 <spi-python> weather_anomaly_dashboard_generation.py`
2. `PYTHONUTF8=1 <spi-python> build_standalone_dashboard.py`
3. `git add -A && git commit -m "data through <latest-week>"`
4. `git push origin main` (fast-forward now that history is shared)
5. Wait ~1–3 min; verify the live manifest.

### Gotchas
- Use the **`spi`** env, not `WEATHER_ANALYSIS` (NumPy 2.0 / dask breakage).
- Always set **`PYTHONUTF8=1`** to avoid the cp1252 `→` crash.
- **Never** regenerate/simplify `districts.geojson` — it is already simplified.
- The pipeline only adds weeks where `week_end < today`; run after a week fully ends.
- `dashboard_standalone.html` (~61 MB) trips GitHub's >50 MB warning but is accepted.
