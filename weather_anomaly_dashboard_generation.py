"""
Climate Anomaly Atlas — Data Pipeline (rainfall + temperature)
==============================================================

Generates per-period, multi-level anomaly data for two climate variables:

  • Rainfall      — deviation from the 1971-2020 IMD LPA normal (in %)
  • Temperature   — anomaly from the 2016-2024 normal (in °C),
                    for both daily maximum (tmax) and minimum (tmin)

Spatial levels (all area-weighted zonal means of the IMD daily grids):
  • districts  — every district polygon              (key: dtname)
  • states     — districts dissolved by state        (key: stname)
  • india      — a single all-India polygon          (single record)

Temporal granularities (all computed from historic DAILY data):
  • weeks   — fixed 4 weeks/month (W1=1-7, W2=8-14, W3=15-21, W4=22-28)
  • months  — the full calendar month
  • seasons — Kharif (Jun-Sep), Rabi (Oct-Mar, spans the year → labelled by
              its END crop-year, e.g. Oct 2025-Mar 2026 = "2026-Rabi"), Zaid (Apr-May)

Output layout
-------------
    <dashboard_data_dir>/
        districts.geojson                 base district geometry
        states.geojson                    base state geometry (dissolved)
        rainfall/
            manifest.json                 { weeks:[…], months:[…], seasons:[…] }
            timeseries.json               weekly district series (legacy, kept)
            trends.json                   { week|month|season: {districts,states,india} }
            weeks/YYYY-MM-WN.json         { districts:{…}, states:{…}, india:{…} }
            months/YYYY-MM.json
            seasons/YYYY-Season.json
        temperature/                      same layout, temperature fields

Each rainfall record:  { actual, normal, deviation, category }
Each temperature record: { tmax_actual, tmax_normal, tmax_anomaly, tmax_category,
                           tmin_actual, tmin_normal, tmin_anomaly, tmin_category }
The `india` block is a single record object (not keyed).

Auto-download
-------------
Daily IMD .grd files are downloaded automatically when they're missing from
their respective raw_dir.  Files already on disk are never re-fetched.

Idempotency
-----------
Per-period JSON files are kept if they already contain all three spatial
levels (and, for temperature, both tmax and tmin).  Older week files that
predate the state/India levels are re-processed once to backfill them.

Temperature classification (12 bins, °C)
----------------------------------------
    < -5    -5 to -4    -4 to -3    -3 to -2    -2 to -1    -1 to 0
     0 to 1   1 to 2     2 to 3      3 to 4      4 to 5      > 5

Rainfall classification (5 IMD-style bins)
------------------------------------------
    Excess (>+20%), Normal (-19% to +20%), Deficient (-20 to -59%),
    Scanty (-60 to -99%), No Rain (≤ -99%).
"""

from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import imdlib as imd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  (registers .rio accessor on xarray)
import xarray as xr
from exactextract import exact_extract


# ============================== CONFIG ==============================
# Edit these paths to match your environment.

CONFIG = {
    # ----- Rainfall (daily .grd + 1971-2020 LPA normal NetCDF) -----
    # Normal is the IMD Long Period Average over 1971-2020, computed on the fly
    # from the 1901-2025 daily grid (sliced to rainfall_normal_years).
    "rainfall_raw_dir":       r"D:\Satsure\IMD\weekly_weather_report\Rainfall\rainfall_data",
    "rainfall_historical_nc": r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\rainfall_historic\india_rainfall_1901_2025.nc",
    "rainfall_normal_years":  (1971, 2020),

    # ----- Temperature (daily .grd for tmax+tmin + 2016-2024 normals) -----
    "temperature_raw_dir":    r"D:\Satsure\IMD\weekly_weather_report\Temperature\data",
    "tmax_historical_nc":     r"D:\Satsure\IMD\weekly_weather_report\Temperature\data\tmax_2016_2024.nc",
    "tmin_historical_nc":     r"D:\Satsure\IMD\weekly_weather_report\Temperature\data\tmin_2016_2024.nc",
    # Daily ACTUALS source (same 0.5 deg grid as the normals). Used instead of
    # the IMD real-time download for any date these files cover (through 2025).
    "tmax_actual_nc":         r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\temp_historic\imd_tmax_1996_2025.nc",
    "tmin_actual_nc":         r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\temp_historic\imd_tmin_1996_2025.nc",

    # ----- Shared -----
    "district_shapefile":    r"D:\Satsure\IMD\India_Boundary\simplified\India_District_Simplified_RID.shp",
    "dashboard_data_dir":    r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\data",
    "start_date":            date(2021, 1, 1),

    # Which variables to generate. Drop one if you only want the other.
    "variables":             ("rainfall", "temperature"),

    "district_key":          "dtname",
    "state_key":             "stname",
    "india_key":             "region",
}

