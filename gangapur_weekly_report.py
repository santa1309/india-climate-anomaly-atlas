"""
Gangapur tehsil (Sawai Madhopur, Rajasthan) weekly rainfall departure -> CSV.
June & July 2026 plus August W1-W2, 10 completed weeks. No maps.

Gangapur is a sub-district, so it is not in the atlas's period JSONs; every value
here is computed from the source grids with the generator's own functions.
The parent district Sawai Madhopur rides along as a control: its recomputed value
must match the stored JSON, which proves this path reproduces the generator.

Run:  C:\\ProgramData\\anaconda3\\envs\\spi\\python.exe gangapur_weekly_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

import weather_anomaly_dashboard_generation as gen

DATA = Path(r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\data")
SHP = Path(r"D:\Satsure\satsure_codes1\dashboard\Gangapur\Gangapur.shp")
OUT = Path(r"D:\Satsure\satsure_codes1\dashboard\gangapur_2026_report")
WEEKS = ([f"2026-{m:02d}-W{w}" for m in (6, 7) for w in (1, 2, 3, 4)]
         + ["2026-08-W1", "2026-08-W2"])          # through 14 Aug
CONTROL = "Sawai Madhopur"  # unique district name -> stored JSON record is safe to trust


def zones() -> gpd.GeoDataFrame:
    """Gangapur tehsil + its parent district, in one frame keyed by `zone`."""
    teh = gpd.read_file(SHP).to_crs("EPSG:4326")[["geometry"]]
    teh["zone"] = "Gangapur"
    dist = gpd.read_file(DATA / "districts.geojson")
    dist = dist[dist["dtname"] == CONTROL][["geometry"]]
    dist["zone"] = CONTROL
    assert len(teh) == 1 and len(dist) == 1
    return pd.concat([teh, dist], ignore_index=True)


def main() -> None:
    z = zones()
    baseline = gen._load_historical(gen.CONFIG["rainfall_historical_nc"], mask_neg999=True,
                                    years=gen.CONFIG["rainfall_normal_years"])
    periods = {p["key"]: p for p in gen.iter_completed_week_periods(
        pd.Timestamp("2026-06-01").date(), pd.Timestamp.today().date())}

    rows = []
    for key in WEEKS:
        p = periods[key]
        print(f"  {key} ...", flush=True)
        actual = gen._zonal_mean(gen.rainfall_actual(p["start"], p["end"]),
                                 "rain", "actual", z, "zone")
        normal = gen._zonal_mean(gen._period_normal(baseline, p, "sum"),
                                 "rain", "normal", z, "zone")
        df = actual.merge(normal, on="zone").set_index("zone")
        df["deviation"] = (df["actual"] - df["normal"]) / df["normal"] * 100

        # Control: recomputed parent district must reproduce the published record.
        want = json.loads((DATA / "rainfall" / "weeks" / f"{key}.json")
                          .read_text(encoding="utf-8"))["districts"][CONTROL]
        got = df.loc[CONTROL]
        for f in ("actual", "normal", "deviation"):
            assert abs(got[f] - want[f]) <= 0.05, f"{key} {CONTROL} {f}: {got[f]} != {want[f]}"

        g = df.loc["Gangapur"]
        assert pd.notna(g["actual"]) and g["normal"] > 0, f"{key}: no grid data over Gangapur"
        rows.append({
            "week_key": key, "start": p["start"], "end": p["end"],
            "month": pd.Timestamp(p["start"]).strftime("%B"), "week": p["meta"]["week"],
            "state": "Rajasthan", "district": "Sawai Madhopur", "tehsil": "Gangapur",
            "actual_mm": round(g["actual"], 2), "normal_mm": round(g["normal"], 2),
            "deviation_pct": round(g["deviation"], 1),
            "category": gen.classify_rainfall(g["deviation"]),
            "district_actual_mm": want["actual"], "district_normal_mm": want["normal"],
            "district_deviation_pct": want["deviation"], "district_category": want["category"],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "gangapur_rainfall_weekly_2026-06_2026-08.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
