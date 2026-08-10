"""
Karnataka & Maharashtra district-wise rainfall departure maps — Kharif 2026
(1 June to 31 July), using the Anomaly Atlas legend/categories.

Computes actual + normal straight from the source grids with the generator's
own functions (per-state geometry, so district-name collisions across states
cannot occur). One PNG per state.

Run:  C:\\ProgramData\\anaconda3\\envs\\spi\\python.exe kharif_2026_state_maps.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

import weather_anomaly_dashboard_generation as gen

DATA = Path(r"D:\Satsure\satsure_codes1\dashboard\weather_dashboard\data")
OUT = Path(r"D:\Satsure\satsure_codes1\dashboard\kharif_2026_report")  # not under data\ -> never published
STATES = {"KARNATAKA": 31, "MAHARASHTRA": 36}  # expected district counts
PERIOD = {"start": date(2026, 6, 1), "end": date(2026, 7, 31),
          "footprint": (6, 1, 7, 31), "spans_year": False}
TITLE_PERIOD = "Kharif 2026 (01 Jun - 31 Jul)"

# Same legend as satsure_dashboard/app.js (and bihar_weekly_report.py).
CATS = [
    ("Excess",    "#60b1f4", ">+20%"),
    ("Normal",    "#6ae944", "-19% to +20%"),
    ("Deficient", "#dd7534", "-20% to -59%"),
    ("Scanty",    "#ffe23a", "-60% to -99%"),
    ("No Rain",   "#969696", "<= -99%"),
    ("No Data",   "#E9EDF0", "-"),
]
COLOR = {k: c for k, c, _ in CATS}

# Districts too small to hold their own label (points offset, label pulled west).
LABEL_OFFSET = {"Mumbai": (-45, -18), "Mumbai Suburban": (-40, 22)}


def zonal(ds_actual, ds_normal, zones: gpd.GeoDataFrame, key: str) -> pd.DataFrame:
    df = gen._zonal_mean(ds_actual, "rain", "actual", zones, key).merge(
        gen._zonal_mean(ds_normal, "rain", "normal", zones, key), on=key)
    df["deviation"] = (df["actual"] - df["normal"]) / df["normal"] * 100
    df["category"] = df["deviation"].map(gen.classify_rainfall)
    return df


def draw_map(df: gpd.GeoDataFrame, state: str, st: pd.Series, path: Path) -> None:
    counts = df["category"].value_counts()
    b = df.total_bounds
    w, h = b[2] - b[0], b[3] - b[1]
    fig, ax = plt.subplots(figsize=(11, 11 * h / w))
    df.plot(ax=ax, color=df["category"].map(COLOR), edgecolor="#333B44", linewidth=0.5)

    for pt, name, dev in zip(df.geometry.representative_point(), df["dtname"], df["deviation"]):
        txt = name if pd.isna(dev) else f"{name}\n{dev:+.0f}%"
        if name in LABEL_OFFSET:  # tiny districts: lead the label out with an arrow
            ax.annotate(txt, (pt.x, pt.y), xytext=LABEL_OFFSET[name],
                        textcoords="offset points", ha="right", va="center",
                        fontsize=6.5, color="#1A2027", linespacing=1.15,
                        arrowprops=dict(arrowstyle="-", lw=0.5, color="#637381"))
        else:
            ax.annotate(txt, (pt.x, pt.y), ha="center", va="center", fontsize=6.5,
                        color="#1A2027", linespacing=1.15)

    ax.set_axis_off()
    ax.set_title(f"{state.title()} - Rainfall Departure\n{TITLE_PERIOD}",
                 fontsize=17, fontweight="bold", color="#212B36", pad=30)
    ax.text(0.5, 1.012,
            f"01 Jun - 31 Jul 2026   |   State: {st['actual']:.1f} mm actual vs "
            f"{st['normal']:.1f} mm normal   ({st['deviation']:+.1f}%, {st['category']})",
            transform=ax.transAxes, ha="center", va="bottom",
            fontsize=9.5, color="#637381")

    handles = []
    for k, c, r in CATS:
        n = int(counts.get(k, 0))
        handles.append(Patch(facecolor=c, edgecolor="#333B44", linewidth=0.5,
                             label=f"{k}  ({r})  -  {n} district{'' if n == 1 else 's'}"))
    leg = ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01),
                    ncol=3, frameon=False, fontsize=9.5,
                    title="Rainfall departure from normal", title_fontsize=10.5,
                    handlelength=1.6, columnspacing=2.2, labelspacing=0.7)

    # Footer goes below the legend, whose axes-fraction height varies with the
    # state's aspect ratio — measure the drawn legend instead of hard-coding.
    fig.canvas.draw()
    leg_bottom = leg.get_window_extent().transformed(ax.transAxes.inverted()).y0
    foot = "Source: IMD gridded daily rainfall | Normal: 1971-2020 LPA | SatSure Climate Anomaly Atlas"
    ax.text(0.5, leg_bottom - 0.015, foot, transform=ax.transAxes, ha="center", va="top",
            fontsize=8, color="#919EAB", linespacing=1.5)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    gdf = gpd.read_file(DATA / "districts.geojson")

    print("computing actual grid (1 Jun - 31 Jul 2026) ...", flush=True)
    actual = gen.rainfall_actual(PERIOD["start"], PERIOD["end"])
    print("computing 1971-2020 normal grid for the same window ...", flush=True)
    baseline = gen._load_historical(gen.CONFIG["rainfall_historical_nc"], mask_neg999=True,
                                    years=gen.CONFIG["rainfall_normal_years"])
    normal = gen._period_normal(baseline, PERIOD, "sum")

    for state, n_expected in STATES.items():
        zones = gdf[gdf["stname"] == state][["dtname", "stname", "geometry"]].reset_index(drop=True)
        assert len(zones) == n_expected, f"{state}: expected {n_expected} districts, got {len(zones)}"

        df = zones.merge(zonal(actual, normal, zones, "dtname"), on="dtname")
        st = zonal(actual, normal, zones.dissolve(by="stname").reset_index(), "stname").iloc[0]

        assert df["category"].isin(COLOR).all(), f"{state}: unknown category"
        assert df["actual"].notna().all(), f"{state}: no data for {df[df['actual'].isna()]['dtname'].tolist()}"

        out = OUT / "maps" / f"{state.lower()}_rainfall_kharif2026_jun-jul.png"
        draw_map(df, state, st, out)
        print(f"{state}: {st['actual']:.1f} mm vs {st['normal']:.1f} mm "
              f"({st['deviation']:+.1f}%, {st['category']}) -> {out}", flush=True)


if __name__ == "__main__":
    main()
