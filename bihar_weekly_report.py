"""
Bihar district-wise weekly rainfall departure — maps + CSV, June-August 2026.

Read-only consumer of the dashboard's existing period JSONs
(data/rainfall/weeks/*.json). Writes one PNG map per completed week using the
same legend as the live Anomaly Atlas, plus two CSVs.

Run:  C:\\ProgramData\\anaconda3\\envs\\spi\\python.exe bihar_weekly_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

import weather_anomaly_dashboard_generation as gen

DATA = Path(r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\data")
OUT = Path(r"D:\Satsure\satsure_codes1\dashboard\bihar_2026_report")
STATE = "BIHAR"
# Every week JSON the generator has published for these months — August is
# partial (W1, W2 so far), so glob rather than assume 4 weeks per month.
MONTHS = ("2026-06", "2026-07", "2026-08")
WEEKS = sorted(p.stem for p in (DATA / "rainfall" / "weeks").glob("*.json")
               if p.stem[:7] in MONTHS)

# ponytail: copied from satsure_dashboard/app.js:17-22 rather than parsed out of
# the JS — 6 lines, and the legend has not changed since the atlas shipped.
CATS = [
    ("Excess",    "#60b1f4", ">+20%"),
    ("Normal",    "#6ae944", "-19% to +20%"),
    ("Deficient", "#dd7534", "-20% to -59%"),
    ("Scanty",    "#ffe23a", "-60% to -99%"),
    ("No Rain",   "#969696", "<= -99%"),
    ("No Data",   "#E9EDF0", "-"),
]
COLOR = {k: c for k, c, _ in CATS}

# Period JSONs key districts by name only (generator: recs = {row[dtname]: ...}),
# so duplicate names across states collide and the last geojson feature wins.
# Bihar is hit once — the stored "Aurangabad" record is Maharashtra's, so that one
# district is recomputed here straight from the source grids (see recompute()).
SHARED_NAME = {"Aurangabad": "recomputed from source grid (name shared with Maharashtra)"}
# Patna rides along as a control: its recomputed value must match the JSON, which
# proves this path reproduces the generator before we trust the Aurangabad number.
CONTROL = "Patna"


def recompute(gdf: gpd.GeoDataFrame, names: list[str], weeks: list[str]) -> dict[str, dict[str, dict]]:
    """
    {week_key: {district: record}} for `names`, computed with the generator's own
    functions on the Bihar polygons — no name collisions, since the zones passed
    in are Bihar-only geometry rather than a dict keyed by district name.
    """
    zones = gdf[gdf["dtname"].isin(names)].copy()
    assert len(zones) == len(names), f"expected {len(names)} zones, got {len(zones)}"
    baseline = gen._load_historical(gen.CONFIG["rainfall_historical_nc"], mask_neg999=True,
                                    years=gen.CONFIG["rainfall_normal_years"])
    periods = {p["key"]: p for p in gen.iter_completed_week_periods(
        min(pd.Timestamp(k[:7] + "-01").date() for k in weeks), pd.Timestamp.today().date())}

    out = {}
    for key in weeks:
        p = periods[key]
        print(f"  recomputing {key} ...", flush=True)
        actual = gen._zonal_mean(gen.rainfall_actual(p["start"], p["end"]),
                                 "rain", "actual", zones, "dtname")
        normal = gen._zonal_mean(gen._period_normal(baseline, p, "sum"),
                                 "rain", "normal", zones, "dtname")
        df = actual.merge(normal, on="dtname")
        df["deviation"] = (df["actual"] - df["normal"]) / df["normal"] * 100
        out[key] = {r.dtname: {"actual": round(r.actual, 2), "normal": round(r.normal, 2),
                               "deviation": round(r.deviation, 1),
                               "category": gen.classify_rainfall(r.deviation)}
                    for r in df.itertuples()}
    return out


def week_label(rec: dict) -> str:
    month = pd.Timestamp(rec["start"]).strftime("%B")
    return f"Week {rec['week']} {month} {rec['year']}"


def build_frame(gdf: gpd.GeoDataFrame, rec: dict, fixes: dict) -> gpd.GeoDataFrame:
    """Join one period's district records onto the Bihar geometry."""
    src = {**rec["districts"], **fixes}  # recomputed records win over the JSON
    df = gdf.copy()
    for col in ("actual", "normal", "deviation"):
        df[col] = [src.get(n, {}).get(col) for n in df["dtname"]]
    df["category"] = [src.get(n, {}).get("category", "No Data") for n in df["dtname"]]
    df["note"] = [SHARED_NAME.get(n, "") for n in df["dtname"]]
    return df