# Crop seasons: name, (start_month, start_day), (end_month, end_day), spans_year.
# Rabi spans the year-end (Oct→Mar) and is labelled by its starting crop-year.
SEASONS = (
    ("Kharif", (6, 1),  (9, 30),  False),
    ("Rabi",   (10, 1), (3, 31),  True),
    ("Zaid",   (4, 1),  (5, 31),  False),
)


# ========================== PERIOD ENUMERATION ======================
# A "period" is a contiguous [start, end] date range plus the calendar
# "footprint" used to pick matching days from the baseline years.

def _period(key, kind, start, end, footprint, spans_year, meta):
    return {"key": key, "kind": kind, "start": start, "end": end,
            "footprint": footprint, "spans_year": spans_year, "meta": meta}


def iter_completed_week_periods(start: date, today: date):
    """Fixed 4 weeks/month (days 29-31 dropped); only fully-completed weeks."""
    year, month = start.year, start.month
    while date(year, month, 1) <= today:
        for wk in (1, 2, 3, 4):
            d0, d1 = (wk - 1) * 7 + 1, wk * 7
            ws, we = date(year, month, d0), date(year, month, d1)
            if ws >= start and we < today:
                yield _period(f"{year:04d}-{month:02d}-W{wk}", "week", ws, we,
                              (month, d0, month, d1), False,
                              {"year": year, "month": month, "week": wk})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def iter_completed_month_periods(start: date, today: date):
    """The full calendar month, once it has fully completed."""
    year, month = start.year, start.month
    while date(year, month, 1) <= today:
        last = calendar.monthrange(year, month)[1]
        ms, me = date(year, month, 1), date(year, month, last)
        if ms >= start and me < today:
            yield _period(f"{year:04d}-{month:02d}", "month", ms, me,
                          (month, 1, month, last), False,
                          {"year": year, "month": month})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def iter_completed_season_periods(start: date, today: date):
    """
    Kharif / Rabi / Zaid crop seasons, once fully completed.

    A season is labelled by its END crop-year. For non-spanning seasons that
    equals the start year; the spanning Rabi (Oct-Mar) is labelled by year+1
    (e.g. Oct 2025-Mar 2026 → "2026-Rabi").
    """
    for year in range(start.year - 1, today.year + 1):
        for name, (sm, sd), (em, ed), spans in SEASONS:
            s = date(year, sm, sd)
            e = date(year + 1 if spans else year, em, ed)
            label_year = year + 1 if spans else year
            if s >= start and e < today:
                yield _period(f"{label_year:04d}-{name}", "season", s, e,
                              (sm, sd, em, ed), spans,
                              {"year": label_year, "season": name})


def inprogress_season_period(today: date, latest_end: date):
    """
    The season currently in progress, computed season-start → latest available
    date (partial "to-date"). The footprint is the same partial window so the
    normal is the baseline average over exactly the same span. Same key scheme
    as completed seasons, so it upgrades in place once the season finishes.

    Returns None when no season is in progress, or the season has started but no
    data is available in it yet.
    """
    for name, (sm, sd), (em, ed), spans in SEASONS:
        # The instance whose window contains `today` (previous crop-year for the
        # year-spanning Rabi when today is in Jan-Mar).
        syear = today.year - 1 if spans and today.month <= em else today.year
        s = date(syear, sm, sd)
        e = date(syear + 1 if spans else syear, em, ed)
        label_year = syear + 1 if spans else syear
        if not (s <= today <= e):
            continue
        end = min(latest_end, e)
        if end < s:            # season just started, no completed week in it yet
            return None
        return _period(f"{label_year:04d}-{name}", "season", s, end,
                       (sm, sd, end.month, end.day), spans,
                       {"year": label_year, "season": name})
    return None


