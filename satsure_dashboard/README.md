# SatSure Climate Anomaly Atlas (SatSure design build)

A re-skin of the India Climate Anomaly Atlas following the SatSure dashboard
design system (Teal `#0BAFAF`, Manrope, white cards, 8px grid, 4px radius,
MUI-style elevation). It reuses the **same data** as the original dashboard
(`../data/`) — nothing here re-runs the pipeline.

## Files
| File | Purpose |
|------|---------|
| `index.html` | Dashboard markup |
| `style.css` | Design-system stylesheet |
| `app.js` | Map + charts + layer logic (reads `../data/`) |
| `build_standalone.py` | Bundles everything into one offline file |
| `dashboard_standalone.html` | Built single-file version (double-click to open) |

## Run it
- **Standalone (easiest):** double-click `dashboard_standalone.html`.
- **Served:** from the parent `weather_dashboard/` folder run
  `python -m http.server` and open
  `http://127.0.0.1:8000/satsure_dashboard/index.html`.

## Rebuild after a data refresh
```bash
python build_standalone.py
```

## Notes on this build
- **Layer panel** lists the three climate variables (info + show toggle only) —
  no per-class toggles, no opacity slider.
- **Normal-period** for the active variable is shown centered in the top app bar.
- **Distribution this week** is a doughnut chart with a compact legend.
- **Single page** — laid out to fit the viewport without scrolling on desktop.
- **Duplicate district names** (e.g. *Aurangabad* in Bihar & Maharashtra) are
  disambiguated by state: the dropdown suffixes the state, and map clicks /
  selections navigate to the polygon in the matching state.
  > Data limitation: the per-week JSON is keyed by district name only, so the
  > two same-named districts currently share one data value. Navigation/state
  > context is correct; splitting their values would require a pipeline change.
- The SatSure logo (`Satsure_Transparent_Bg_logo.png`) sits on a white pill in
  the app bar; `build_standalone.py` embeds it as a base64 data URI.
- The active-variable chip is shown at the **top-right** of the map; the basemap
  is the Carto Positron tiles toned down slightly for contrast.
- The normal-period note (per variable) and **Source: IMD** are shown in the
  bottom bar.