def draw_map(df: gpd.GeoDataFrame, rec: dict, path: Path) -> None:
    counts = df["category"].value_counts()
    st = rec["states"][STATE]

    # Bihar's bbox is ~5.0 deg wide x 3.2 deg tall — keep the figure in that ratio
    # so `bbox_inches="tight"` does not leave a band of white under the map.
    fig, ax = plt.subplots(figsize=(13, 8.5))
    df.plot(ax=ax, color=df["category"].map(COLOR), edgecolor="#333B44", linewidth=0.5)

    for pt, name, dev in zip(df.geometry.representative_point(), df["dtname"], df["deviation"]):
        txt = name if dev is None or pd.isna(dev) else f"{name}\n{dev:+.0f}%"
        ax.annotate(txt, (pt.x, pt.y), ha="center", va="center", fontsize=6.2,
                    color="#1A2027", linespacing=1.15)

    ax.set_axis_off()
    ax.set_title(f"Bihar - Rainfall Departure\n{week_label(rec)}",
                 fontsize=17, fontweight="bold", color="#212B36", pad=30)
    ax.text(0.5, 1.012,
            f"{pd.Timestamp(rec['start']):%d %b} - {pd.Timestamp(rec['end']):%d %b %Y}"
            f"   |   State: {st['actual']:.1f} mm actual vs {st['normal']:.1f} mm normal"
            f"   ({st['deviation']:+.1f}%, {st['category']})",
            transform=ax.transAxes, ha="center", va="bottom",
            fontsize=9.5, color="#637381")

    handles = []
    for k, c, r in CATS:
        n = int(counts.get(k, 0))
        handles.append(Patch(facecolor=c, edgecolor="#333B44", linewidth=0.5,
                             label=f"{k}  ({r})  -  {n} district{'' if n == 1 else 's'}"))
    # Legend below the map: inside the axes it sits on top of south-west Bihar.
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01),
              ncol=3, frameon=False, fontsize=9.5,
              title="Rainfall departure from normal", title_fontsize=10.5,
              handlelength=1.6, columnspacing=2.2, labelspacing=0.7)

    foot = "Source: IMD gridded daily rainfall | Normal: 1971-2020 LPA | SatSure Climate Anomaly Atlas"
    ax.text(0.5, -0.24, foot, transform=ax.transAxes, ha="center", va="top",
            fontsize=8, color="#919EAB", linespacing=1.5)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def run(weeks: list[str], out: Path, csv_name: str, summary_name: str) -> None:
    """Maps + CSVs for `weeks` (period-JSON keys) into `out`."""
    gdf = gpd.read_file(DATA / "districts.geojson")
    gdf = gdf[gdf["stname"] == STATE][["dtname", "geometry"]].reset_index(drop=True)

    fixed = recompute(gdf, [*SHARED_NAME, CONTROL], weeks)

    rows, summary = [], []
    for key in weeks:
        rec = json.loads((DATA / "rainfall" / "weeks" / f"{key}.json").read_text(encoding="utf-8"))

        # Control: the recomputed Patna must reproduce the stored JSON record,
        # otherwise this path differs from the generator and the recomputed
        # Aurangabad cannot be trusted either. Tolerance is 0.1 rather than
        # exact: 2024-2025 week JSONs were published from the IMD .grd download
        # before actuals moved to the local NC, a seam worth <=0.05 mm on Patna
        # (2021-2023 and 2026 reproduce exactly). Categories must still match.
        got, want = fixed[key][CONTROL], rec["districts"][CONTROL]
        for f in ("actual", "normal", "deviation"):
            assert round(abs(got[f] - want[f]), 6) <= 0.1, f"{key} {CONTROL} {f}: {got[f]} != {want[f]}"
        assert got["category"] == want["category"], f"{key} {CONTROL} category mismatch"

        df = build_frame(gdf, rec, {n: fixed[key][n] for n in SHARED_NAME})
        draw_map(df, rec, out / "maps" / f"bihar_rainfall_{key}.png")

        for r in df.itertuples():
            rows.append({
                "week_key": key, "start": rec["start"], "end": rec["end"],
                "year": rec["year"], "month": pd.Timestamp(rec["start"]).strftime("%B"), "week": rec["week"],
                "state": "Bihar", "district": r.dtname,
                "actual_mm": r.actual, "normal_mm": r.normal,
                "deviation_pct": r.deviation, "category": r.category, "note": r.note,
            })

        st, counts = rec["states"][STATE], df["category"].value_counts()
        summary.append({
            "week_key": key, "year": rec["year"],
            "period": f"{rec['start']} to {rec['end']}",
            "label": week_label(rec),
            **{k: int(counts.get(k, 0)) for k, _, _ in CATS},
            "bihar_actual_mm": st["actual"], "bihar_normal_mm": st["normal"],
            "bihar_deviation_pct": st["deviation"], "bihar_category": st["category"],
        })

        assert len(df) == 38, f"{key}: expected 38 Bihar districts, got {len(df)}"
        assert df["category"].isin(COLOR).all(), f"{key}: unknown category"
        unjoined = df[df["actual"].isna()]["dtname"].tolist()
        assert not unjoined, f"{key}: no data joined for {unjoined}"

    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / csv_name, index=False)
    pd.DataFrame(summary).to_csv(out / summary_name, index=False)

    assert len(rows) == 38 * len(weeks), f"expected {38 * len(weeks)} rows, got {len(rows)}"
    print(f"{len(weeks)} maps -> {out / 'maps'}")
    print(f"{len(rows)} rows  -> {out}")


if __name__ == "__main__":
    run(WEEKS, OUT, f"bihar_rainfall_districtwise_{WEEKS[0][:7]}_{WEEKS[-1][:7]}.csv",
        "bihar_rainfall_category_summary.csv")