# ========================== AUTO-DOWNLOAD ===========================

def _ensure_imd_data(var: str, d0: date, d1: date, raw_dir: str) -> None:
    """Download IMD daily .grd files for `var` over [d0, d1] if missing."""
    raw_dir_p = Path(raw_dir)
    raw_dir_p.mkdir(parents=True, exist_ok=True)
    try:
        imd.open_real_data(var, d0, d1, file_dir=str(raw_dir_p))
    except FileNotFoundError:
        print(f"    downloading IMD {var} files {d0} → {d1}")
        imd.get_real_data(var, d0, d1, file_dir=str(raw_dir_p))


# ========================== HISTORICAL CACHE ========================

_HISTORICAL_CACHE: dict[tuple, xr.Dataset] = {}

def _load_historical(path: str, mask_neg999: bool = False,
                     years: tuple[int, int] | None = None,
                     mask_above: float | None = None) -> xr.Dataset:
    """
    Lazy-load a historical NetCDF once per process.

    `years` restricts the baseline to an inclusive [start, end] year range
    (e.g. (1971, 2020) for the IMD LPA). Slicing happens BEFORE the masks
    so a large multi-decade file is never fully materialised.

    Masks (so no-data never participates in the normal):
      • `mask_neg999`  -> drop the -999 rainfall sentinel.
      • `mask_above`   -> drop values >= this threshold, e.g. the 99.9 IMD
                          temperature fill value (real temps never reach it).
    """
    key = (path, years, mask_neg999, mask_above)
    if key not in _HISTORICAL_CACHE:
        ds = xr.open_dataset(path)
        if years is not None:
            ds = ds.sel(time=slice(str(years[0]), str(years[1])))
        data_var = list(ds.data_vars)[0]
        if mask_neg999:
            ds = ds.where(ds[data_var] != -999.0)
        if mask_above is not None:
            ds = ds.where(ds[data_var] < mask_above)
        _HISTORICAL_CACHE[key] = ds
    return _HISTORICAL_CACHE[key]


def _historical_actual(path: str, d0: date, d1: date, agg: str,
                       mask_neg999: bool = False,
                       mask_above: float | None = None) -> xr.Dataset | None:
    """
    Aggregate the daily historical NetCDF over [d0, d1] as the period ACTUAL
    (sum for rainfall, mean for temperature). Returns None if the range isn't
    fully inside the file's time span, so the caller can fall back to the IMD
    real-time download. Same cache/masks as the baseline loader, so the actual
    sits on the identical grid as its normal.
    """
    base = _load_historical(path, mask_neg999=mask_neg999, mask_above=mask_above)
    tmin = pd.Timestamp(base["time"].min().values)
    tmax = pd.Timestamp(base["time"].max().values)
    if pd.Timestamp(d0) < tmin or pd.Timestamp(d1) > tmax:
        return None
    sub = base.sel(time=slice(str(d0), str(d1)))
    if agg == "sum":
        return sub.sum(dim="time", skipna=True, min_count=1)
    return sub.mean(dim="time", skipna=True)


def _footprint_months(sm: int, em: int, spans: bool) -> list[int]:
    return list(range(sm, 13)) + list(range(1, em + 1)) if spans else list(range(sm, em + 1))


