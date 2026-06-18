"""
Climate Anomaly Atlas — Data Pipeline (rainfall + temperature)
==============================================================

Generates per-week district-level data for two climate variables:

  • Rainfall      — deviation from the 1961-2010 normal (in %)
  • Temperature   — anomaly from the 2016-2024 normal (in °C),
                    for both daily maximum (tmax) and minimum (tmin)

Output layout
-------------
    <dashboard_data_dir>/
        districts.geojson                 shared base geometry
        rainfall/
            manifest.json
            timeseries.json
            weeks/YYYY-MM-WN.json         { dtname: { actual, normal,
                                                       deviation, category } }
        temperature/
            manifest.json
            timeseries.json
            weeks/YYYY-MM-WN.json         { dtname: { tmax_actual, tmax_normal,
                                                       tmax_anomaly, tmax_category,
                                                       tmin_actual, tmin_normal,
                                                       tmin_anomaly, tmin_category } }

Week convention
---------------
Each month is split into 4 fixed weeks:
    W1 = days 1-7   |  W2 = days 8-14
    W3 = days 15-21 |  W4 = days 22-28
Days 29-31 are intentionally excluded. A week is processed only after it has
fully completed (week_end < today).

Auto-download
-------------
Daily IMD .grd files are downloaded automatically when they're missing from
their respective raw_dir.  Files already on disk are never re-fetched.

Idempotency
-----------
Per-week JSON files are kept if they already exist, so re-runs only do the
new weeks.  The manifest and timeseries files are rebuilt every run from
whatever per-week files are present.

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

import json
import os
from datetime import date, timedelta
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
    # ----- Rainfall (daily .grd + 1961-2010 normal NetCDF) -----
    "rainfall_raw_dir":       r"D:\Satsure\IMD\weekly_weather_report\Rainfall\rainfall_data",
    "rainfall_historical_nc": r"D:\Satsure\IMD\weekly_weather_report\Rainfall\rainfall_data\rainfall_1961_2010.nc",

    # ----- Temperature (daily .grd for tmax+tmin + 2016-2024 normals) -----
    "temperature_raw_dir":    r"D:\Satsure\IMD\weekly_weather_report\Temperature\data",
    "tmax_historical_nc":     r"D:\Satsure\IMD\weekly_weather_report\Temperature\data\tmax_2016_2024.nc",
    "tmin_historical_nc":     r"D:\Satsure\IMD\weekly_weather_report\Temperature\data\tmin_2016_2024.nc",

    # ----- Shared -----
    "district_shapefile":    r"D:\Satsure\IMD\India_Boundary\simplified\India_District_Simplified_RID.shp",
    "dashboard_data_dir":    r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\data",
    "start_date":            date(2024, 1, 1),

    # Which variables to generate. Drop one if you only want the other.
    "variables":             ("rainfall", "temperature"),

    "district_key":          "dtname",
    "state_key":             "stname",
}


# ========================== WEEK ENUMERATION ========================

def iter_completed_month_weeks(start: date, today: date):
    """Yield (year, month, week_num, week_start, week_end) for completed weeks."""
    year, month = start.year, start.month
    while date(year, month, 1) <= today:
        for week_num in (1, 2, 3, 4):
            day_start = (week_num - 1) * 7 + 1
            day_end = week_num * 7
            week_start = date(year, month, day_start)
            week_end = date(year, month, day_end)
            if week_start < start:
                continue
            if week_end < today:
                yield year, month, week_num, week_start, week_end
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


# ========================== AUTO-DOWNLOAD ===========================

def _ensure_imd_data(var: str, week_start: date, week_end: date, raw_dir: str) -> None:
    """
    Make sure the IMD daily .grd files for `var` are on disk for [start, end].

    Probes by opening; if that raises FileNotFoundError, downloads the range
    and retries. Existing files are never re-fetched.

    `var` is one of 'rain', 'tmax', 'tmin'.
    """
    raw_dir_p = Path(raw_dir)
    raw_dir_p.mkdir(parents=True, exist_ok=True)
    try:
        imd.open_real_data(var, week_start, week_end, file_dir=str(raw_dir_p))
    except FileNotFoundError:
        print(f"    downloading IMD {var} files {week_start} → {week_end}")
        imd.get_real_data(var, week_start, week_end, file_dir=str(raw_dir_p))


# ========================== HISTORICAL CACHE ========================

_HISTORICAL_CACHE: dict[str, xr.Dataset] = {}

def _load_historical(path: str, mask_neg999: bool = False) -> xr.Dataset:
    """Lazy-load a historical NetCDF once per process."""
    if path not in _HISTORICAL_CACHE:
        ds = xr.open_dataset(path)
        if mask_neg999:
            data_var = list(ds.data_vars)[0]
            ds = ds.where(ds[data_var] != -999.0)
        _HISTORICAL_CACHE[path] = ds
    return _HISTORICAL_CACHE[path]


def _select_calendar_window(ds: xr.Dataset, month: int,
                            day_start: int, day_end: int) -> xr.Dataset:
    """All historical days falling in [month/day_start … month/day_end]."""
    return ds.sel(time=(
        (ds["time"].dt.month == month) &
        (ds["time"].dt.day >= day_start) &
        (ds["time"].dt.day <= day_end)
    ))


def _round_or_none(v, ndp: int = 2):
    if pd.isna(v):
        return None
    return round(float(v), ndp)


# ===================== DISTRICTS GEODATAFRAME =======================

_DISTRICTS_GDF: gpd.GeoDataFrame | None = None

def _load_districts_gdf() -> gpd.GeoDataFrame:
    """
    Read the district shapefile once and return it as a GeoDataFrame in
    EPSG:4326. The shapefile is already simplified, so no geometry
    simplification is applied here. exact_extract requires a GeoDataFrame
    (not a path) in the current API.
    """
    global _DISTRICTS_GDF
    if _DISTRICTS_GDF is None:
        gdf = gpd.read_file(CONFIG["district_shapefile"])
        if gdf.crs is None:
            gdf = gdf.set_crs(4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        _DISTRICTS_GDF = gdf
    return _DISTRICTS_GDF


def _zonal_mean_one(ds: xr.Dataset, var_name: str, out_col: str) -> pd.DataFrame:
    """Run exact_extract for a single variable; pass the cached GeoDataFrame."""
    if ds.rio.crs is None:
        ds = ds.rio.write_crs("EPSG:4326")
    return exact_extract(
        ds[var_name], _load_districts_gdf(), ["mean"],
        include_cols=[CONFIG["district_key"]], output="pandas",
    ).rename(columns={"mean": out_col})


# ============================ RAINFALL ==============================

def rainfall_actual_for_week(week_start: date, week_end: date) -> xr.Dataset:
    """Sum of daily rainfall over the week."""
    _ensure_imd_data("rain", week_start, week_end, CONFIG["rainfall_raw_dir"])
    ds = imd.open_real_data(
        "rain", week_start, week_end, file_dir=CONFIG["rainfall_raw_dir"],
    ).get_xarray()
    ds = ds.where(ds["rain"] != -999.0)
    return ds.sum(dim="time", skipna=True)


def rainfall_normal_for_week(month: int, day_start: int, day_end: int) -> xr.Dataset:
    """Mean of yearly-summed rainfall across 1961-2010 over the same calendar window."""
    ds = _load_historical(CONFIG["rainfall_historical_nc"], mask_neg999=True)
    sel = _select_calendar_window(ds, month, day_start, day_end)
    yearly_sums = sel.groupby("time.year").sum(dim="time")
    return yearly_sums.mean(dim="year", skipna=True)


def classify_rainfall(d) -> str:
    if d is None or pd.isna(d):
        return "No Data"
    if d >  20:      return "Excess"
    if d > -19.99:   return "Normal"
    if d > -59.99:   return "Deficient"
    if d > -99.99:   return "Scanty"
    return "No Rain"


def process_rainfall_week(year, month, week_num, week_start, week_end,
                          out_root: Path) -> dict | None:
    week_key = f"{year:04d}-{month:02d}-W{week_num}"
    week_file = out_root / "rainfall" / "weeks" / f"{week_key}.json"
    if week_file.exists():
        with open(week_file, encoding="utf-8") as f:
            return json.load(f)

    print(f"  rainfall    {week_key}  [{week_start} → {week_end}]")
    try:
        actual = rainfall_actual_for_week(week_start, week_end)
    except Exception as exc:
        print(f"    SKIPPED: could not load rainfall ({exc})")
        return None

    normal = rainfall_normal_for_week(month, week_start.day, week_end.day)
    df = _zonal_mean_one(actual, "rain", "actual").merge(
         _zonal_mean_one(normal, "rain", "normal"),
         on=CONFIG["district_key"])
    df["normal"] = df["normal"].replace(0, pd.NA)
    df["deviation"] = ((df["actual"] - df["normal"]) / df["normal"]) * 100
    df["category"] = df["deviation"].apply(classify_rainfall)

    districts = {}
    for _, row in df.iterrows():
        districts[row[CONFIG["district_key"]]] = {
            "actual":    _round_or_none(row["actual"], 2),
            "normal":    _round_or_none(row["normal"], 2),
            "deviation": _round_or_none(row["deviation"], 1),
            "category":  row["category"],
        }

    record = _week_record(week_key, year, month, week_num,
                          week_start, week_end, districts)
    _write_json(week_file, record)
    return record


# =========================== TEMPERATURE ============================

TEMP_BINS   = (-np.inf, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, np.inf)
TEMP_LABELS = ("< -5", "-5 to -4", "-4 to -3", "-3 to -2", "-2 to -1", "-1 to 0",
               "0 to 1", "1 to 2", "2 to 3", "3 to 4", "4 to 5", "> 5")


def temp_actual_for_week(var: str, week_start: date, week_end: date) -> xr.Dataset:
    """Weekly mean of tmax or tmin. Sentinel = the max value in the cube (IMD convention)."""
    _ensure_imd_data(var, week_start, week_end, CONFIG["temperature_raw_dir"])
    ds = imd.open_real_data(
        var, week_start, week_end, file_dir=CONFIG["temperature_raw_dir"],
    ).get_xarray()
    # Mirror the notebook: drop the IMD "no-data" sentinel which equals the cube max
    sentinel = ds[var].max().values
    ds[var] = ds[var].where(ds[var] != sentinel)
    return ds.mean(dim="time", skipna=True)


def temp_normal_for_week(var: str, month: int,
                         day_start: int, day_end: int) -> xr.Dataset:
    """Mean of yearly-mean temperature across 2016-2024 over the same calendar window."""
    path = CONFIG[f"{var}_historical_nc"]
    ds = _load_historical(path, mask_neg999=False)
    sel = _select_calendar_window(ds, month, day_start, day_end)
    yearly_means = sel.groupby("time.year").mean(dim="time", skipna=True)
    return yearly_means.mean(dim="year", skipna=True)


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


def process_temperature_week(year, month, week_num, week_start, week_end,
                             out_root: Path) -> dict | None:
    """
    Separate tmax + tmin anomalies per district for the week.

      tmax/tmin_actual  = weekly mean of daily tmax / tmin
      tmax/tmin_normal  = mean across 2016-2024 yearly-mean over the same calendar window
      tmax/tmin_anomaly = actual - normal, clipped to ±10 °C
    """
    week_key = f"{year:04d}-{month:02d}-W{week_num}"
    week_file = out_root / "temperature" / "weeks" / f"{week_key}.json"
    if week_file.exists():
        with open(week_file, encoding="utf-8") as f:
            rec = json.load(f)
        sample = next(iter(rec.get("districts", {}).values()), {})
        # Current schema has tmax_*/tmin_* keys
        if "tmax_actual" in sample or "tmin_actual" in sample:
            return rec
        print(f"  temperature {week_key}: outdated schema → re-processing")

    print(f"  temperature {week_key}  [{week_start} → {week_end}]")

    districts: dict[str, dict] = {}
    any_ok = False

    for var in ("tmax", "tmin"):
        try:
            actual = temp_actual_for_week(var, week_start, week_end)
        except Exception as exc:
            print(f"    SKIPPED {var}: {exc}")
            continue

        normal = temp_normal_for_week(var, month, week_start.day, week_end.day)
        anomaly_ds = actual - normal
        # Clip to physically plausible ±10 °C window (mirror the notebook)
        anomaly_ds[var] = anomaly_ds[var].where(
            (anomaly_ds[var] > -10) & (anomaly_ds[var] < 10)
        )

        df = _zonal_mean_one(actual,     var, "actual").merge(
             _zonal_mean_one(normal,     var, "normal"),
             on=CONFIG["district_key"]).merge(
             _zonal_mean_one(anomaly_ds, var, "anomaly"),
             on=CONFIG["district_key"])
        df["category"] = df["anomaly"].apply(classify_temp)

        for _, row in df.iterrows():
            dt = row[CONFIG["district_key"]]
            entry = districts.setdefault(dt, {})
            entry[f"{var}_actual"]   = _round_or_none(row["actual"], 2)
            entry[f"{var}_normal"]   = _round_or_none(row["normal"], 2)
            entry[f"{var}_anomaly"]  = _round_or_none(row["anomaly"], 2)
            entry[f"{var}_category"] = row["category"]
        any_ok = True

    if not any_ok:
        return None

    record = _week_record(week_key, year, month, week_num,
                          week_start, week_end, districts)
    _write_json(week_file, record)
    return record


# ========================== SHARED OUTPUT ===========================

def _week_record(week_key, year, month, week_num,
                 week_start, week_end, districts) -> dict:
    return {
        "key":       week_key,
        "year":      year,
        "month":     month,
        "week":      week_num,
        "start":     week_start.isoformat(),
        "end":       week_end.isoformat(),
        "districts": districts,
    }


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def write_base_geometry(out_root: Path) -> None:
    out_d = out_root / "districts.geojson"
    if out_d.exists():
        print(f"  districts.geojson already exists, skipping (delete to regenerate)")
        return
    dkey, skey = CONFIG["district_key"], CONFIG["state_key"]
    # Reuse the same cached, reprojected GeoDataFrame that exact_extract uses.
    gdf = _load_districts_gdf()
    keep = [c for c in (dkey, skey) if c in gdf.columns] + ["geometry"]
    gdf = gdf[keep]
    
    # Write to a temporary file, then read, round coordinates to 5 decimals, minify, and save
    temp_path = out_root / "temp_districts.geojson"
    gdf.to_file(temp_path, driver="GeoJSON")
    
    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        def round_coords(coords, precision=5):
            if isinstance(coords, list):
                if len(coords) > 0 and isinstance(coords[0], (int, float)):
                    return [round(c, precision) for c in coords]
                else:
                    return [round_coords(c, precision) for c in coords]
            return coords

        for feature in data.get("features", []):
            geom = feature.get("geometry")
            if geom and "coordinates" in geom:
                geom["coordinates"] = round_coords(geom["coordinates"])
                
        with open(out_d, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
                
    print(f"  wrote {out_d.name}  "
          f"({len(gdf)} features, {out_d.stat().st_size/1024:.0f} KB)")


def write_manifest_and_timeseries(out_root: Path, variable: str,
                                  records: list[dict | None]) -> None:
    """Rebuild manifest.json + timeseries.json for `variable`."""
    base = out_root / variable
    manifest = []
    timeseries: dict[str, list[dict]] = {}

    for r in records:
        if r is None:
            continue
        manifest.append({
            "key":   r["key"], "year": r["year"], "month": r["month"],
            "week":  r["week"], "start": r["start"], "end": r["end"],
        })
        for name, vals in r["districts"].items():
            timeseries.setdefault(name, []).append({"key": r["key"], **vals})

    for name in timeseries:
        timeseries[name].sort(key=lambda x: x["key"])

    _write_json(base / "manifest.json", {
        "variable":        variable,
        "weeks":           manifest,
        "generated_at":    date.today().isoformat(),
        "week_definition": "W1=1-7, W2=8-14, W3=15-21, W4=22-28",
    })
    _write_json(base / "timeseries.json", timeseries)

    ts_kb = (base / "timeseries.json").stat().st_size / 1024
    print(f"  {variable}/manifest.json   ({len(manifest)} weeks)")
    print(f"  {variable}/timeseries.json ({len(timeseries)} districts, {ts_kb:.0f} KB)")


# ================================ MAIN ==============================

def main() -> None:
    out_root = Path(CONFIG["dashboard_data_dir"])
    out_root.mkdir(parents=True, exist_ok=True)

    print("Base geometry")
    print("-------------")
    write_base_geometry(out_root)

    today = date.today()
    weeks = list(iter_completed_month_weeks(CONFIG["start_date"], today))
    print(f"\n{len(weeks)} completed weeks to consider")

    if "rainfall" in CONFIG["variables"]:
        print("\nRainfall")
        print("--------")
        (out_root / "rainfall" / "weeks").mkdir(parents=True, exist_ok=True)
        records = [process_rainfall_week(y, m, w, ws, we, out_root)
                   for (y, m, w, ws, we) in weeks]
        write_manifest_and_timeseries(out_root, "rainfall", records)

    if "temperature" in CONFIG["variables"]:
        print("\nTemperature (tmax + tmin)")
        print("-------------------------")
        (out_root / "temperature" / "weeks").mkdir(parents=True, exist_ok=True)
        records = [process_temperature_week(y, m, w, ws, we, out_root)
                   for (y, m, w, ws, we) in weeks]
        write_manifest_and_timeseries(out_root, "temperature", records)

    print("\nDone.")


if __name__ == "__main__":
    main()