def _period_normal(ds: xr.Dataset, period: dict, agg: str) -> xr.Dataset:
    """
    Baseline normal grid for a period.

    Selects every baseline day whose (month, day) falls inside the period's
    calendar footprint, groups them into per-instance crop/calendar years,
    aggregates within each instance-year (`sum` for rainfall, `mean` for
    temperature), then averages across the *complete* instance-years.

    Handles year-spanning periods (Rabi) and drops partial instance-years at
    the baseline edges so a half-season never biases the normal.
    """
    sm, sd, em, ed = period["footprint"]
    spans = period["spans_year"]
    start_md, end_md = sm * 100 + sd, em * 100 + ed
    md = ds["time"].dt.month * 100 + ds["time"].dt.day
    mask = (md >= start_md) | (md <= end_md) if spans else (md >= start_md) & (md <= end_md)
    sel = ds.sel(time=mask)

    yr = sel["time"].dt.year
    inst = xr.where(sel["time"].dt.month >= sm, yr, yr - 1) if spans else yr
    inst_vals = np.asarray(inst.data)

    # Keep only instance-years that cover every footprint month.
    n_months = len(_footprint_months(sm, em, spans))
    present = pd.Series(sel["time"].dt.month.values).groupby(inst_vals).nunique()
    complete = np.asarray(present.index[present.values == n_months])
    keep_idx = np.nonzero(np.isin(inst_vals, complete))[0]
    sel = sel.isel(time=keep_idx)
    sel = sel.assign_coords(inst=("time", inst_vals[keep_idx]))

    grouped = sel.groupby("inst")
    # min_count=1 (sum only): a cell with no valid data in a period stays NaN
    # instead of becoming 0, so no-data/ocean cells don't dilute rainfall means.
    per_inst = (grouped.sum("time", skipna=True, min_count=1) if agg == "sum"
                else grouped.mean("time", skipna=True))
    return per_inst.mean("inst", skipna=True)


def _round_or_none(v, ndp: int = 2):
    if pd.isna(v):
        return None
    return round(float(v), ndp)


# ===================== ZONE GEODATAFRAMES ===========================

_GDF_CACHE: dict[str, gpd.GeoDataFrame] = {}

def _load_districts_gdf() -> gpd.GeoDataFrame:
    """District shapefile in EPSG:4326 (already simplified)."""
    if "districts" not in _GDF_CACHE:
        gdf = gpd.read_file(CONFIG["district_shapefile"])
        if gdf.crs is None:
            gdf = gdf.set_crs(4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        _GDF_CACHE["districts"] = gdf
    return _GDF_CACHE["districts"]


def _make_valid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repair self-intersections so exact_extract doesn't hit TopologyException."""
    gdf = gdf.copy()
    try:
        gdf["geometry"] = gdf.geometry.make_valid()
    except AttributeError:            # older shapely/geopandas
        gdf["geometry"] = gdf.geometry.buffer(0)
    return gdf


def _load_states_gdf() -> gpd.GeoDataFrame:
    """Districts dissolved by state name (geometry repaired)."""
    if "states" not in _GDF_CACHE:
        skey = CONFIG["state_key"]
        clean = _make_valid(_load_districts_gdf())
        gdf = clean.dissolve(by=skey, as_index=False)[[skey, "geometry"]]
        _GDF_CACHE["states"] = _make_valid(gdf)
    return _GDF_CACHE["states"]


def _load_india_gdf() -> gpd.GeoDataFrame:
    """A single all-India polygon (geometry repaired)."""
    if "india" not in _GDF_CACHE:
        clean = _make_valid(_load_districts_gdf())
        gdf = clean.dissolve().reset_index(drop=True)[["geometry"]]
        gdf[CONFIG["india_key"]] = "India"
        _GDF_CACHE["india"] = _make_valid(gdf)
    return _GDF_CACHE["india"]


def _levels() -> list[tuple[str, gpd.GeoDataFrame, str]]:
    """(block name, zones gdf, key column) for the three spatial levels."""
    return [
        ("districts", _load_districts_gdf(), CONFIG["district_key"]),
        ("states",    _load_states_gdf(),    CONFIG["state_key"]),
        ("india",     _load_india_gdf(),     CONFIG["india_key"]),
    ]


def _zonal_mean(ds: xr.Dataset, var_name: str, out_col: str,
                zones: gpd.GeoDataFrame, key: str) -> pd.DataFrame:
    """Area-weighted zonal mean of `var_name` over `zones`."""
    if ds.rio.crs is None:
        ds = ds.rio.write_crs("EPSG:4326")
    return exact_extract(
        ds[var_name], zones, ["mean"], include_cols=[key], output="pandas",
    ).rename(columns={"mean": out_col})


def _as_block(records: dict, is_india: bool):
    """India collapses to a single record object; others stay keyed."""
    if not is_india:
        return records
    return next(iter(records.values()), None)


# ============================ RAINFALL ==============================

def rainfall_actual(d0: date, d1: date) -> xr.Dataset:
    """Sum of daily rainfall over [d0, d1]."""
    # Prefer the local daily historical file (1901-2025); it covers all backfill
    # dates, so no download happens. Fall back to the IMD real-time grid only
    # for dates past the file's span.
    hist = _historical_actual(CONFIG["rainfall_historical_nc"], d0, d1, "sum",
                              mask_neg999=True)
    if hist is not None:
        return hist
    _ensure_imd_data("rain", d0, d1, CONFIG["rainfall_raw_dir"])
    ds = imd.open_real_data("rain", d0, d1, file_dir=CONFIG["rainfall_raw_dir"]).get_xarray()
    ds = ds.where(ds["rain"] != -999.0)
    # min_count=1 so all-no-data cells (e.g. ocean) stay NaN instead of summing
    # to 0 — a 0 would be treated as valid and dilute the zonal means
    # (especially coastal districts / states / the all-India aggregate).
    return ds.sum(dim="time", skipna=True, min_count=1)


def classify_rainfall(d) -> str:
    if d is None or pd.isna(d):
        return "No Data"
    if d >  20:      return "Excess"
    if d > -19.99:   return "Normal"
    if d > -59.99:   return "Deficient"
    if d > -99.99:   return "Scanty"
    return "No Rain"


def compute_rainfall(period: dict) -> dict:
    actual = rainfall_actual(period["start"], period["end"])
    normal = _period_normal(
        _load_historical(CONFIG["rainfall_historical_nc"], mask_neg999=True,
                         years=CONFIG["rainfall_normal_years"]), period, "sum")

    blocks = {}
    for name, zones, key in _levels():
        df = _zonal_mean(actual, "rain", "actual", zones, key).merge(
             _zonal_mean(normal, "rain", "normal", zones, key), on=key)
        df["normal"] = df["normal"].replace(0, pd.NA)
        df["deviation"] = ((df["actual"] - df["normal"]) / df["normal"]) * 100
        df["category"] = df["deviation"].apply(classify_rainfall)
        recs = {row[key]: {
            "actual":    _round_or_none(row["actual"], 2),
            "normal":    _round_or_none(row["normal"], 2),
            "deviation": _round_or_none(row["deviation"], 1),
            "category":  row["category"],
        } for _, row in df.iterrows()}
        blocks[name] = _as_block(recs, name == "india")
    return blocks


# =========================== TEMPERATURE ============================

TEMP_BINS   = (-np.inf, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, np.inf)
TEMP_LABELS = ("< -5", "-5 to -4", "-4 to -3", "-3 to -2", "-2 to -1", "-1 to 0",
               "0 to 1", "1 to 2", "2 to 3", "3 to 4", "4 to 5", "> 5")


def temp_actual(var: str, d0: date, d1: date) -> xr.Dataset:
    """Mean of daily tmax/tmin over [d0, d1]. Drops the 99.9 IMD no-data fill."""
    # Prefer the local daily historical file (1996-2025, same 0.5 deg grid as the
    # normal); no download. Fall back to the IMD real-time grid past its span.
    hist = _historical_actual(CONFIG[f"{var}_actual_nc"], d0, d1, "mean",
                              mask_above=90.0)
    if hist is not None:
        return hist
    _ensure_imd_data(var, d0, d1, CONFIG["temperature_raw_dir"])
    ds = imd.open_real_data(var, d0, d1, file_dir=CONFIG["temperature_raw_dir"]).get_xarray()
    # Fixed threshold (real temps never reach 90 C) instead of the data-dependent
    # cube max, so no-data is dropped even in a cube that happens to contain none.
    ds[var] = ds[var].where(ds[var] < 90.0)
    return ds.mean(dim="time", skipna=True)


def classify_temp(anomaly) -> str:
    if anomaly is None or pd.isna(anomaly):
        return "No Data"
    a = float(anomaly)
    if a < -5: return "< -5"
    if a < -4: return "-5 to -4"
    if a < -3: return "-4 to -3"
    if a < -2: return "-3 to -2"
    if a < -1: return "-2 to -1"
    if a <  0: return "-1 to 0"
    if a <  1: return "0 to 1"
    if a <  2: return "1 to 2"
    if a <  3: return "2 to 3"
    if a <  4: return "3 to 4"
    if a <  5: return "4 to 5"
    return "> 5"


def compute_temperature(period: dict) -> dict | None:
    """tmax + tmin anomalies for districts / states / india."""
    per_level: dict[str, dict] = {name: {} for name, _, _ in _levels()}
    any_ok = False

    for var in ("tmax", "tmin"):
        try:
            actual = temp_actual(var, period["start"], period["end"])
        except Exception as exc:
            print(f"    SKIPPED {var}: {exc}")
            continue
        # mask_above=90 drops the 99.9 IMD temperature fill so no-data cells
        # don't leak into the normal (real temps never reach 90 C).
        normal = _period_normal(
            _load_historical(CONFIG[f"{var}_historical_nc"], mask_above=90.0), period, "mean")
        anomaly = actual - normal
        anomaly[var] = anomaly[var].where((anomaly[var] > -10) & (anomaly[var] < 10))

        for name, zones, key in _levels():
            df = _zonal_mean(actual,  var, "actual",  zones, key).merge(
                 _zonal_mean(normal,  var, "normal",  zones, key), on=key).merge(
                 _zonal_mean(anomaly, var, "anomaly", zones, key), on=key)
            df["category"] = df["anomaly"].apply(classify_temp)
            for _, row in df.iterrows():
                entry = per_level[name].setdefault(row[key], {})
                entry[f"{var}_actual"]   = _round_or_none(row["actual"], 2)
                entry[f"{var}_normal"]   = _round_or_none(row["normal"], 2)
                entry[f"{var}_anomaly"]  = _round_or_none(row["anomaly"], 2)
                entry[f"{var}_category"] = row["category"]
        any_ok = True

    if not any_ok:
        return None
    return {name: _as_block(recs, name == "india") for name, recs in per_level.items()}


# ============================ PROCESS ONE ===========================

_COMPUTE = {"rainfall": compute_rainfall, "temperature": compute_temperature}
_FOLDER  = {"week": "weeks", "month": "months", "season": "seasons"}


def _is_complete(rec: dict, variable: str) -> bool:
    """A stored file is done when it has all three levels (both temp vars)."""
    if not all(k in rec for k in ("districts", "states", "india")):
        return False
    if rec["india"] is None or not rec["districts"]:
        return False
    if variable == "temperature":
        sample = next(iter(rec["districts"].values()), {})
        return "tmax_actual" in sample and "tmin_actual" in sample
    return True


def process_period(variable: str, period: dict, out_root: Path) -> dict | None:
    folder = _FOLDER[period["kind"]]
    subdir = "rainfall" if variable == "rainfall" else "temperature"
    path = out_root / subdir / folder / f"{period['key']}.json"

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            rec = None            # corrupt/partial write → recompute over it
        if rec is not None and _is_complete(rec, variable) \
                and rec.get("end") == period["end"].isoformat():
            return rec
        print(f"  {variable:11s} {period['key']}: window/levels changed → re-processing")

    print(f"  {variable:11s} {period['key']}  [{period['start']} → {period['end']}]")
    try:
        blocks = _COMPUTE[variable](period)
    except Exception as exc:
        print(f"    SKIPPED: {exc}")
        return None
    if blocks is None:
        return None

    record = {"key": period["key"], "kind": period["kind"],
              "start": period["start"].isoformat(), "end": period["end"].isoformat(),
              **period["meta"], **blocks}
    _write_json(path, record)
    return record


# ========================== SHARED OUTPUT ===========================

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def _round_coords(coords, precision=5):
    if isinstance(coords, list):
        if coords and isinstance(coords[0], (int, float)):
            return [round(c, precision) for c in coords]
        return [_round_coords(c, precision) for c in coords]
    return coords


def _write_geojson_minified(gdf: gpd.GeoDataFrame, out_path: Path, cols: list[str]) -> None:
    keep = [c for c in cols if c in gdf.columns] + ["geometry"]
    tmp = out_path.with_suffix(".tmp.geojson")
    gdf[keep].to_file(tmp, driver="GeoJSON")
    try:
        with open(tmp, encoding="utf-8") as f:
            data = json.load(f)
        for feature in data.get("features", []):
            geom = feature.get("geometry")
            if geom and "coordinates" in geom:
                geom["coordinates"] = _round_coords(geom["coordinates"])
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
    print(f"  wrote {out_path.name}  "
          f"({len(gdf)} features, {out_path.stat().st_size/1024:.0f} KB)")


def write_base_geometry(out_root: Path) -> None:
    dkey, skey = CONFIG["district_key"], CONFIG["state_key"]
    d_path = out_root / "districts.geojson"
    if d_path.exists():
        print("  districts.geojson already exists, skipping (delete to regenerate)")
    else:
        _write_geojson_minified(_load_districts_gdf(), d_path, [dkey, skey])
    s_path = out_root / "states.geojson"
    if s_path.exists():
        print("  states.geojson already exists, skipping (delete to regenerate)")
    else:
        _write_geojson_minified(_load_states_gdf(), s_path, [skey])


def _manifest_entry(rec: dict) -> dict:
    keys = ("key", "year", "month", "week", "season", "start", "end")
    return {k: rec[k] for k in keys if k in rec}


def write_outputs(out_root: Path, variable: str,
                  by_kind: dict[str, list[dict | None]]) -> None:
    """Rebuild manifest.json, trends.json and legacy timeseries.json."""
    base = out_root / variable

    manifest = {"variable": variable, "generated_at": date.today().isoformat(),
                "week_definition": "W1=1-7, W2=8-14, W3=15-21, W4=22-28",
                "season_definition": "Kharif Jun-Sep · Rabi Oct-Mar (labelled by end year) · Zaid Apr-May"}
    trends: dict[str, dict] = {}

    for kind, plural in (("week", "weeks"), ("month", "months"), ("season", "seasons")):
        recs = [r for r in by_kind.get(kind, []) if r]
        recs.sort(key=lambda r: r["key"])
        manifest[plural] = [_manifest_entry(r) for r in recs]

        series = {"districts": {}, "states": {}, "india": []}
        for r in recs:
            for name, vals in r["districts"].items():
                series["districts"].setdefault(name, []).append({"key": r["key"], **vals})
            for name, vals in r["states"].items():
                series["states"].setdefault(name, []).append({"key": r["key"], **vals})
            if r.get("india"):
                series["india"].append({"key": r["key"], **r["india"]})
        trends[kind] = series

    _write_json(base / "manifest.json", manifest)
    _write_json(base / "trends.json", trends)
    # Legacy weekly district series (kept for the older root dashboard).
    _write_json(base / "timeseries.json", trends["week"]["districts"])

    print(f"  {variable}/manifest.json   "
          f"({len(manifest['weeks'])} weeks, {len(manifest['months'])} months, "
          f"{len(manifest['seasons'])} seasons)")


# ================================ MAIN ==============================

def main() -> None:
    out_root = Path(CONFIG["dashboard_data_dir"])
    out_root.mkdir(parents=True, exist_ok=True)

    print("Base geometry")
    print("-------------")
    write_base_geometry(out_root)

    today = date.today()
    start = CONFIG["start_date"]
    periods = {
        "week":   list(iter_completed_week_periods(start, today)),
        "month":  list(iter_completed_month_periods(start, today)),
        "season": list(iter_completed_season_periods(start, today)),
    }
    # Current season "to date": start → end of the latest completed week (the
    # freshest data the weekly view already trusts). Regenerated every run.
    if periods["week"]:
        ip = inprogress_season_period(today, periods["week"][-1]["end"])
        if ip is not None:
            periods["season"].append(ip)
    print(f"\n{len(periods['week'])} weeks · {len(periods['month'])} months · "
          f"{len(periods['season'])} seasons to consider")

    for variable in CONFIG["variables"]:
        v = "rainfall" if variable == "rainfall" else "temperature"
        print(f"\n{v.title()}")
        print("-" * len(v))
        by_kind: dict[str, list[dict | None]] = {}
        for kind, plist in periods.items():
            (out_root / v / _FOLDER[kind]).mkdir(parents=True, exist_ok=True)
            by_kind[kind] = [process_period(variable, p, out_root) for p in plist]
        write_outputs(out_root, v, by_kind)

    print("\nDone.")


if __name__ == "__main__":
    main()
